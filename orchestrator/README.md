# Orchestrator

Python 3.11+, managed with `uv`.

```
uv sync --extra dev
uv run pytest
uv run airim serve                                   # live: listen for the mod, log to logs/
uv run airim replay tests/fixtures/sample.jsonl --hold   # develop the dashboard without the game
```

Modules: `receiver` (TCP JSONL from the mod), `bus` (fan-out + logging), `state` (latest colony state), `dashboard` (aiohttp HTTP + WebSocket, static page in `airim/static/`), `replay`, `cli`.
