# Telegram Job Crawler

A small Python project for collecting Telegram job-posting messages and storing raw text for analysis.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env .env.local
```

Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE_NUMBER` in `.env`. Leave `TELEGRAM_GROUP_IDS` empty to crawl every group and supergroup joined by the account, or set it to comma-separated IDs to restrict the crawl. Telegram API credentials are available from [my.telegram.org](https://my.telegram.org/apps).

The first run asks for the Telegram login code and, if enabled, the two-factor password. The session is saved under `data/tdlib/`, so later runs reuse the authenticated session. By default, history is fetched back to `2021-01-01`, with each row flushed to disk immediately and a one-second pause between groups. Set `CRAWL_UNTIL_DATE` to another ISO date, leave it empty for no date cutoff, or set `REQUEST_DELAY_SECONDS` higher for a slower crawl.

## Run

```bash
python -m src.main
```

Complete raw message objects are written one per line to `data/raw/group_<chat_id>.jsonl`. Each run resumes after the highest saved message ID, so existing messages are not fetched or written again. The crawler only reads groups joined by the authenticated account, makes sequential requests, and leaves Telegram's flood-wait protections enabled.
