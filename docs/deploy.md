# Deploying Blackkite on a VPS

Runbook for the single-VPS stack (spec 9, decision 44). Nothing is deployed
without the owner's go-ahead, and no real email is sent until the owner says so
(decision 45). Everything below was run on a local Docker host on 2026-11-26
except where it says "not verified here" (see the last section).

## 1. What runs

| Service | Image | Networks | Published | Holds secrets |
|---|---|---|---|---|
| `proxy` | `blackkite-proxy` (web/Dockerfile: the built SPA + Caddy 2.11.6) | edge | 80, 443, 443/udp | TLS keys (volume `caddy-data`) |
| `api` | `blackkite-app` (api/Dockerfile target `app`) | default, edge, render-internal | none | yes (.env) |
| `worker` | `blackkite-app` (same image, `bk worker`) | default, render-internal | none | yes (.env) |
| `renderer` | `blackkite-renderer` (target `renderer`) | render-internal, render-egress | none | only `BK_RENDERER_TOKEN` |
| `db` | `pgvector/pgvector:pg16` | default | none | `POSTGRES_PASSWORD` |
| `mailpit` | `axllent/mailpit:v1.20` | default | 127.0.0.1:1025, :8025 | none; **local profile `dev` only** |

- `edge` (fixed subnet `BK_EDGE_SUBNET`, default 172.30.250.0/24) joins only the
  proxy and the api. The proxy has the fixed address `BK_PROXY_IP` (default
  172.30.250.10); compose sets the api's `BK_FORWARDED_ALLOW_IPS` to it, so the
  api believes `X-Forwarded-For` from the proxy and from nothing else.
- `render-internal` is internal (no route out); `render-egress` is the
  renderer's own way out. The renderer is not on `default`, so it cannot reach
  the database (decision 46, docs/api-contract.md 4.2).
- Volumes: `db-data` (database), `bk-data` (downloaded documents),
  `caddy-data` (certificates and ACME account), `caddy-config`.

Routing in the proxy (deploy/caddy/Caddyfile, same rules as web/apiProxy.ts):
exactly `/api`, `/api/*`, `/auth/verify`, `/auth/request-link`, `/auth/logout`
and `/me` go to the api. Everything else is the SPA with history fallback to
`/index.html`, including `/auth/confirm`, `/unsubscribe`, `/admin/*`,
`/sources`, `/calendar` and `/o/:id`. `/auth/confirm` and `/unsubscribe` are
never forwarded (their tokens are in the URL fragment). A missing file under
`/assets/` is a 404, not the app.

