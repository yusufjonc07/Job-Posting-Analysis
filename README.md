# Telegram Job Crawler

A small Python project for collecting Telegram job-posting messages and storing raw text for analysis.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env .env.local
```

Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE_NUMBER` in `.env`. The collector reads every message from `TELEGRAM_SOURCE_GROUP_ID` and uses `TELEGRAM_SOURCE_GROUP_TITLE` only as a fallback lookup. Telegram API credentials are available from [my.telegram.org](https://my.telegram.org/apps).

The first run asks for the Telegram login code and, if enabled, the two-factor password. The session is saved under `data/tdlib/`, so later runs reuse the authenticated session. By default, source history is fetched back to `2025-01-01`, with each row flushed to the JSONL file for the referenced `Guruh:` and a one-second pause between runs. Set `CRAWL_UNTIL_DATE` to another ISO date or set `REQUEST_DELAY_SECONDS` higher for a slower crawl.

## Run

```bash
python -m src.main
```

Complete raw message objects are written one per line to `data/raw/group_<referenced_chat_id>.jsonl`. Posts without a resolvable public `Guruh:` link go to a `group_unmatched_*.jsonl` audit file. A source checkpoint under `data/raw/.state/` prevents already processed source messages from being fetched again. The crawler reads every message from the single source group, makes sequential requests, and leaves Telegram's flood-wait protections enabled.

## Web app

A live dashboard (FastAPI + React) over `data/raw`, updated in real time as Telegram pushes new posts.

```bash
python -m src.main                                       # once, in a terminal: logs in to Telegram if needed
cd frontend && npm install && npm run build && cd ..     # once, and after frontend changes
uvicorn src.api.main:app --port 8000                     # then open http://localhost:8000
```

How new posts reach the page:

1. The server starts the Telegram listener (`python -m src.main --listen`) as a child process and restarts it if it stops. The listener follows the source group (posts routed by their `Guruh:` link) and every group that has its own `group_-100<id>.jsonl` history (or the groups in `TELEGRAM_GROUP_IDS`). On start it fills the gap since the newest stored message of each, then Telegram pushes each new message to it and it is written to `data/raw` immediately. Every 5 minutes it re-checks the newest messages (one request per group) in case a dropped connection missed any. Messages already stored are never written again.
2. The server notices the changed file within milliseconds, updates its in-memory statistics and pushes an update to every open page (server-sent events).

The web app never calls Telegram: every page request is answered from the server's memory. Telegram lookups (group links, titles) are saved in `data/raw/.state/telegram_lookups.json` and requested only once, also across restarts. Only one crawler/listener can use the Telegram session at a time; a second one stops with a message.

The first server start reads every raw file (about 20 s) and saves a cache to `data/cache/`; later starts take under a second. Set `API_TELEGRAM_LISTENER=0` to run the dashboard without the listener (e.g. when you run `python -m src.main --listen` yourself in another terminal; the sidebar shows its status either way). For frontend development, run `npm run dev` in `frontend/` (http://localhost:5173); it proxies `/api` to port 8000. Other settings: `RAW_DATA_DIR`, `API_CACHE_DIR`, `API_POLL_SECONDS` (fallback check interval), `API_CORS_ORIGINS`, `API_WORKERS`. Tests: `python -m pytest tests`.
