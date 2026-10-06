# One container for everything: the dashboard (built React app), its API and the Telegram listener.
# Data lives outside the image, in a volume at /app/data: raw/ (crawled posts), tdlib/ (Telegram session),
# cache/ (snapshot + login cookie key) and telegram_groups.csv.

# 1. Build the dashboard.
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. The Python server, which also serves the built dashboard at /.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements-server.txt .
RUN pip install -r requirements-server.txt

COPY config ./config
COPY src ./src
COPY --from=frontend /frontend/dist ./frontend/dist

RUN useradd --create-home --uid 1000 app && mkdir -p /app/data && chown app /app/data
USER app

VOLUME ["/app/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/api/health', timeout=4)"

# PORT is set by Railway / Render / Fly; --proxy-headers trusts X-Forwarded-* from the Vercel proxy or Caddy.
CMD ["sh", "-c", "exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