Headers from the proxy: a strict CSP (`default-src 'self'`, no inline scripts
or styles, `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`
(`no-referrer` on `/auth/confirm` and `/unsubscribe`), HSTS
(`max-age=31536000`) over HTTPS only, no `Server` banner. Hashed bundles under
`/assets/` are cached for a year (`immutable`); `index.html`, `sw.js` and the
manifest are `no-cache`, so a deploy reaches browsers on their next load.

## 2. Prerequisites

- A VPS with Ubuntu 24.04 or Debian 12, 2 vCPU and 4 GB RAM or more (each
  headless Chromium render can take several hundred MB), 20 GB disk.
- Docker Engine with the compose plugin, **compose 2.24 or newer** (the files
  use `env_file: required: false` and `!override`). Tested with Docker 29.9.3,
  compose 5.7.1, buildx 0.39.0.
- `git`, `openssl`, `curl`.
- Firewall: inbound 22 (SSH, ideally restricted to your address), 80 and 443
  (TCP; 443/UDP for HTTP/3) only. Outbound HTTPS to the sources, to the model,
  embedding and search APIs once their keys are set, and to Resend once real
  email is on.
- Building on the VPS needs Docker Hub, `mcr.microsoft.com` only for the
  opt-in prebuilt renderer, PyPI, the npm registry, `deb.debian.org` and
  Playwright's browser CDN (`cdn.playwright.dev`).

## 3. DNS

Choose the hostname (open decision 3 in CLAUDE.md; check the name before any
public launch). Create an `A` record (and `AAAA` if the VPS has IPv6) for it
pointing at the VPS, and wait until `dig +short <name>` returns the VPS
address. Caddy needs it to answer the ACME HTTP/TLS challenge on ports 80/443
at first boot; if DNS is not ready, Caddy keeps retrying with back-off and the
site has no certificate until it succeeds.

## 4. The `.env` file

```sh
git clone <repo> blackkite && cd blackkite
cp .env.example .env
chmod 600 .env
```

Fill in (generate each random value separately; never reuse one):

| Variable | Required | How |
|---|---|---|
| `BK_DOMAIN` | yes | the hostname from section 3, no scheme |
| `POSTGRES_PASSWORD` | yes | `openssl rand -hex 24` |
| `BK_RENDERER_TOKEN` | yes | `openssl rand -hex 32` |
| `BK_UNSUBSCRIBE_SECRET` | yes, for digests and alerts | `openssl rand -hex 32` |
| `BK_CALENDAR_SECRET` | for calendar feeds | `openssl rand -hex 32` (not the unsubscribe one) |
| `BK_FIRST_ADMIN_EMAIL` | yes | the owner's real address (only in this file) |
| `BK_BOT_CONTACT_URL` | before any real fetch | public page saying who runs the bot |
| `BK_MAIL_FROM` | for email | a sender on a domain verified with Resend |
| `BK_MAIL_TRANSPORT` | | `console` until real email is approved (section 8) |
| `BK_MAIL_ALLOW_REAL_SEND` | | `false` until the owner's go-ahead |
| `RESEND_API_KEY` | for email | from Resend, when the owner provides it |
| `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `BRAVE_API_KEY` | for extraction, embeddings, `search_query` | from each provider |
| `BK_INGEST_IMAP_*`, `BK_INGEST_AUTHSERV_ID` | for `email_ingest` sources | the shared inbox |

Compose sets these itself and ignores `.env` for them: `BK_ENV=prod`,
`BK_COOKIE_SECURE=true`, `BK_WEB_BASE_URL=https://$BK_DOMAIN`,
`BK_FORWARDED_ALLOW_IPS=$BK_PROXY_IP`, `BK_DATABASE_URL`, `BK_DATA_DIR`,
`BK_RENDERER_URL`. The renderer gets none of `.env`; it refuses to start if a
database URL, API key or password reaches its environment.

Leave `BK_BUILD_CA` empty and `BK_RENDERER_BASE=renderer-debian` on the VPS
(section 13 explains both).

Startup refuses example values and weak secrets (fewer than 32 characters or
fewer than 12 different characters).

## 5. Build and first boot

```sh
docker compose build                 # or: make deploy-build
docker compose up -d --wait          # or: make deploy-up
docker compose ps                    # every service "(healthy)"
docker compose logs proxy | grep -i certificate
curl -sI https://$BK_DOMAIN/ | head  # 200, strict-transport-security present
```

The api applies database migrations every time it starts (`bk migrate`, then
uvicorn). To run them by hand: `docker compose exec api bk migrate`.

Start order is enforced by health checks: db, then renderer, then api, then
worker and proxy. The proxy refuses to start (exit 2) if `BK_DOMAIN` is empty.

## 6. Bootstrap

```sh
docker compose exec api bk bootstrap       # first admin from BK_FIRST_ADMIN_EMAIL + the 7.1 seed profiles
docker compose exec api bk seed-sources    # the 4.5 seed sources, status testing
```

Both are idempotent. `bk demo-seed` is refused here (`BK_ENV is 'prod'`): demo
data belongs on a local stack only.

Signing in the first time: open `https://$BK_DOMAIN/sign-in` and ask for a
link. With `BK_MAIL_TRANSPORT=console` the mail, link included, is printed to
the api log: `docker compose logs api | grep -A3 'auth/confirm'`. The link is
single-use and expires after `BK_LOGIN_TOKEN_MINUTES` (15). Only the person
with shell access to the VPS can read it; once real email is on, nothing is
printed.

## 7. Promoting sources after M0

Seed sources start as `testing`: the worker runs them on schedule and their
items are stored but hidden from members. Before promoting any of them:

1. Do the M0 access test from the VPS (spec 11): plain fetch, headless fetch,
   RSS, email alerts. `docker compose exec api bk test-source "<name>"` shows
   what one run would parse without writing anything.
2. Record the result and the site's robots/terms position in the source's
   `access_note` (admin screen `/admin/sources/<id>`).
3. After at least two sane scheduled runs (run history on the admin screen;
   `docker compose exec api bk sources` lists status, health, items in 30 days
   and the last success), promote it to `active` on the admin screen.

Check each source's terms before making it `active` (spec 10): members see its
items.

## 8. Enabling real email (only after the owner's go-ahead)

1. Verify the sending domain with Resend; set `BK_MAIL_FROM` to an address on it.
2. Put `RESEND_API_KEY` in `.env` (from the owner, never through chat or a commit).
3. Set `BK_MAIL_TRANSPORT=resend`. While `BK_MAIL_ALLOW_REAL_SEND=false`, Resend
   sends nothing and the api logs what it would have sent: use this to check.
4. Preview a digest: `docker compose exec api bk digest --user <owner email> --dry-run`.
5. Only with the owner's explicit go-ahead: `BK_MAIL_ALLOW_REAL_SEND=true`.
6. Apply: `docker compose up -d --wait` (recreates api and worker with the new `.env`).

## 9. Updates

```sh
deploy/backup.sh                     # always first
git pull
docker compose build
docker compose up -d --wait          # migrations run as the api starts
docker compose ps
docker image prune -f                # old image layers
```

To roll back: check out the previous commit, rebuild, `up -d --wait`. If the
new version ran a migration the old one does not know, restore the backup
taken before the update (section 10).

## 10. Backups and restore

`deploy/backup.sh [DIR]` (default `./backups`, mode 700) runs `pg_dump
--format=custom` in the db container, checks the dump with `pg_restore
--list`, writes `blackkite-<UTC time>.dump` and deletes dumps older than
`BK_BACKUP_KEEP_DAYS` (14).

Nightly at 02:17 UTC (crontab of the user that runs docker):

```cron
17 2 * * * cd /home/<user>/blackkite && deploy/backup.sh >> backups/backup.log 2>&1
```

The dumps hold every user's email address, profiles and notes: copy them off
the VPS to storage only the owner can read (e.g. `rsync` to the owner's
machine, or an encrypted bucket), and delete old copies there too.

Also worth keeping, less often: `caddy-data` (certificates; Caddy re-issues
them if lost, within rate limits) and `bk-data` (downloaded documents; the
worker can fetch them again):

```sh
docker run --rm -v blackkite_bk-data:/d:ro -v "$PWD/backups":/b alpine tar czf /b/bk-data-$(date -u +%Y%m%d).tgz -C /d .
```

Restore (destructive: replaces the current database):

```sh
deploy/restore.sh backups/blackkite-<time>.dump --yes
```

It checks the dump, stops proxy, worker and api, drops and recreates the
database, restores with `pg_restore --no-owner --exit-on-error`, and starts
them again; the api then applies any newer migrations.

Restore on a new VPS: sections 2 to 5 with the same `.env` (the same
`POSTGRES_PASSWORD` is not required, but `BK_UNSUBSCRIBE_SECRET` and
`BK_CALENDAR_SECRET` must be the same or every emailed unsubscribe link and
calendar link stops working), then `deploy/restore.sh <dump> --yes`, then skip
bootstrap.

Tested locally (deploy/smoke/run.sh): a dump restored into a fresh pgvector
container and over the running stack, with identical row counts for users,
opportunities, profiles and sources, and a change made after the dump gone.

## 11. Logs and redaction

`docker compose logs <service>`; files rotate at 5 x 10 MB per container.

Calendar feeds (`/api/calendar.ics?token=…`) and one-click unsubscribe
(`/api/unsubscribe?token=…`) carry a secret token in the query string:

- The proxy rewrites `token=…` to `token=[redacted]` in its JSON access log
  (stdout) and in Caddy's own log (stderr, where upstream errors carry the
  request), and drops the `Cookie`, `Authorization` and `Referer` request
  headers and `Set-Cookie` from log lines.
