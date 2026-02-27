from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tester_agent.browser_flow import BrowserRegistrationFlow
from tester_agent.config import AgentConfig
from tester_agent.qwen_reasoner import QwenThinkingReasoner


class RegistrationTestRunner:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.browser_flow = BrowserRegistrationFlow(config)
        self.reasoner = QwenThinkingReasoner(config.qwen)
        self.artifact_dir = Path(config.artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    async def run(self) -> dict[str, Any]:
        test_id = self._build_test_id()
        report: dict[str, Any] = {
            "test_id": test_id,
            "start_time": datetime.now().isoformat(timespec="seconds"),
            "base_url": self.config.base_url,
            "register_url": self.browser_flow.register_url(),
            "max_retries": self.config.max_retries,
            "qwen_enabled": self.config.qwen.enabled,
            "attempts": [],
            "status": "failed",
        }

        for attempt in range(1, self.config.max_retries + 1):
            print(f"[Attempt {attempt}/{self.config.max_retries}] Starting registration flow")
            user_data = self.browser_flow.generate_user_data()
            attempt_result = await self.browser_flow.run_attempt(test_id, attempt, user_data)
            report["attempts"].append(attempt_result)

            if attempt_result.get("success"):
                report["status"] = "success"
                report["successful_attempt"] = attempt
                break

            if attempt < self.config.max_retries:
                decision = await self.reasoner.decide(attempt_result, attempt, self.config.max_retries)
                attempt_result["next_action"] = decision.get("next_action")
                attempt_result["next_action_source"] = decision.get("source")
                if decision.get("framework_error"):
                    attempt_result["framework_error"] = decision["framework_error"]

                print(f"[Attempt {attempt}] Next action: {attempt_result['next_action']}")
                if decision.get("should_retry", True):
                    await asyncio.sleep(int(decision.get("retry_delay_seconds", self.config.retry_delay_seconds)))
                else:
                    break

        report["end_time"] = datetime.now().isoformat(timespec="seconds")
        report_path = self.artifact_dir / f"{test_id}_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report saved: {report_path}")
        return report

    @staticmethod
    def _build_test_id() -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"registration_test_{stamp}"

