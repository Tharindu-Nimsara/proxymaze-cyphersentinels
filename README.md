# ProxyMaze'26 — Cypher Sentinels

## Quick Start (local)

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Hit `http://localhost:8000/health` — should return `{"status":"ok"}`.

## Local testing

A mock proxy server is included in `tests/mock_proxies.py`. Run:

```bash
python tests/mock_proxies.py    # serves on :9000
python tests/scenario.py        # exercises the full flow
```

## Architecture

| File | Responsibility |
|------|----------------|
| `main.py` | FastAPI app, all 13 endpoints |
| `monitor.py` | Background worker that probes proxies on an interval |
| `alerts.py` | Alert state machine (fire / resolve / re-fire) |
| `webhooks.py` | Webhook dispatcher with retry + dedup |
| `integrations.py` | Slack and Discord payload formatters |
| `state.py` | Thread-safe in-memory state container |
