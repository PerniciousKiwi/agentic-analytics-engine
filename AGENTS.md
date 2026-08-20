# Agent Instructions

## Project Shape

- Python 3.11 only (`requires-python = ">=3.11,<3.12"`); the package is `cardinal` under `src/cardinal`.
- Keep application logic in `src/cardinal`, unit/integration/e2e tests in `tests`, evaluation code in `eval`, and dbt assets in `warehouse`.
- Read [pyproject.toml](pyproject.toml) for dependency groups, Ruff, mypy, and pytest configuration.

## Environment And Commands

- Copy `.env.example` to `.env` for local development. Never commit `.env` or put credentials in source; see [.env.example](.env.example) for the expected variables.
- Keep VS Code's `python.terminal.useEnvFile` enabled so Python terminals inherit the workspace environment file. The application also reads `.env` through [src/cardinal/config.py](src/cardinal/config.py).
- Use `uv run` for Python tools and prefer the existing Make targets in [Makefile](Makefile): `make test`, `make lint`, `make fmt`, and `make type`.
- Run `make test-all` only when integration, slow, and Ollama-backed tests are available. `make up` starts the local Docker services; `make down` stops them.
- Use `make demo` for the API module, `make eval` for evaluation tests, and `make warehouse` for dbt commands.

## Change Rules

- Preserve strict mypy typing and Ruff's configured checks; add or update focused tests with behavior changes.
- Keep secrets and machine-specific values in `.env`; use Docker Compose service environment variables for container-only hostnames.
- Prefer existing package boundaries and configuration helpers over introducing new global settings or ad hoc environment loading.
