FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./

RUN uv sync --all-extras --no-install-project

COPY src ./src
COPY configs ./configs

RUN uv sync --all-extras
