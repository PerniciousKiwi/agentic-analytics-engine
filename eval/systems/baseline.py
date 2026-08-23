from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import psycopg
import yaml
from jinja2 import Template

from cardinal.config import get_settings
from cardinal.llm.client import OllamaClient
from cardinal.llm.registry import get_prompt_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODELS_CONFIG_PATH = PROJECT_ROOT / "configs" / "models.yaml"

PROMPT_PATH = PROJECT_ROOT / "src" / "cardinal" / "llm" / "prompts" / "generate_sql.j2"


def load_model_config() -> dict[str, Any]:
    """Load the Phase 3 model configuration."""
    with MODELS_CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError("configs/models.yaml must contain a mapping.")

    return config


def load_schema_dump() -> str:
    """Return the complete marts schema as DDL-like text."""
    query = """
        SELECT
            table_name,
            column_name,
            data_type,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'marts'
        ORDER BY table_name, ordinal_position
    """

    settings = get_settings()

    with (
        psycopg.connect(
            host=settings.warehouse_ro_host,
            port=settings.warehouse_ro_port,
            dbname=settings.warehouse_ro_db,
            user=settings.warehouse_ro_user,
            password=settings.warehouse_ro_password,
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(query)
        rows = cursor.fetchall()

    tables: dict[str, list[tuple[str, str, str]]] = {}

    for table_name, column_name, data_type, is_nullable in rows:
        tables.setdefault(table_name, []).append(
            (
                column_name,
                data_type,
                is_nullable,
            )
        )

    lines: list[str] = []

    for table_name, columns in tables.items():
        lines.append(f"CREATE TABLE marts.{table_name} (")

        column_lines = [
            f"    {column_name} {data_type} {'NULL' if is_nullable == 'YES' else 'NOT NULL'}"
            for column_name, data_type, is_nullable in columns
        ]

        lines.append(",\n".join(column_lines))
        lines.append(");")
        lines.append("")

    return "\n".join(lines).rstrip()


def load_sqlite_schema_dump(database_path: Path) -> str:
    """Return a SQLite database schema as DDL-like text."""
    query = """
        SELECT
            name,
            sql
        FROM sqlite_master
        WHERE type = 'table'
          AND sql IS NOT NULL
        ORDER BY name
    """

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(query).fetchall()

    return "\n\n".join(str(sql) for _, sql in rows)


def parse_sql_response(text: str) -> str:
    """Strip common markdown SQL fences without modifying the SQL."""
    cleaned = text.strip()

    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()

        if lines and lines[0].strip().lower() in {"```sql", "```postgresql", "```"}:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

    return cleaned


class BaselineSystem:
    """Naive full-schema SQL-generation baseline."""

    def __init__(self) -> None:
        settings = get_settings()
        model_config = load_model_config()

        self.model = str(model_config["model_fast"])
        self.temperature = float(model_config["temperature"]["fast"])
        self.max_output_tokens = int(model_config["max_output_tokens"]["fast"])

        self.prompt_template = Template(PROMPT_PATH.read_text(encoding="utf-8"))

        self.prompt_hash = get_prompt_hash()
        self.schema_dump = load_schema_dump()
        self.sqlite_schema_cache: dict[str, str] = {}

        self.loop = asyncio.new_event_loop()

        self.http_client = httpx.AsyncClient()

        self.client = OllamaClient(
            base_url=settings.ollama_base_url,
            model=self.model,
            timeout=300.0,
            http_client=self.http_client,
        )

    def resolve_schema_dump(self, db_context: dict[str, Any]) -> str:
        """Resolve the schema appropriate for the evaluation database."""
        source = db_context.get("source")

        if source == "postgres":
            return self.schema_dump

        if source == "sqlite":
            database_path = db_context.get("database_path")

            if not isinstance(database_path, Path):
                raise ValueError("SQLite evaluation requires a valid database_path.")

            cache_key = str(database_path)

            if cache_key not in self.sqlite_schema_cache:
                self.sqlite_schema_cache[cache_key] = load_sqlite_schema_dump(database_path)

            return self.sqlite_schema_cache[cache_key]

        raise ValueError(f"Unsupported evaluation source: {source!r}")

    def answer(
        self,
        question: str,
        db_context: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Generate SQL using the naive baseline prompt."""
        schema_dump = self.resolve_schema_dump(db_context)

        prompt = self.prompt_template.render(
            schema_dump=schema_dump,
            question=question,
        )

        response = self.loop.run_until_complete(
            self.client.complete(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_output_tokens,
            )
        )

        predicted_sql = parse_sql_response(response.text)

        metadata = {
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "latency_ms": response.latency_ms,
            "prompt_hash": self.prompt_hash,
            "llm_attempts": response.attempts,
            "llm_retried": response.retried,
        }

        return predicted_sql, metadata

    def close(self) -> None:
        """Close the HTTP client and event loop."""
        if not self.loop.is_closed():
            self.loop.run_until_complete(self.http_client.aclose())
            self.loop.close()
