from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(path: str) -> bool:  # type: ignore[override]
        if not os.path.exists(path):
            return False
        with open(path, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        return True


@dataclass
class Selectors:
    email: str = 'input[name="email"]'
    password: str = 'input[name="password"]'
    name: str = 'input[name="name"]'
    submit: str = 'button[type="submit"]'
    error: str = ".error-message, .alert-danger, [role='alert']"


@dataclass
class QwenConfig:
    enabled: bool = False
    model_server: str = "http://localhost:11434/v1"
    model: str = "Qwen/Qwen3-14B"
    api_key: str = "EMPTY"
    max_tokens: int = 512
    enable_thinking: bool = True


@dataclass
class AgentConfig:
    base_url: str
    register_path: str = "/en/user/register"
    dashboard_url_pattern: str = r"/en/generate"
    max_retries: int = 3
    retry_delay_seconds: int = 3
    timeout_ms: int = 30000
    headless: bool = True
    locale: str = "en_US"
    video_dir: str = "test_recordings"
    artifact_dir: str = "artifacts"
    selectors: Selectors = field(default_factory=Selectors)
    qwen: QwenConfig = field(default_factory=QwenConfig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Registration testing agent with retries, video recording, and Qwen-Agent reasoning."
    )
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    parser.add_argument("--base-url", default=None, help="Base site URL (overrides env)")
    parser.add_argument("--register-path", default=None, help="Registration page path (overrides env)")
    parser.add_argument("--max-retries", type=int, default=None, help="Max attempts (overrides env)")
    parser.add_argument("--timeout-ms", type=int, default=None, help="Timeout in ms (overrides env)")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> AgentConfig:
    load_dotenv(args.env_file)

    base_url = args.base_url or _env_or("BASE_URL", "")
    if not base_url:
        raise ValueError("BASE_URL is required in .env (or pass --base-url).")

    selectors = Selectors(
        email=_env_or("EMAIL_SELECTOR", 'input[name="email"]'),
        password=_env_or("PASSWORD_SELECTOR", 'input[name="password"]'),
        name=_env_or("NAME_SELECTOR", 'input[name="name"]'),
        submit=_env_or("SUBMIT_SELECTOR", 'button[type="submit"]'),
        error=_env_or("ERROR_SELECTOR", ".error-message, .alert-danger, [role='alert']"),
    )

    qwen = QwenConfig(
        enabled=_parse_bool(_env_or("QWEN_ENABLED", "false")),
        model_server=_env_or("QWEN_MODEL_SERVER", "http://localhost:11434/v1"),
        model=_env_or("QWEN_MODEL", "Qwen/Qwen3-14B"),
        api_key=_env_or("QWEN_API_KEY", "EMPTY"),
        max_tokens=int(_env_or("QWEN_MAX_TOKENS", "512")),
        enable_thinking=_parse_bool(_env_or("QWEN_ENABLE_THINKING", "true")),
    )

    return AgentConfig(
        base_url=base_url,
        register_path=args.register_path or _env_or("REGISTER_PATH", "/en/user/register"),
        dashboard_url_pattern=_env_or("DASHBOARD_URL_PATTERN", r"/en/generate"),
        max_retries=args.max_retries if args.max_retries is not None else int(_env_or("MAX_RETRIES", "3")),
        retry_delay_seconds=int(_env_or("RETRY_DELAY_SECONDS", "3")),
        timeout_ms=args.timeout_ms if args.timeout_ms is not None else int(_env_or("TIMEOUT_MS", "30000")),
        headless=not args.headed if args.headed else _parse_bool(_env_or("HEADLESS", "true")),
        locale=_env_or("LOCALE", "en_US"),
        video_dir=_env_or("VIDEO_DIR", "test_recordings"),
        artifact_dir=_env_or("ARTIFACT_DIR", "artifacts"),
        selectors=selectors,
        qwen=qwen,
    )


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_or(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None else default
