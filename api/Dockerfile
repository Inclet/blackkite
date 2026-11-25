FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Headless Chromium for browser_list sources (spec 9: Playwright only there). The
# playwright CLI comes from the venv just synced, so the browser build is the one
# pinned for playwright 1.63 in uv.lock. --with-deps pulls Chromium's system
# libraries (apt, needs root: before USER). Browsers live outside any home
# directory, readable by the non-root bk user. Playwright launches Chromium
# without Chromium's own sandbox by default (no user namespaces needed in the
# container); collectors/browser_list.py routes every request through the URL
# guard and runs the browser in a killable child process. Nothing is downloaded
# at run time. The image is unbuilt here (no Docker daemon in the dev sandbox).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -c "import importlib.metadata as m; v = m.version('playwright'); \
        assert v.startswith('1.63.'), v" \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && chmod -R a+rX /ms-playwright
COPY . .
RUN uv sync --frozen --no-dev

# /app/data is the mount point for the bk-data volume (BK_DATA_DIR); a fresh named
# volume takes this directory's ownership, so the bk user can write documents to it.
RUN useradd --system --uid 10001 bk && mkdir -p /app/data && chown bk /app/data
USER bk
EXPOSE 8000
# Applies migrations, then serves. --proxy-headers so rate limits see the client IP
# behind the VPS reverse proxy. Forwarded headers are trusted only from the peer
# addresses in BK_FORWARDED_ALLOW_IPS (comma-separated; default 127.0.0.1). Never
# set it to '*': any client could then forge X-Forwarded-For and dodge the per-IP
# limit. The proxy must overwrite X-Forwarded-For, not append to it.
ENV BK_FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "bk migrate && exec uvicorn blackkite.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=\"${BK_FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