- The api does the same in uvicorn's access log and its own logs
  (`blackkite/logredact.py`).
- Sign-in and unsubscribe page tokens are in URL fragments and never reach a
  server.

Exception: with `BK_MAIL_TRANSPORT=console` the api prints whole emails,
sign-in links included, to its log (section 6). Switch to `resend` before
inviting anyone else.

If you put another proxy or CDN in front, it must redact `token=` the same way
and set `X-Forwarded-For` and `X-Forwarded-Proto`; then set
`BK_TRUSTED_PROXIES` to its address or subnet so Caddy reads `{client_ip}`
from the header instead of overwriting it. Without that, every client shares
one rate-limit key. See section 15 for the shared-proxy layout.

## 12. What not to expose

- Only the proxy publishes ports. Never publish db (5432), api (8000),
  renderer (8100), Caddy's admin API (2019, bound to localhost inside the
  container) or its health port (8099).
- Never use `docker-compose.local.yml` or `deploy/smoke/compose.smoke.yml` on
  the VPS: the first turns on `BK_ENV=dev`, plain HTTP and Mailpit and
  publishes db and api on localhost; the second gives the renderer a test
  network. Never run `deploy/smoke/run.sh` there (it seeds demo data and
  restores over the database).
- Never set `BK_FORWARDED_ALLOW_IPS` to `*`.
- Never give the renderer an `env_file` or volumes.
- `.env` and `backups/` stay mode 600/700, out of git (`.gitignore` covers
  `.env`; keep `backups/` outside the repository or add it locally).

