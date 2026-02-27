from __future__ import annotations

import inspect
import json
import re
from typing import Any

from tester_agent.config import QwenConfig
from tester_agent.qwen_tools import BrowserTool


class QwenThinkingReasoner:
    SYSTEM_PROMPT = (
        "Ты автономный тестировщик регистрации на сайте. Анализируешь неудачную попытку регистрации и предлагаешь следующее действие. "
        "Можешь вызывать инструмент browser_automation с action=analyze_failure. "
        "Ответ дай в JSON с полями: next_action, should_retry, retry_delay_seconds."
    )

    def __init__(self, config: QwenConfig):
        self.config = config
        self._assistant = None
        self._assistant_error: str | None = None
        if self.config.enabled:
            self._assistant = self._build_assistant()
            if self._assistant is None:
                raise RuntimeError(
                    "QWEN_ENABLED=true, but Qwen-Agent Assistant is unavailable. "
                    f"Install `qwen-agent` and check settings. Details: {self._assistant_error}"
                )

    async def decide(self, attempt_result: dict[str, Any], attempt: int, max_retries: int) -> dict[str, Any]:
        if not self.config.enabled:
            return self._fallback(attempt_result, attempt, max_retries)
        if self._assistant is None:
            fallback = self._fallback(attempt_result, attempt, max_retries)
            fallback["source"] = "heuristic"
            fallback["framework_error"] = self._assistant_error or "Qwen-Agent Assistant unavailable."
            return fallback

        request_payload = {
            "attempt": attempt,
            "max_retries": max_retries,
            "reason": attempt_result.get("reason"),
            "final_url": attempt_result.get("final_url"),
            "dashboard_checks": attempt_result.get("dashboard_checks", {}),
        }
        messages = [
            {
                "role": "user",
                "content": (
                    "Проанализируй провал регистрации и предложи следующее действие.\n"
                    f"Данные: {json.dumps(request_payload, ensure_ascii=False)}"
                ),
            }
        ]

        try:
            raw = await self._run_assistant(messages)
            parsed = self._parse_response(raw)
            parsed["source"] = "qwen-agent"
            parsed["raw_response"] = raw
            return parsed
        except Exception as exc:  # noqa: BLE001
            fallback = self._fallback(attempt_result, attempt, max_retries)
            fallback["source"] = "heuristic"
            fallback["framework_error"] = f"Qwen-Agent call failed: {exc}"
            return fallback

    def _build_assistant(self) -> Any | None:
        try:
            from qwen_agent.agents import Assistant
        except Exception as exc:  # noqa: BLE001
            self._assistant_error = str(exc)
            return None

        llm_cfg = {
            "model": self.config.model,
            "model_server": self.config.model_server,
            "api_key": self.config.api_key,
            "generate_cfg": {
                "enable_thinking": self.config.enable_thinking,
                "max_tokens": self.config.max_tokens,
            },
        }

        return Assistant(
            llm=llm_cfg,
            function_list=[BrowserTool()],
            system_message=self.SYSTEM_PROMPT,
        )

    async def _run_assistant(self, messages: list[dict[str, str]]) -> str:
        response = self._assistant.run(messages)
        if inspect.isawaitable(response):
            response = await response

        if hasattr(response, "__aiter__"):
            parts: list[str] = []
            async for chunk in response:
                text = self._extract_text(chunk)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()

        if hasattr(response, "__iter__") and not isinstance(response, (str, dict, bytes)):
            parts = [self._extract_text(chunk) for chunk in response]
            return "\n".join(part for part in parts if part).strip()

        return self._extract_text(response)

    def _parse_response(self, raw: str) -> dict[str, Any]:
        payload = self._try_extract_json(raw)
        if payload:
            return {
                "next_action": str(payload.get("next_action") or self._fallback_message()),
                "should_retry": bool(payload.get("should_retry", True)),
                "retry_delay_seconds": int(payload.get("retry_delay_seconds", 3)),
            }

        return {
            "next_action": raw.strip() or self._fallback_message(),
            "should_retry": True,
            "retry_delay_seconds": 3,
        }

    @staticmethod
    def _extract_text(response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            if "content" in response and isinstance(response["content"], str):
                return response["content"]
            if "text" in response and isinstance(response["text"], str):
                return response["text"]
            return json.dumps(response, ensure_ascii=False)
        return str(response)

    @staticmethod
    def _try_extract_json(raw: str) -> dict[str, Any] | None:
        raw = raw.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    def _fallback(self, attempt_result: dict[str, Any], attempt: int, max_retries: int) -> dict[str, Any]:
        reason = (attempt_result.get("reason") or "").lower()
        next_action = self._fallback_message(reason)
        return {
            "next_action": next_action,
            "should_retry": attempt < max_retries,
            "retry_delay_seconds": 3,
            "source": "heuristic",
        }

    @staticmethod
    def _fallback_message(reason: str = "") -> str:
        if "already" in reason or "duplicate" in reason or "существ" in reason:
            return "Email вероятно уже существует, сгенерировать нового пользователя и повторить."
        if "timeout" in reason or "timed out" in reason:
            return "Похоже на медленный ответ сервера, увеличить ожидание и повторить."
        if "captcha" in reason:
            return "Обнаружена CAPTCHA, нужен обход в тестовой среде или ручная проверка."
        if "500" in reason or "502" in reason or "503" in reason:
            return "Серверная ошибка, повторить позже и сохранить артефакты."
        return "Повторить с новыми данными и сохранить больше диагностических артефактов."
