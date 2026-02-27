from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from faker import Faker
from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from tester_agent.config import AgentConfig


class BrowserRegistrationFlow:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.fake = Faker(config.locale)
        self.video_dir = Path(config.video_dir)
        self.artifact_dir = Path(config.artifact_dir)
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def generate_user_data(self) -> dict[str, str]:
        return {
            "name": self.fake.name(),
            "email": f"test+{uuid4().hex[:10]}@example.com",
            "password": self.fake.password(length=14, special_chars=True, digits=True, upper_case=True, lower_case=True),
        }

    def register_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}{self.config.register_path}"

    async def run_attempt(self, test_id: str, attempt: int, user_data: dict[str, str]) -> dict[str, Any]:
        attempt_prefix = f"{test_id}_attempt{attempt}"
        attempt_dir = self.artifact_dir / attempt_prefix
        attempt_dir.mkdir(parents=True, exist_ok=True)

        result: dict[str, Any] = {
            "attempt": attempt,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "user_data": {"email": user_data["email"], "name": user_data["name"]},
            "success": False,
            "reason": None,
            "video_path": None,
            "dashboard_checks": {},
        }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.config.headless)
            context = await self._new_context(browser)
            page = await context.new_page()
            page.set_default_timeout(self.config.timeout_ms)
            page.set_default_navigation_timeout(self.config.timeout_ms)
            recorded_video = page.video

            try:
                await self._open_registration_via_home(page)
                await page.fill(self.config.selectors.email, user_data["email"])
                await page.fill(self.config.selectors.password, user_data["password"])
                await page.fill(self.config.selectors.name, user_data["name"])
                await page.screenshot(path=str(attempt_dir / "before_submit.png"))

                await page.locator('button[type="submit"]').first.click()
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(1500)
                await page.screenshot(path=str(attempt_dir / "after_submit.png"))

                current_url = page.url
                is_dashboard_url = bool(re.search(self.config.dashboard_url_pattern, current_url))
                dashboard_checks = await self.verify_dashboard(page)

                success = is_dashboard_url and dashboard_checks.get("ok", False)
                result["success"] = success
                result["final_url"] = current_url
                result["dashboard_checks"] = dashboard_checks

                if not is_dashboard_url:
                    error_text = await self._safe_text(page, self.config.selectors.error)
                    result["reason"] = error_text or "Registration did not redirect to dashboard URL."
                elif not dashboard_checks.get("ok", False):
                    result["reason"] = dashboard_checks.get("reason", "Dashboard checks failed.")

            except PlaywrightTimeoutError as exc:
                await page.screenshot(path=str(attempt_dir / "error.png"))
                result["reason"] = f"Timeout: {exc}"
            except Exception as exc:  # noqa: BLE001
                await page.screenshot(path=str(attempt_dir / "error.png"))
                result["reason"] = f"Unhandled error: {exc}"
            finally:
                await context.close()
                await browser.close()
                if recorded_video:
                    raw_path = await recorded_video.path()
                    finalized = self.video_dir / f"{attempt_prefix}.webm"
                    os.replace(raw_path, finalized)
                    result["video_path"] = str(finalized)

        return result

    async def verify_dashboard(self, page: Page) -> dict[str, Any]:
        combined_selector = "div.model-select.dropdown"
        exists_model_dropdown = await page.locator(combined_selector).count() > 0
        generate_button_exists = await page.locator("button#generateButton").count() > 0

        dropdown_menu_count = 0
        dropdown_item_count = 0
        if exists_model_dropdown:
            container = page.locator(combined_selector).first
            dropdown_menu = container.locator(".dropdown-menu")
            dropdown_menu_count = await dropdown_menu.count()
            if dropdown_menu_count > 0:
                first_menu = dropdown_menu.first
                direct_children = await first_menu.locator(":scope > *").count()
                if direct_children == 0:
                    direct_children = await first_menu.locator("li, a, button, div").count()
                dropdown_item_count = direct_children

        ok = (
            exists_model_dropdown
            and dropdown_menu_count > 0
            and dropdown_item_count >= 2
            and generate_button_exists
        )

        if ok:
            return {
                "ok": True,
                "model_select_dropdown_exists": True,
                "dropdown_menu_count": dropdown_menu_count,
                "dropdown_item_count": dropdown_item_count,
                "generate_button_exists": True,
            }

        problems: list[str] = []
        if not exists_model_dropdown:
            problems.append('Missing `div.model-select.dropdown`.')
        if dropdown_menu_count == 0:
            problems.append("Missing `.dropdown-menu` inside model select container.")
        if dropdown_item_count < 2:
            problems.append("Expected multiple elements inside `.dropdown-menu`.")
        if not generate_button_exists:
            problems.append("Missing `button#generateButton`.")

        return {
            "ok": False,
            "reason": " ".join(problems),
            "model_select_dropdown_exists": exists_model_dropdown,
            "dropdown_menu_count": dropdown_menu_count,
            "dropdown_item_count": dropdown_item_count,
            "generate_button_exists": generate_button_exists,
        }

    async def _new_context(self, browser: Browser) -> BrowserContext:
        return await browser.new_context(
            viewport={"width": 1366, "height": 768},
            record_video_dir=str(self.video_dir),
            record_video_size={"width": 1366, "height": 768},
        )

    async def _open_registration_via_home(self, page: Page) -> None:
        await page.goto(self.config.base_url.rstrip("/"), wait_until="domcontentloaded")

        clicked_generate = await self._click_first_existing(
            page,
            [
                page.get_by_role("button", name=re.compile(r"^Generate Image$", re.IGNORECASE)),
                page.get_by_role("link", name=re.compile(r"^Generate Image$", re.IGNORECASE)),
                page.get_by_role("button", name=re.compile(r"^Generate Video$", re.IGNORECASE)),
                page.get_by_role("link", name=re.compile(r"^Generate Video$", re.IGNORECASE)),
                page.locator("text=Generate Image"),
                page.locator("text=Generate Video"),
            ],
        )
        if not clicked_generate:
            raise RuntimeError("Cannot find 'Generate Image' or 'Generate Video' on landing page.")

        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_url(re.compile(r".*/en/generate.*"), timeout=self.config.timeout_ms)

        clicked_registration = await self._click_first_existing(
            page,
            [
                page.get_by_role("link", name=re.compile(r"^Registration$", re.IGNORECASE)),
                page.locator("a:has-text('Registration')"),
                page.locator("text=Registration"),
            ],
        )
        if not clicked_registration:
            raise RuntimeError("Cannot find 'Registration' link on login screen.")

        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_url(re.compile(r".*/en/user/register.*"), timeout=self.config.timeout_ms)

    async def _click_first_existing(self, page: Page, candidates: list[Any]) -> bool:
        for locator in candidates:
            try:
                if await locator.count() > 0:
                    await locator.first.click()
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    async def _safe_text(page: Page, selector: str) -> str | None:
        locator = page.locator(selector).first
        if await locator.count() == 0:
            return None
        text = await locator.text_content()
        return text.strip() if text else None
