.DEFAULT_GOAL := help
COMPOSE := docker compose
PROD := docker compose -f docker-compose.prod.yml
BE := $(COMPOSE) exec backend

help: ## Show commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from the example (once)
	@test -f .env || cp .env.example .env

up: env ## Start db, API (:8000) and web (:5173)
	$(COMPOSE) up -d --build

down: ## Stop everything
	$(COMPOSE) down

logs: ## Follow logs
	$(COMPOSE) logs -f --tail=100

migrate: ## Apply database migrations
	$(BE) alembic upgrade head

migration: ## New migration: make migration m="add item master"
	$(BE) alembic revision --autogenerate -m "$(m)"

seed: ## Seed shops and starter users
	$(BE) python -m app.scripts.seed

test: ## All backend tests (needs `make up`) + frontend tests
	$(BE) pytest
	$(COMPOSE) exec frontend npm test

lint: ## Lint and type-check both apps
	$(BE) sh -c "ruff check . && ruff format --check . && mypy app && alembic check"
	$(COMPOSE) exec frontend sh -c "npm run lint && npm run typecheck && npm run format:check"

fmt: ## Auto-format both apps
	$(BE) sh -c "ruff check --fix . && ruff format ."
	$(COMPOSE) exec frontend npm run format

gen-api: ## Regenerate frontend API types from the running backend
	$(COMPOSE) exec -e VITE_API_PROXY=http://backend:8000 frontend sh -c "npx openapi-typescript http://backend:8000/api/openapi.json -o src/api/schema.d.ts"

prod-up: ## Simple production: build and start (see docs/DEPLOYMENT.md)
	$(PROD) up -d --build

prod-seed: ## Production first-run seed
	$(PROD) exec backend python -m app.scripts.seed

prod-backup: ## Take a backup now (database and uploaded files)
	@mkdir -p backups; stamp=$$(date +%Y%m%d-%H%M); \
	$(PROD) exec -T db sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" --format=custom' > backups/erp-$$stamp.dump && \
	$(PROD) exec -T backend tar -czf - -C /data/files . > backups/erp-files-$$stamp.tar.gz && \
	echo "Wrote backups/erp-$$stamp.dump and backups/erp-files-$$stamp.tar.gz"

prod-verify: ## Check the books against themselves (add FULL=1 to re-read every file)
	$(PROD) exec backend python -m app.scripts.verify $(if $(FULL),--full,)

prod-drill: ## Restore drill: newest backup into a scratch copy, then check it
	./scripts/restore-drill.sh

.PHONY: help env up down logs migrate migration seed test lint fmt gen-api prod-up prod-seed prod-backup prod-verify prod-drill
