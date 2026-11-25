FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
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
