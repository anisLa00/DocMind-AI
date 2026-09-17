.PHONY: help install dev up down migrate revision test lint format clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime and development dependencies
	pip install -r requirements-dev.txt

dev:  ## Run the API with autoreload
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

up:  ## Start Postgres, Redis and the API with docker compose
	docker compose up --build

down:  ## Stop the docker compose stack
	docker compose down

migrate:  ## Apply database migrations
	alembic upgrade head

revision:  ## Autogenerate a migration: make revision m="add thing"
	alembic revision --autogenerate -m "$(m)"

test:  ## Run the test suite
	pytest

lint:  ## Check formatting and lint rules
	ruff check .
	ruff format --check .

format:  ## Apply formatting and safe lint fixes
	ruff format .
	ruff check . --fix

clean:  ## Remove caches and build artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
