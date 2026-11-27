# blackkite

Project card maintained by Octant. Octant updates it after each task; edit it freely, and Octant will keep your changes.

## Purpose

Help individual users (starting with the owner) hear about relevant Rwandan opportunities before their deadlines pass. The spec's success test is a weekly digest where at least half of the top 10 items are actionable, and no relevant item is first seen after its deadline.

## Users

Just me for now

## Current goal

Get to first real use: run M0 access tests, add API keys, deploy to a VPS and send the first real digest

## Definition of done

The spec's success test passes for the first user, then for a second user with a different profile without code changes

## Stack

- Python 3.13
- FastAPI
- SQLAlchemy 2
- Alembic
- Pydantic / pydantic-settings
- APScheduler
- Typer (bk CLI)
- uv
- httpx
- selectolax
- pypdf
- rapidfuzz
- Playwright (Python, headless Chromium renderer)
- Anthropic Claude API
- Voyage embeddings
- Brave Search API
- Resend (email)
- IMAP (email ingest)
- PostgreSQL 16 with pgvector and pg_trgm
- React 19
- TypeScript
- Vite
- vite-plugin-pwa
- React Router
- Vitest
- Testing Library
- Playwright Test (e2e, visual, contract)
- pixelmatch
- Docker / Docker Compose
- Caddy
- Mailpit (dev)

## Structure

`api/blackkite/` is the Python backend. It holds the collectors (seven collector types), the pipeline (normalise, dedupe, enrich, extract, validate), scoring (rules, shortlist, Claude judge), delivery (digest, alerts, unsubscribe, mail), member features (feed, calendar/ics, profiles, privacy), routes, auth, the LLM clients, the renderer service, the worker, seed data and the db models and migrations. `api/tests/` holds the pytest suites. `web/` is the React PWA, with unit, e2e, contract and visual tests. `design/` holds the approved design boards and tokens, which are the source of truth and never edited. `deploy/` holds the Caddy config, backup and restore scripts, and the smoke test. `docs/` holds the plan, numbered decisions, API contract, design review, milestone reports and deploy guide. `CLAUDE.md` is the product spec. `.claude/` holds the subagents and path/bash guard hooks used to build the project.

## Commands

- run: `cp .env.example .env && make up (local stack with Mailpit at http://localhost:8080); or make dev (API with reload on :8000) and cd web && npm run dev`
- test: `make test (pytest against throwaway Postgres + pgvector); cd web && npm test && npm run typecheck && npm run e2e && npm run visual; make smoke`
- build: `make deploy-build (docker compose build); cd web && npm run build`
- deploy: `make deploy-build && make deploy-up on the VPS, then docker compose exec api bk bootstrap and bk seed-sources (see docs/deploy.md)`
- install: `make install (cd api && uv sync); cd web && npm ci`

## Conventions

- The product spec lives in CLAUDE.md; owner decisions are numbered in docs/decisions.md and referenced in code (e.g. decision 45, 46)
- design/ is never edited; the UI is pixel-checked against six design boards (npm run visual)
- Ruff lint config in pyproject.toml (flake8-bugbear settings)
- TypeScript type checking via tsc for app and node configs
- Tests run against real Postgres, not mocks
- Contract tests keep web stubs in sync with API schemas (contract:schemas dumps FastAPI schemas)
- Sources are database rows, not code; new sources of an existing collector type need no deploy
- Role checks are enforced server-side
- Users see fit words (Strong/Good/Possible) with quoted reasons, never numeric scores
- Every extracted field is backed by a quote; dates require an explicit year
- Secret link tokens are redacted from all logs
- Real email sending is gated by BK_MAIL_ALLOW_REAL_SEND and needs the owner's go-ahead
- Subagents (pipeline-builder, ui-builder, reviewer, pixel-checker, source-scout) and guard hooks in .claude/
- Milestone reports written to docs/ after each phase
- No CI configuration visible in the shown tree

Feature branches with PRs, all suites green

## Do not touch without asking

design/, the BK_MAIL_ALLOW_REAL_SEND switch, renderer isolation and urlsafety, auth, and database migrations

## Deployment

VPS and domain already chosen, production only

## Data sources

Yes, read-only access to production

## Notes

**Which external API keys and accounts do you already have (Anthropic, Voyage, Brave Search, Resend with a verified sending domain), and is there a monthly budget cap for model and API spend?**
All four, no fixed budget

**What public contact URL should go in the collector's User-Agent (BK_BOT_CONTACT_URL), and who should be listed as the contact for site operators?**
Not decided yet

**The spec mentions Ironji and AI lab tenders as profiles to score in v1. Are the seed profiles in api/blackkite/seed/profiles.yaml accurate for you, or do they need updating before the first real run?**
Accurate as written

## Decisions

- 2026-11-27 — Onboarded through the interview
docs/decisions.md is current; multiple profiles per user is confirmed
