# Blackkite

Blackkite finds, ranks and tracks opportunities in Rwanda — tenders, investments, funding and events — for each user's own profiles, before their deadlines pass. Named after the black kite that circles over Kigali.

It collects notices once for everyone from a managed registry of sources, extracts each one into a structured record with a supporting quote for every field, and then matches and scores it privately against each user's profiles. Users get a ranked feed, a calendar, a weekly digest and urgent alerts.

> **Status:** every milestone in the spec (M0–M5) is built, reviewed and tested on synthetic and demo data. Nothing has run against real sites, real model APIs or real email yet; see [What's left before real use](#whats-left-before-real-use).

## What's in it

- **Sources** (`api/blackkite/sources`, `collectors`): sources are database rows, not code. Seven collector types — `html_list`, `browser_list` (headless Chromium in its own container), `rss`, `json_api`, `search_query` (Brave), `email_ingest` (IMAP) and allowlisted `custom` collectors (JSON-LD events, Umucyo awards and procurement plans). Admin-entered config is untrusted: URLs are checked against internal addresses at connect time and on every redirect; robots.txt, rate limits and size caps always apply.
- **Shared pipeline** (`api/blackkite/pipeline`): normalise → dedupe → enrich (detail pages, PDFs) → extract (Claude, every field backed by a quote from the notice) → validate (dates only with an explicit year; three trust states: confirmed, not yet confirmed, sources disagree).
- **Per-user scoring** (`api/blackkite/scoring`): hard filters, a cheap shortlist with no model call, then one Claude judgement per shortlisted pair. Users see a fit word (Strong, Good, Possible) with a reason that quotes the notice — never a number.
- **Delivery** (`api/blackkite/delivery`): weekly digest (email-safe HTML and plain text), urgent alerts, one-click unsubscribe, a personal calendar feed (`.ics`).
- **Web app** (`web/`): React + TypeScript PWA built from the approved design boards in `design/`, pixel-checked against them (all six boards at 0.00% difference). Feed, opportunity detail, shortlist, calendar, profiles, private items, sources, benchmarks of past awards, planned tenders, and admin screens.
- **Deployment** (`docker-compose.yml`, `deploy/`): Postgres with pgvector, API, worker, a secret-free renderer container, and a Caddy proxy with automatic HTTPS, redacted logs and strict security headers.

## Repository layout

| Path | What |
|---|---|
| `CLAUDE.md` | The product spec (start here) |
| `design/` | Approved design boards, tokens and assets — the source of truth for the UI; never edited |
| `api/` | Python 3.13 API, pipeline, scoring and worker (FastAPI, SQLAlchemy, Alembic, uv) |
| `web/` | React 19 + TypeScript + Vite PWA, with unit, end-to-end, contract and visual tests |
| `deploy/` | Caddy config, backup/restore scripts, end-to-end smoke test of the running stack |
| `docs/` | Plan, decisions, API contract, design-review list, milestone reports, deployment guide |
| `.claude/agents/` | The subagents used to build the project |

## Running it locally

You need Docker, and for the smoke test Node with Playwright.

```sh
cp .env.example .env   # fill POSTGRES_PASSWORD, BK_RENDERER_TOKEN, BK_UNSUBSCRIBE_SECRET,
                       # BK_CALENDAR_SECRET and BK_FIRST_ADMIN_EMAIL
make up                # every service plus Mailpit, BK_ENV=dev, at http://localhost:8080
```

The API applies database migrations when it starts. Then set up the first admin and some demo data:

```sh
LOCAL="docker compose -f docker-compose.yml -f docker-compose.local.yml"
$LOCAL exec api bk bootstrap          # first admin from BK_FIRST_ADMIN_EMAIL, with the seed profiles
$LOCAL exec api bk demo-seed          # dev only: fictional items, awards and planned tenders
$LOCAL exec worker bk worker --once   # one worker cycle (collect, score, alerts)
```

Sign in at http://localhost:8080 with your email; the sign-in link arrives in Mailpit at http://127.0.0.1:8025.

`make smoke` builds and starts the stack and runs the end-to-end smoke test through the proxy; `make down` stops it.

### Working on the code

```sh
make install && make test          # API: uv sync, then pytest against a throwaway Postgres with pgvector
cd web && npm ci && npm run dev    # web dev server (proxies the API paths to localhost:8000)
npm test                           # unit tests
npm run typecheck
npm run e2e                        # end-to-end tests against a stub API
npm run visual                     # pixel comparison against the six design boards
```

## Deploying

See [docs/deploy.md](docs/deploy.md): DNS, every secret and how to generate it, first boot, bootstrap, promoting sources, enabling real email, updates, backups and restore, and log redaction.

## Documentation

- [CLAUDE.md](CLAUDE.md) — the spec
- [docs/decisions.md](docs/decisions.md) — every owner decision, numbered
- [docs/api-contract.md](docs/api-contract.md) — the API as built
- [docs/design-review.md](docs/design-review.md) — screens and wording built without a design board, awaiting review
- [docs/token-mismatches.md](docs/token-mismatches.md) — where the design tokens and boards disagree
- Milestone reports: [phase 1](docs/phase-1-report.md), [2](docs/phase-2-report.md), [3](docs/phase-3-report.md), [4](docs/phase-4-report.md), [M3](docs/m3-report.md), [M4](docs/m4-report.md), [M5](docs/m5-report.md)

## What's left before real use

1. **M0 access test** of the seed sources from a real host, then configure and promote the sources (including Umucyo awards and plans).
2. **API keys:** Anthropic (extraction and scoring), Voyage (embeddings), Brave (search collector), Resend (email).
3. **A public contact URL** for the collector's User-Agent.
4. **A VPS and domain**, then deploy with `docs/deploy.md`.
5. **The owner's go-ahead for real email.**

Then the spec's success test can run: at least half of the weekly digest's top 10 should be items the user would act on.

## Guardrails

Blackkite shows short summaries with a link to the original, never republished notices. It respects robots.txt and site terms, identifies itself honestly and rate-limits every request. Investment items are factual listings, never advice. Profiles, scores, saved items, notes and private items are visible only to their owner.
