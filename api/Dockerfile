# Two images from one file (decision 46):
#   target `app` (the default, last stage): api and worker. No browser.
#   target `renderer`: `bk renderer`, headless Chromium for browser_list. It is
#     started with no secrets (docker-compose.yml) and refuses to start if any
#     database URL, API key or password reaches its environment.
# Unbuilt in the dev sandbox (no Docker daemon there).

# --- dependencies, shared by both images ----------------------------------------------
FROM python:3.13-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
RUN useradd --system --uid 10001 bk

# --- renderer: Chromium, no secrets --------------------------------------------------
FROM deps AS renderer

# The playwright CLI comes from the venv just synced, so the browser build is the
# one pinned for playwright 1.63 in uv.lock. --with-deps pulls Chromium's system
# libraries (apt, needs root: before USER). Browsers live outside any home
# directory, readable by the non-root bk user. Playwright launches Chromium
# without Chromium's own sandbox by default (no user namespaces needed); the
# browser runs in a killable child process and every request it makes goes
# through the URL guard (collectors/browser_list.py). Nothing is downloaded at
# run time. Installed before the code is copied so code changes keep this layer.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -c "import importlib.metadata as m; v = m.version('playwright'); \
        assert v.startswith('1.63.'), v" \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && chmod -R a+rX /ms-playwright
COPY . .
RUN uv sync --frozen --no-dev
USER bk
# Chromium and the Playwright driver write their scratch files under HOME.
ENV HOME=/tmp
EXPOSE 8100
CMD ["bk", "renderer", "--host", "0.0.0.0", "--port", "8100"]

# --- app: api and worker (default target) ----------------------------------------------
FROM deps AS app

COPY . .
RUN uv sync --frozen --no-dev

# /app/data is the mount point for the bk-data volume (BK_DATA_DIR); a fresh named
# volume takes this directory's ownership, so the bk user can write documents to it.
RUN mkdir -p /app/data && chown bk /app/data
USER bk
EXPOSE 8000
# Applies migrations, then serves. --proxy-headers so rate limits see the client IP
# behind the VPS reverse proxy. Forwarded headers are trusted only from the peer
# addresses in BK_FORWARDED_ALLOW_IPS (comma-separated; default 127.0.0.1). Never
# set it to '*': any client could then forge X-Forwarded-For and dodge the per-IP
# limit. The proxy must overwrite X-Forwarded-For, not append to it.
ENV BK_FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "bk migrate && exec uvicorn blackkite.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=\"${BK_FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
