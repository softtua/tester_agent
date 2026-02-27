# Registration Tester Agent

Agent for end-to-end registration testing with retries, dashboard checks, and video recording.
Qwen thinking is implemented via Qwen-Agent framework (`Assistant` + custom `BaseTool`).

## What it verifies

Navigation flow before registration:
- opens landing page
- clicks `Generate Image` or `Generate Video`
- waits for `/en/generate`
- clicks `Registration` link under login form
- waits for `/en/user/register`

After successful registration and redirect to user area, it checks:

- `div` element with both classes: `.model-select.dropdown`
- Inside it, `.dropdown-menu` exists and contains multiple child elements
- `button` with id `generateButton` exists

If registration fails, the agent analyzes the reason and retries with new test data.

## Setup

```bash
uv sync
uv run playwright install chromium
```

## Configuration via .env

Create `.env` from `.env.example` and fill at least `BASE_URL`.

```bash
cp .env.example .env
```

## Run

```bash
uv run python registration_tester_agent.py
```

## Useful flags

- `--env-file` to use non-default env file path
- `--base-url`, `--register-path`, `--max-retries`, `--timeout-ms` to override env values
- `--headed` to run browser with UI (overrides `HEADLESS=true`)

Current test locale setup: `en` (`LOCALE=en_US`).

## Qwen thinking mode

Qwen integration follows the pattern from chat:
- `Assistant` from `qwen_agent.agents`
- `BaseTool` from `qwen_agent.tools` (see `BrowserTool` / `browser_automation`)

Enable it when you want model-based retry decisions:

- set `QWEN_ENABLED=true`
- point `QWEN_MODEL_SERVER` to your local or remote OpenAI-compatible endpoint
- set `QWEN_MODEL` (for example `Qwen/Qwen3-14B`)

## Project structure

- `registration_tester_agent.py`: CLI entrypoint
- `tester_agent/config.py`: env + CLI config
- `tester_agent/browser_flow.py`: Playwright flow, registration, dashboard checks, video
- `tester_agent/qwen_tools.py`: Qwen BaseTool implementation
- `tester_agent/qwen_reasoner.py`: Assistant-based reasoning
- `tester_agent/runner.py`: orchestration and JSON report

## Outputs

- Attempt videos: `test_recordings/*.webm`
- Screenshots per attempt: `artifacts/<test_id>_attemptN/*.png`
- Final JSON report: `artifacts/<test_id>_report.json`
