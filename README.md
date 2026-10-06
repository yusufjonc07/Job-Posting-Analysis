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

1. The server starts the Telegram listener (`python -m src.main --listen`) as a child process and restarts it if it stops. It follows the source group (posts routed by their `Guruh:` link) and every group we have an id for (from `data/raw` file names and `data/telegram_groups.csv`, or `TELEGRAM_GROUP_IDS`), whether the account has joined it or not. On start each fills its gap: since its newest stored message, or, for a group read for the first time, since the newest post we have for it (at most 30 days back). Then:
   - joined groups: Telegram pushes each new message instantly;
   - groups the account has not joined: Telegram does not push those, so they are checked in turn, each about every 2 minutes (`--poll`), with one request that returns only newer messages;
   - private groups the account is not in cannot be read; they are listed in the log as skipped.

   A group's own messages go to `group_-100<id>.jsonl`. Every 5 minutes the newest messages of pushed chats are re-checked in case a dropped connection missed any. Messages already stored are never written again.
2. The server notices the changed file within milliseconds, updates its in-memory statistics and pushes an update to every open page (server-sent events).

Only job offers are counted. Every message is classified by `src/utils/job_filter.py` (`classify_post` / `is_job_post`: job offer, person looking for work, parcels, flights and rides, sales and rentals, courses and services, conversation), reading Uzbek in Latin and Cyrillic letters, Russian and Korean. The dashboard (statistics, map, feed, live updates) uses job offers only and shows what was left out on the Posts page; `src.preprocess.load_messages()` also returns job offers only unless called with `jobs_only=False`. `data/raw` keeps every message.

The job map and all province numbers are public. Telegram group details (the Groups page, group names in the feed, the groups list in region details) are only shown after **Log in with Telegram**. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_USERNAME` in `.env` (a bot made with @BotFather); the page then opens `t.me/<bot>?start=<one-time code>` and unlocks when you press Start in the bot (works on localhost too). On a public domain, set it for the bot with @BotFather `/setdomain` and in `TELEGRAM_LOGIN_DOMAIN` to also offer the official Telegram login widget. `DASHBOARD_ALLOWED_USERS=@you,123456789` limits login to those accounts (empty: any Telegram account); `DASHBOARD_REQUIRE_LOGIN=0` shows the groups without login; `DASHBOARD_SECURE_COOKIE=1` behind https. Sessions last 30 days (signing key in `data/cache/session_secret`).

The web app never calls Telegram: every page request is answered from the server's memory. Telegram lookups (group links, titles) are saved in `data/raw/.state/telegram_lookups.json` and requested only once, also across restarts. Only one crawler/listener can use the Telegram session at a time; a second one stops with a message.

The first server start reads every raw file (about 20 s) and saves a cache to `data/cache/`; later starts take under a second. Set `API_TELEGRAM_LISTENER=0` to run the dashboard without the listener (e.g. when you run `python -m src.main --listen` yourself in another terminal; the sidebar shows its status either way). For frontend development, run `npm run dev` in `frontend/` (http://localhost:5173); it proxies `/api` to port 8000. Other settings: `RAW_DATA_DIR`, `API_CACHE_DIR`, `API_POLL_SECONDS` (fallback check interval), `API_CORS_ORIGINS`, `API_WORKERS`. Tests: `python -m pytest tests`.

## Finding new job groups

```bash
python -m src.discover_groups --list      # links mentioned in posts that are not checked yet (no Telegram request)
python -m src.discover_groups             # check up to 50 of them, most mentioned first
python -m src.discover_groups --level 3   # also check groups linked from checked groups, 3 levels deep (the default)
```

Every `t.me` link in the posts is collected. For each public group or channel not followed yet, its last 100 messages are read (one request) and classified; a group with at least 5 job offers that was active in the last 30 days is added to `data/telegram_groups.csv` with an empty province and city (assign them later; restart the server afterwards so existing posts are re-located) and its checked messages are saved to `data/raw`. The listener starts following added groups within 30 seconds. Links in our data are level 1; the links found in the messages of a checked group (added or not) are the next level, up to `--level` (default 3, `1` = no recursion). They cost no extra request and wait in the discovery state when a run's `--limit` is used up; all levels are checked most mentioned first. Each link is checked once (results in `data/raw/.state/discovery.json`; rejected links again after 30 days); private invite links cannot be checked without joining. Telegram limits username lookups, so a run stops at a long flood wait and the next run continues. While the listener runs it holds the Telegram session, so the command asks the listener to do the check (results appear in the server log); the listener also runs it by itself once a day (`DISCOVER_EVERY_HOURS`, `0` turns that off). Options: `--limit`, `--min-jobs`, `--min-mentions`, `--dry-run`.

## Deploy

The whole app (the dashboard, its API and the Telegram listener) is **one Docker container**: the image builds the React dashboard and the FastAPI server serves it at `/`, next to `/api`. Run it on any always-on machine with a disk (a VPS, Railway, Render, Fly.io). It cannot run on Vercel: the posts (`data/`, 450 MB) are not in git, and the listener must stay connected and keep writing new posts, which serverless functions cannot do.

**On a server with Docker (VPS)**

```bash
git clone https://github.com/yusufjonc07/ishbaroka && cd ishbaroka
# copy your data/ folder (raw/, tdlib/ with the Telegram session, telegram_groups.csv) and .env here, e.g. with rsync
echo "API_WORKERS=2" >> .env                                          # keeps the first data load within 2 GB RAM
DOMAIN=api.example.com docker compose --profile https up -d --build   # https://api.example.com (DNS record needed)
docker compose up -d --build                                          # or plain http://<server>:8000
```

No domain? `DOMAIN=<server-ip-with-dashes>.sslip.io` (e.g. `1-2-3-4.sslip.io`) still gets a real HTTPS certificate. No Telegram session on the server yet? Log in once: `docker compose run --rm dashboard python -m src.main`.

**On Railway / Render / Fly.io**: deploy the repository (they build the `Dockerfile`), attach a volume at `/app/data`, copy your data into it, and set the variables from `.env` plus `DASHBOARD_SECURE_COOKIE=1`.

Run **one** instance only, and stop the server on your own computer first: two copies using the same Telegram session at once can make Telegram revoke it.

**Telegram login on your domain**: the bot login works right away. For the official Telegram login button too, send `/setdomain` to @BotFather with your domain and set `TELEGRAM_LOGIN_DOMAIN` to it.

**Optional: dashboard on Vercel.** If you want the pages on Vercel's CDN, import the repository with **Root Directory `frontend`** and set `BACKEND_URL` to the container's https address; `frontend/api/backend.ts` forwards `/api/*` to it.
