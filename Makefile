# Blackkite developer tasks. Run from the repo root.
API := cd api &&

.PHONY: install migrate downgrade-base test bootstrap seed-sources demo-seed worker renderer dev up down smoke smoke-down smoke-shared check-compose deploy-build deploy-up deploy-up-shared backup

install:        ## install API dependencies
	$(API) uv sync

migrate:        ## alembic upgrade head (uses BK_DATABASE_URL)
	$(API) uv run alembic upgrade head

downgrade-base: ## alembic downgrade base
	$(API) uv run alembic downgrade base

test:           ## pytest against real Postgres (BK_TEST_DATABASE_URL or a throwaway cluster)
	$(API) uv run pytest

bootstrap:      ## first admin from BK_FIRST_ADMIN_EMAIL + seed profiles (idempotent)
	$(API) uv run bk bootstrap

seed-sources:   ## seed sources as status testing (idempotent)
	$(API) uv run bk seed-sources

demo-seed:      ## dev only (BK_ENV=dev): fictional demo catalogue, rules-only scores
	$(API) uv run bk demo-seed

worker:         ## run the scheduler locally (active/testing sources on their schedules)
	$(API) uv run bk worker

renderer:       ## run the renderer service locally (needs BK_RENDERER_TOKEN in the shell; no .env is read)
	$(API) uv run bk renderer

dev:            ## run the API locally with reload
	$(API) uv run uvicorn blackkite.app:app --reload --port 8000

# --- Containers (docs/deploy.md) ---
LOCAL := docker compose -f docker-compose.yml -f docker-compose.local.yml --profile dev

up:             ## local stack: every service + Mailpit, BK_ENV=dev, http://localhost:8080
	$(LOCAL) up -d --build --wait

down:           ## stop the local stack (keeps volumes; `$(LOCAL) down -v` removes them)
	$(LOCAL) down

smoke:          ## local stack end-to-end smoke test through the proxy (leaves it running)
	deploy/smoke/run.sh

smoke-down:     ## smoke test, then remove the stack's containers, volumes and networks
	deploy/smoke/run.sh --down

smoke-shared:   ## shared-proxy layout smoke test (creates throwaway containers and networks)
	deploy/smoke-shared-proxy.sh

check-compose:  ## validate standalone and shared-proxy compose configs (no containers)
	deploy/check-compose-configs.sh

deploy-build:   ## VPS: build the production images
	docker compose build

deploy-up:      ## VPS: start or update the production stack (BK_ENV=prod, HTTPS for BK_DOMAIN)
	docker compose up -d --wait

SHARED := docker compose -f docker-compose.yml -f deploy/compose.shared-proxy.yml

deploy-up-shared: ## VPS: start behind a shared reverse proxy (needs BK_CADDY_NETWORK, BK_TRUSTED_PROXIES)
	$(SHARED) up -d --wait

backup:         ## VPS: dump the database to ./backups (deploy/backup.sh)
	deploy/backup.sh