## 13. Local stack and smoke test

```sh
cp .env.example .env    # fill POSTGRES_PASSWORD, BK_RENDERER_TOKEN, BK_UNSUBSCRIBE_SECRET, BK_CALENDAR_SECRET
make up                 # docker compose -f docker-compose.yml -f docker-compose.local.yml --profile dev up -d --build --wait
open http://localhost:8080   # Mailpit: http://127.0.0.1:8025
make smoke              # deploy/smoke/run.sh; `make smoke-down` also removes containers, volumes, networks
```

The smoke test needs node with Playwright on the host. It builds and starts
the stack plus a local test page for the renderer, then checks (63 checks):
health of every service; migrate, bootstrap of `owner@example.com`, demo-seed
(and its refusal under `BK_ENV=prod`); sign-in link from Mailpit's API ->
`/auth/confirm#token` -> Continue -> ranked demo feed; admin API; deep links;
calendar `.ics` link and the redacted proxy log line; the unsubscribe page;
cache and security headers; JSON 404s under `/api`; `X-Forwarded-For`
overwriting; renderer isolation (no secret env, no route to the db, refusal to
start with a secret, render only with the token); `bk worker --once`; backup and
both restores.

### Building behind an intercepting proxy (opt-in)

Only for building behind an intercepting HTTPS proxy. Set `BK_BUILD_CA` in
`.env` to the proxy's CA bundle on the build host. Compose passes it as the
BuildKit secret `build_ca`, mounted only for the `pip`, `uv` and `npm` download
steps (and Playwright's browser download); it is never copied into an image
layer. If the proxy is not transparent, also pass it as build args, e.g.
`docker compose build --build-arg HTTPS_PROXY=http://proxy:3128`. Never commit
either.

Where `deb.debian.org` or Playwright's CDN cannot be reached at build time, set
`BK_RENDERER_BASE=renderer-prebuilt`: the renderer is then built on
`mcr.microsoft.com/playwright/python:v1.63.0-noble` (browsers and their system
libraries preinstalled) with Python 3.13 copied from the official bookworm
image. The image is much bigger (3.9 GB here, as it also carries Firefox and
WebKit). The default `renderer-debian` is the production choice.

## 14. Verified here, and not

Verified on a local Docker host (2026-11-26, deploy/smoke/run.sh, 63 of 63
checks passing): everything listed in section 13. Also checked by hand: with
`BK_SITE_ADDRESS=localhost` the same proxy image serves HTTPS (Caddy's local
CA), sends HSTS, redirects HTTP to HTTPS with 308 and proxies the api over
HTTP/2; with an empty `BK_DOMAIN` it refuses to start.

Not verified here:

- TLS issuance from Let's Encrypt for a real `BK_DOMAIN` (needs public DNS
  and ports 80/443 on the VPS).
- The default `renderer-debian` image: its build needs `deb.debian.org` and
  Playwright's CDN, which this build host could not reach; the renderer was
  tested with `renderer-prebuilt`.
- Real email through Resend, real sources, and model, embedding or search API
  calls (no keys; demo data only).
- The backup cron line and off-site copies.

Known issue (application code, not deployment): the PWA service worker answers
every navigation with its cached `index.html`. Once it is installed, opening an
`/api/...` URL in that browser (for example the calendar `.ics` link from the
app) shows the app instead of the file, and `/auth/confirm` and `/unsubscribe`
get that cached file's headers (the pages' own `no-referrer` meta tag still
applies). Calendar apps and mail providers do not run the service worker and are
unaffected. Fix: a `navigateFallbackDenylist` for `/api` and the other API paths
in `web/vite.config.ts`.

## 15. Behind a shared reverse proxy

Use this layout when the VPS already runs a shared reverse proxy (e.g. Caddy)
that holds ports 80 and 443 for multiple services. The blackkite proxy
publishes no host ports; it joins the shared proxy's Docker network and
listens on plain HTTP. TLS terminates at the shared proxy.

