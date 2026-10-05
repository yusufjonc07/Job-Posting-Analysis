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
