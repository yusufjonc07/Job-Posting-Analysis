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

## Run

```bash
python -m src.main
```

The TDLib connection is isolated in `src/tdlib/client.py`; connect it to the TDLib binding and native library used by the deployment before crawling live chats. Raw text files are written under `data/raw/`.
