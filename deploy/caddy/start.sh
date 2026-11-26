#!/bin/sh
# Entry point of the proxy image: refuse to start without a site address, so a
# VPS .env missing BK_DOMAIN fails loudly instead of serving the wrong host.
set -eu
if [ -z "${BK_SITE_ADDRESS:-}" ]; then
	echo "proxy: BK_SITE_ADDRESS is empty; set BK_DOMAIN in .env (docs/deploy.md)" >&2
	exit 2
fi
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
