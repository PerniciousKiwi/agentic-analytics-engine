from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from jinja2 import Template

from cardinal.agent.repair import FailureClass, run_with_repair
from cardinal.catalog.catalog import Catalog
from cardinal.catalog.manifest import Column, Manifest, Relation
from cardinal.catalog.models import Glossary
from cardinal.guardrails.pipeline import run_guardrails
from eval.systems.baseline import (
    BaselineSystem,
    parse_sql_response,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

REPAIR_PROMPT_PATH = PROJECT_ROOT / "src" / "cardinal" / "llm" / "prompts" / "repair_sql.j2"


class BaselineRepairedSystem(BaselineSystem):
    """Phase 5 baseline with guardrails and bounded SQL self-repair."""

    def __init__(self) -> None:
        super().__init__()

        # Used for the PostgreSQL/Olist evaluation.
        self.catalog = Catalog.load(
            PROJECT_ROOT / "warehouse/target/manifest.json",
            PROJECT_ROOT / "warehouse/semantic/metrics.yml",
            PROJECT_ROOT / "warehouse/semantic/glossary.yml",
            PROJECT_ROOT / "warehouse/target/catalog.json",
        )

        self.sqlite_catalog_cache: dict[str, Catalog] = {}

        self.repair_template = Template(
            REPAIR_PROMPT_PATH.read_text(encoding="utf-8"),
        )

    def _load_sqlite_catalog(
        self,
        database_path: Path,
    ) -> Catalog:
        """Build a lightweight catalog from a SQLite evaluation database."""
        cache_key = str(database_path.resolve())

        if cache_key in self.sqlite_catalog_cache:
            return self.sqlite_catalog_cache[cache_key]

        with sqlite3.connect(database_path) as connection:
            tables = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """,
            ).fetchall()

            relations: dict[str, Relation] = {}

            for (table_name,) in tables:
                columns_rows = connection.execute(
                    f'PRAGMA table_info("{table_name}")',
                ).fetchall()

                columns = {
                    str(row[1]): Column(
                        name=str(row[1]),
                        data_type=str(row[2]) if row[2] else None,
                    )
                    for row in columns_rows
                }

                unique_id = f"sqlite.{table_name}"

                relations[unique_id] = Relation(
                    unique_id=unique_id,
                    name=str(table_name),
                    schema_name="main",
                    database=None,
                    resource_type="model",
                    columns=columns,
                )

        manifest = Manifest(relations=relations)

        catalog = Catalog(
            manifest=manifest,
            metrics=[],
            glossary=Glossary(
                version=1,
                glossary={},
                pii_columns=[],
            ),
        )

        self.sqlite_catalog_cache[cache_key] = catalog

        return catalog

    def _resolve_catalog(
        self,
        db_context: dict[str, Any],
    ) -> Catalog:
        """Return the catalog matching the evaluation database."""
        source = db_context.get("source")

        if source == "sqlite":
            database_path = db_context.get("database_path")

            if not isinstance(database_path, Path):
                raise ValueError(
                    "SQLite evaluation requires a valid database_path.",
                )

            return self._load_sqlite_catalog(database_path)

        if source == "postgres":
            return self.catalog

        raise ValueError(f"Unsupported evaluation source: {source!r}")

    def _generate_sql(
        self,
        question: str,
        db_context: dict[str, Any],
    ) -> str:
        schema_dump = self.resolve_schema_dump(db_context)

        source = db_context.get("source")

        if source == "sqlite":
            sql_dialect = "SQLite"
        elif source == "postgres":
            sql_dialect = "PostgreSQL"
        else:
            raise ValueError(f"Unsupported evaluation source: {source!r}")

        prompt = self.prompt_template.render(
            schema_dump=schema_dump,
            question=question,
            sql_dialect=sql_dialect,
        )

        response = self.loop.run_until_complete(
            self.client.complete(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_output_tokens,
            ),
        )

        return parse_sql_response(response.text)

    def _repair_sql(
        self,
        question: str,
        failed_sql: str,
        failure_class: FailureClass,
        error_message: str,
        candidates: list[str],
        cost_budget: float,
        db_context: dict[str, Any],
    ) -> str:
        schema_dump = self.resolve_schema_dump(db_context)

        source = db_context.get("source")

        if source == "sqlite":
            sql_dialect = "SQLite"
        elif source == "postgres":
            sql_dialect = "PostgreSQL"
        else:
            raise ValueError(f"Unsupported evaluation source: {source!r}")

        prompt = self.repair_template.render(
            schema_dump=schema_dump,
            question=question,
            sql_dialect=sql_dialect,
            failed_sql=failed_sql,
            failure_class=failure_class.value,
            error_message=error_message,
            candidates=candidates,
            cost_budget=cost_budget,
        )

        response = self.loop.run_until_complete(
            self.client.complete(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_output_tokens,
            ),
        )

        return parse_sql_response(response.text)

    def answer(
        self,
        question: str,
        db_context: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Generate SQL and repair guardrail/execution failures."""

        metadata: dict[str, Any] = {
            "failure_class": None,
            "repair_attempts": 0,
            "degraded": False,
        }

        generated_sql = self._generate_sql(
            question,
            db_context,
        )

        catalog = self._resolve_catalog(db_context)

        def generate_fn(_: str) -> str:
            return generated_sql

        def guard_pipeline_fn(
            sql: str,
            catalog: Catalog,
            _cost_budget: float,
        ):
            return run_guardrails(
                sql,
                catalog,
                question=question,
                role="analyst",
                max_rows=1000,
                enforce_result_limit=False,
            )

        def execute_fn(sql: str) -> None:
            source = db_context.get("source")

            if source == "sqlite":
                database_path = db_context.get("database_path")

                if not isinstance(database_path, Path):
                    raise ValueError(
                        "SQLite evaluation requires a valid database_path.",
                    )

                with sqlite3.connect(database_path) as connection:
                    connection.execute(sql).fetchall()

                return

            if source == "postgres":
                import psycopg

                from cardinal.config import get_settings

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
                    cursor.execute(sql)
                    cursor.fetchall()

                return

            raise ValueError(f"Unsupported evaluation source: {source!r}")

        def repair_fn(
            repair_question: str,
            failed_sql: str,
            failure_class: FailureClass,
            error_message: str,
            candidates: list[str],
            cost_budget: float,
        ) -> str:
            return self._repair_sql(
                repair_question,
                failed_sql,
                failure_class,
                error_message,
                candidates,
                cost_budget,
                db_context,
            )

        result = run_with_repair(
            question,
            catalog,
            generate_fn,
            guard_pipeline_fn,
            execute_fn,
            repair_fn,
            max_attempts=3,
            cost_budget=None,
        )

        metadata["repair_attempts"] = max(
            0,
            len(result.attempts) - 1,
        )

        if result.succeeded:
            # A successful repair on attempt 2+ means the final SQL was
            # recovered through degradation/repair rather than the original
            # generation.
            metadata["degraded"] = len(result.attempts) > 1

            if result.attempts:
                first_failure = result.attempts[0].failure_class

                if first_failure is not None:
                    metadata["failure_class"] = first_failure.value

            return result.sql or "", metadata

        if result.attempts:
            final_attempt = result.attempts[-1]

            if final_attempt.failure_class is not None:
                metadata["failure_class"] = final_attempt.failure_class.value

            metadata["error"] = final_attempt.error_message

            return final_attempt.sql, metadata

        metadata["error"] = "Repair loop produced no attempts."

        return generated_sql, metadata

    def close(self) -> None:
        super().close()
