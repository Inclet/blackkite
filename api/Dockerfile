# Two images from one file (decision 46):
#   target `app` (the default, last stage): api and worker. No browser.
#   target `renderer`: `bk renderer`, headless Chromium for browser_list. It is
#     started with no secrets (docker-compose.yml) and refuses to start if any
#     database URL, API key or password reaches its environment.
#
# Build behind an intercepting HTTPS proxy (opt-in, docs/deploy.md): pass the
# proxy's CA bundle as the BuildKit secret `build_ca`. It is mounted only for the
# steps that download packages and is never written to an image layer. Without
# it (or with an empty one, the compose default) those steps use the image's own
# trust store.
#
# Renderer base (build arg RENDERER_BASE):
#   renderer-debian (default): Debian python:3.13-slim plus `playwright install
#     --with-deps chromium` (needs deb.debian.org and Playwright's download CDN).
#   renderer-prebuilt: Microsoft's Playwright 1.63 image, which already holds the
#     browsers and their system libraries, with Python 3.13 copied in from the
#     official bookworm image. Only for building where Debian's mirrors or the
#     Playwright CDN are unreachable; bigger (it also carries Firefox and WebKit).
ARG RENDERER_BASE=renderer-debian

# --- dependencies, shared by both images ----------------------------------------------
FROM python:3.13-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy PATH=/opt/venv/bin:$PATH
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --no-cache-dir uv==0.11.32

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export SSL_CERT_FILE=/run/secrets/build_ca; fi; \
    uv sync --frozen --no-dev --no-install-project --no-cache
RUN useradd --system --uid 10001 bk

# --- renderer base, default: Debian + Playwright's own Chromium download -------------
FROM deps AS renderer-debian

# The playwright CLI comes from the venv just synced, so the browser build is the
# one pinned for playwright 1.63 in uv.lock. --with-deps pulls Chromium's system
# libraries (apt, needs root: before USER). Browsers live outside any home
# directory, readable by the non-root bk user. Playwright launches Chromium
# without Chromium's own sandbox by default (no user namespaces needed); the
# browser runs in a killable child process and every request it makes goes
# through the URL guard (collectors/browser_list.py). Nothing is downloaded at
# run time. Installed before the code is copied so code changes keep this layer.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    python -c "import importlib.metadata as m; v = m.version('playwright'); \
        assert v.startswith('1.63.'), v" \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && chmod -R a+rX /ms-playwright

# --- renderer base, opt-in: Microsoft's Playwright image (browsers preinstalled) -----
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble AS renderer-prebuilt

# Python 3.13 from the official image built on Debian bookworm (glibc 2.36), which
# runs on this Ubuntu 24.04 base (glibc 2.39). The image's own Python 3.12 is unused.
COPY --from=python:3.13-slim-bookworm /usr/local/ /usr/local/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy PATH=/opt/venv/bin:/usr/local/bin:$PATH \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN ldconfig && python3.13 --version
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    python3.13 -m pip install --no-cache-dir uv==0.11.32
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export SSL_CERT_FILE=/run/secrets/build_ca; fi; \
    uv sync --frozen --no-dev --no-install-project --no-cache --python /usr/local/bin/python3.13
# The browsers in this image are the ones Playwright 1.63 expects: check, then
# make sure nothing will be downloaded at run time.
RUN python -c "import importlib.metadata as m; v = m.version('playwright'); \
        assert v == '1.63.0', v" \
    && python -m playwright install --dry-run chromium \
        | sed -n 's/^ *Install location: *//p' > /tmp/expected \
    && test -s /tmp/expected && xargs ls -d < /tmp/expected && rm /tmp/expected \
    && chmod -R a+rX /ms-playwright \
    && useradd --system --uid 10001 bk

# --- renderer: Chromium, no secrets --------------------------------------------------
FROM ${RENDERER_BASE} AS renderer

COPY . .
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export SSL_CERT_FILE=/run/secrets/build_ca; fi; \
    uv sync --frozen --no-dev --no-cache
USER bk
# Chromium and the Playwright driver write their scratch files under HOME.
ENV HOME=/tmp
EXPOSE 8100
CMD ["bk", "renderer", "--host", "0.0.0.0", "--port", "8100"]

# --- app: api and worker (default target) ----------------------------------------------
FROM deps AS app

COPY . .
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export SSL_CERT_FILE=/run/secrets/build_ca; fi; \
    uv sync --frozen --no-dev --no-cache

# /app/data is the mount point for the bk-data volume (BK_DATA_DIR); a fresh named
# volume takes this directory's ownership, so the bk user can write documents to it.
RUN mkdir -p /app/data && chown bk /app/data
USER bk
EXPOSE 8000
# Applies migrations, then serves. --proxy-headers so rate limits see the client IP
# behind the VPS reverse proxy. Forwarded headers are trusted only from the peer
# addresses in BK_FORWARDED_ALLOW_IPS (comma-separated; default 127.0.0.1;
# docker-compose.yml sets it to the proxy's fixed address). Never set it to '*':
# any client could then forge X-Forwarded-For and dodge the per-IP limit. The
# proxy must overwrite X-Forwarded-For, not append to it (deploy/caddy/Caddyfile does).
ENV BK_FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "bk migrate && exec uvicorn blackkite.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=\"${BK_FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
