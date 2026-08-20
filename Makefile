.PHONY: up down lint fmt type test test-all eval demo warehouse catalog

up:
	docker compose up -d

down:
	docker compose down

lint:
	uv run ruff check src tests eval

fmt:
	uv run ruff format src tests eval

type:
	uv run mypy src

test:
	uv run pytest -m "not integration and not slow and not llm"

test-all:
	uv run pytest

eval:
	uv run pytest eval

demo:
	uv run python -m cardinal.api.main

warehouse:
	docker compose run --rm api uv run dbt --project-dir warehouse

catalog:
	uv run python -m cardinal.catalog
