# Blackkite developer tasks. Run from the repo root.
API := cd api &&

.PHONY: install migrate downgrade-base test bootstrap seed-sources worker dev up down

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

worker:         ## run the scheduler locally (active/testing sources on their schedules)
	$(API) uv run bk worker

dev:            ## run the API locally with reload
	$(API) uv run uvicorn blackkite.app:app --reload --port 8000

up:             ## compose: db + api + mailpit
	docker compose --profile dev up -d --build

down:
	docker compose --profile dev down