### When to use

- The host already has another Caddy (or nginx, Traefik, ...) on 80/443.
- You do not want blackkite to manage its own TLS certificates.
- Multiple services share one IP address.

If blackkite is the only service on the VPS, use the standalone layout
(sections 4 to 6).

### Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Base: all services, networks, volumes |
| `deploy/compose.shared-proxy.yml` | Override: proxy gets no ports, listens on :80, joins the shared network |
| `deploy/shared-caddy.example` | Template site block for the shared Caddy (**needs owner approval before loading**) |

### Required variables

Set these in `.env` (or export them):

| Variable | Value | How to find it |
|---|---|---|
| `BK_CADDY_NETWORK` | Name of the shared Caddy's Docker network | `docker network ls` |
| `BK_TRUSTED_PROXIES` | Subnet of that network, or the shared Caddy's IP | `docker network inspect <net> --format '{{(index .IPAM.Config 0).Subnet}}'` |
| `BK_DOMAIN` | Public hostname (same as standalone) | |

The override refuses to start if `BK_CADDY_NETWORK` or `BK_TRUSTED_PROXIES` is
unset, with a message naming the missing variable.

### Commands

```sh
# Build (same as standalone):
docker compose build
# or: make deploy-build

# Start:
docker compose -f docker-compose.yml -f deploy/compose.shared-proxy.yml up -d --wait
# or: make deploy-up-shared

# The rest (bootstrap, seed-sources, backup, restore) is the same as standalone.
```

### What changes

- **`BK_SITE_ADDRESS`** is `:80` (plain HTTP). The shared Caddy handles TLS.
  The blackkite proxy's `caddy-data` volume no longer stores certificates.
- **No published ports** on the proxy. The shared Caddy reaches it at
  `blackkite-proxy:80` on the shared Docker network.
- **Only the proxy** joins the shared network (`shared_edge`). db, api, worker
  and renderer stay on internal networks only.
- **`BK_TRUSTED_PROXIES`** tells the blackkite Caddy whose `X-Forwarded-For`
  and `X-Forwarded-Proto` to believe. When the peer is in that range,
  `{client_ip}` is taken from `X-Forwarded-For`; otherwise the header is
  overwritten with the peer's real address (same as standalone). Rate limits
  in the API still key on the real visitor's IP.
- **HSTS** is sent when the connection is HTTPS directly (standalone) or when
  `X-Forwarded-Proto: https` comes from a trusted proxy. An untrusted peer
  sending that header does not trigger HSTS.

### The shared Caddy template

`deploy/shared-caddy.example` is a site-block template for the shared Caddy.
**Do not load it without the owner's approval.** It reverse-proxies to
`blackkite-proxy:80`, sets `X-Forwarded-For`, `X-Forwarded-Proto: https`,
and strips `Forwarded` and `X-Forwarded-Port`. Review and adapt it for
your shared Caddy's conventions before loading.

### Memory limits

The renderer (`BK_RENDERER_MEM_LIMIT`, default 1 GB) and the worker
(`BK_WORKER_MEM_LIMIT`, default 768 MB) have configurable memory limits in
the base compose file. Together with the other services (db ~400 MB, api
~300 MB, proxy ~50 MB), the total is about 2.5 GB, leaving ~1.5 GB for the
OS, page cache and swap headroom on a 4 GB VPS.

ro-vps has about 4.7 GB available and is already using swap. If other
services on the host compete for memory, lower the limits:

```sh
BK_RENDERER_MEM_LIMIT=768m
BK_WORKER_MEM_LIMIT=512m
```

### Subnet clashes

The blackkite edge network defaults to `BK_EDGE_SUBNET=172.30.250.0/24`
with the proxy at `BK_PROXY_IP=172.30.250.10`. If that clashes with the
shared network or other networks on the host, change both in `.env`:

```sh
BK_EDGE_SUBNET=172.30.251.0/24
BK_PROXY_IP=172.30.251.10
```

### Verification

```sh
# Standalone config still works:
docker compose config >/dev/null

# Shared config works:
BK_CADDY_NETWORK=x BK_TRUSTED_PROXIES=172.18.0.0/16 \
  docker compose -f docker-compose.yml -f deploy/compose.shared-proxy.yml config >/dev/null

# Compose config checks (both layouts):
make check-compose

# Shared-proxy smoke test (creates throwaway containers and networks):
make smoke-shared
```
