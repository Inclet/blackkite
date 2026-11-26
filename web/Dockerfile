# Web app + reverse proxy image (`proxy` service in docker-compose.yml).
#   stage build: node builds the PWA (vite build) into static files.
#   final stage: Caddy serves those files and proxies the API paths
#     (deploy/caddy/Caddyfile). No node in the runtime image.
#
# Build contexts (compose passes them): this directory, plus `design` (../design,
# imported by vite.config.ts as @design) and `caddy` (../deploy/caddy).
# Behind an intercepting HTTPS proxy, pass its CA bundle as the BuildKit secret
# `build_ca` (docs/deploy.md); it is mounted for `npm ci` only, never stored.

FROM node:22.23.5-alpine AS build
WORKDIR /src/web
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm ci --no-audit --no-fund --ignore-scripts
COPY --from=design . /src/design
COPY . .
RUN npm run build

FROM caddy:2.11.6-alpine
COPY --from=caddy Caddyfile /etc/caddy/Caddyfile
COPY --from=caddy --chmod=0755 start.sh /usr/local/bin/bk-proxy-start
COPY --from=build /src/web/dist /srv
RUN caddy fmt /etc/caddy/Caddyfile >/dev/null \
    && BK_SITE_ADDRESS=:80 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
EXPOSE 80 443 443/udp
CMD ["bk-proxy-start"]
