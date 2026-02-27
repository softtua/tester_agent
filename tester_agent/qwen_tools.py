from __future__ import annotations

from typing import Any

try:
    from qwen_agent.tools import BaseTool
except ImportError:  # pragma: no cover
    class BaseTool:  # type: ignore[override]
        pass


class BrowserTool(BaseTool):
    name = "browser_automation"
    description = "Analyzes registration and dashboard verification outcomes for retry strategy."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["register", "verify", "analyze_failure"]},
            "reason": {"type": "string"},
            "dashboard_ok": {"type": "boolean"},
            "register_success": {"type": "boolean"},
            "attempt": {"type": "integer"},
            "max_retries": {"type": "integer"},
        },
        "required": ["action"],
    }

    async def call(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        action = str(params.get("action") or "").lower()
        reason = str(params.get("reason") or "").lower()
        dashboard_ok = bool(params.get("dashboard_ok"))
        register_success = bool(params.get("register_success"))
        attempt = int(params.get("attempt", 1))
        max_retries = int(params.get("max_retries", 3))

        if action == "register":
            return {"register_success": register_success, "message": "Registration state normalized."}
        if action == "verify":
            return {"dashboard_ok": dashboard_ok, "message": "Dashboard verification state normalized."}

        if action and action != "analyze_failure":
            return {"error": f"Unknown action: {action}"}

        if dashboard_ok:
            return {"category": "post_registration_validation", "next_action": "Retry with same flow and capture extra screenshots."}
        if "already" in reason or "duplicate" in reason or "существ" in reason:
            return {"category": "duplicate_email", "next_action": "Generate a new email and retry."}
        if "timeout" in reason or "timed out" in reason:
            return {"category": "timeout", "next_action": "Increase wait and retry after delay."}
        if "captcha" in reason:
            return {"category": "captcha", "next_action": "Requires manual bypass or test environment bypass."}
        if "500" in reason or "502" in reason or "503" in reason:
            return {"category": "server_error", "next_action": "Retry later; backend may be unstable."}
        if attempt >= max_retries:
            return {"category": "max_retries_reached", "next_action": "Stop retries and escalate with report artifacts."}
        return {"category": "unknown", "next_action": "Retry with fresh test data and keep collecting artifacts."}
