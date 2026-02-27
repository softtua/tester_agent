from __future__ import annotations

import asyncio
import json

from tester_agent.config import build_config, parse_args
from tester_agent.runner import RegistrationTestRunner


async def async_main() -> int:
    args = parse_args()
    config = build_config(args)
    runner = RegistrationTestRunner(config)
    report = await runner.run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))

