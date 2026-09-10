from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from jinja2 import Template

from cardinal.agent.repair import FailureClass, run_with_repair
from cardinal.catalog.catalog import Catalog
from cardinal.catalog.manifest import Column, Manifest, Relation
from cardinal.catalog.models import Glossary
from cardinal.confidence.self_consistency import run_self_consistency
from cardinal.confidence.synthesis import AnswerSynthesizer
from cardinal.guardrails.pipeline import run_guardrails
from cardinal.retrieval.context import SchemaContextAssembler
from cardinal.retrieval.service import RetrievalService
from eval.systems.baseline import (
    BaselineSystem,
    parse_sql_response,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROMPT_PATH = PROJECT_ROOT / "src" / "cardinal" / "llm" / "prompts" / "generate_sql_v2.j2"

REPAIR_PROMPT_PATH = PROJECT_ROOT / "src" / "cardinal" / "llm" / "prompts" / "repair_sql.j2"


class RetrievalGuardedRepairedSystem(BaselineSystem):
    """Phase 6 retrieval + guardrails + bounded SQL repair system."""

    def __init__(self) -> None:
        super().__init__()

        self.catalog = Catalog.load(
            PROJECT_ROOT / "warehouse/target/manifest.json",
            PROJECT_ROOT / "warehouse/semantic/metrics.yml",
            PROJECT_ROOT / "warehouse/semantic/glossary.yml",
            PROJECT_ROOT / "warehouse/target/catalog.json",
        )

        self.sqlite_catalog_cache: dict[str, Catalog] = {}

        self.prompt_template = Template(
            PROMPT_PATH.read_text(encoding="utf-8"),
        )

        self.repair_template = Template(
            REPAIR_PROMPT_PATH.read_text(encoding="utf-8"),
        )

        self.answer_synthesizer = AnswerSynthesizer(
            self.client
        )

        self.retrieval = RetrievalService()
        self.context_assembler = SchemaContextAssembler(
            catalog=self.catalog,
        )
        self._last_context = None
        self._last_context = None
        self._last_metrics_context = None
        self._last_glossary_context = None
        self._last_table_notes_context = None

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

        catalog = Catalog(
            manifest=Manifest(relations=relations),
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
    ) -> tuple[str, dict[str, Any]]:
        """Retrieve schema context and generate SQL."""
        source = db_context.get("source")

        if source == "sqlite":
            sql_dialect = "SQLite"
        elif source == "postgres":
            sql_dialect = "PostgreSQL"
        else:
            raise ValueError(f"Unsupported evaluation source: {source!r}")

        if source == "sqlite":
            database_path = db_context.get(
                "database_path"
            )

            if not isinstance(database_path, Path):
                raise ValueError(
                    "SQLite evaluation requires a valid database_path."
                )

            sqlite_catalog = self._load_sqlite_catalog(
                database_path
            )

            schema_context = _render_sqlite_schema(
                sqlite_catalog
            )

            metrics = []
            metrics_context = ""
            glossary_context = ""
            table_notes_context = ""

            response = None

        else:
            response = self.retrieval.retrieve(
                question,
                mode="hybrid",
                limit=20,
            )

            metrics = self.context_assembler.select_metrics(
                question,
                self.catalog.metrics,
            )

            context = self.context_assembler.assemble(
                response.results,
                required_tables=[
                    table
                    for metric in metrics
                    for table in metric.tables
                ],
            )

            schema_context = context.schema

            metrics_context = (
                self.context_assembler._format_metrics(
                    metrics
                )
            )

            tables_in_context = (
                self.context_assembler.tables_from_card_ids(
                    context.card_ids
                )
            )

            glossary_context = (
                self.context_assembler._format_glossary(
                    question,
                    tables_in_context,
                )
            )

            table_notes_context = (
                self.context_assembler._format_table_notes(
                    tables_in_context
                )
            )
        
        self._last_context = (
            context
            if source == "postgres"
            else None
        )
        self._last_metrics_context = metrics_context
        self._last_glossary_context = glossary_context
        self._last_table_notes_context = table_notes_context
        prompt = self.prompt_template.render(
            schema_context=schema_context,
            metrics_context=metrics_context,
            glossary_context=glossary_context,
            table_notes_context=table_notes_context,
            question=question,
            sql_dialect=sql_dialect,
        )

        llm_response = self.loop.run_until_complete(
            self.client.complete(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_output_tokens,
            ),
        )

        top_rrf_score: float | None = None
        reranker_margin: float | None = None

        if response is not None and response.results:
            rrf_score = response.results[0].metadata.get(
                "rrf_score"
            )

            if isinstance(rrf_score, (int, float)):
                top_rrf_score = float(rrf_score)

        if (
            response is not None
            and len(response.results) >= 2
        ):
            reranker_margin = float(
                response.results[0].score
                - response.results[1].score
            )

        metadata = {
            "tokens_in": llm_response.tokens_in,
            "tokens_out": llm_response.tokens_out,
            "latency_ms": llm_response.latency_ms,
            "prompt_hash": self.prompt_hash,
            "llm_attempts": llm_response.attempts,
            "llm_retried": llm_response.retried,
            "retrieval_mode": "hybrid",
            "retrieved_card_count": (
                len(response.results)
                if response is not None
                else 0
            ),
            "context_card_count": (
                len(context.card_ids)
                if source == "postgres"
                else len(
                    self._load_sqlite_catalog(
                        db_context["database_path"]
                    ).manifest.relations
                )
            ),
            "context_token_count": (
                context.token_count
                if source == "postgres"
                else 0
            ),
            "retrieved_card_ids": (
                [
                    result.card_id
                    for result in response.results
                ]
                if response is not None
                else []
            ),
            "selected_metrics": metrics,
            "top_rrf_score": top_rrf_score,
            "reranker_margin": reranker_margin,
        }

        return parse_sql_response(llm_response.text), metadata

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
        """Repair SQL using the existing Phase 5 repair prompt."""
        if self._last_context is None:
            raise RuntimeError(
                "Repair requested before retrieval context was generated.",
            )

        schema_context = self._last_context.schema
        metrics_context = self._last_metrics_context
        glossary_context = self._last_glossary_context
        table_notes_context = self._last_table_notes_context

        source = db_context.get("source")

        if source == "sqlite":
            sql_dialect = "SQLite"
        elif source == "postgres":
            sql_dialect = "PostgreSQL"
        else:
            raise ValueError(f"Unsupported evaluation source: {source!r}")

        prompt = self.repair_template.render(
            schema_dump=schema_context,
            metrics_context=metrics_context,
            glossary_context=glossary_context,
            table_notes_context=table_notes_context,
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
        """Generate retrieval-aware SQL and repair failures."""

        generated_sql, metadata = self._generate_sql(
            question,
            db_context,
        )

        try:
            metadata["agreement_rate"] = (
                self._compute_self_consistency(
                    question,
                    db_context,
                )
            )
        except Exception:
            metadata["agreement_rate"] = 0.0

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
                metrics=metadata.get("selected_metrics", []),
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
            _cost_budget: float,
        ) -> str:
            return self._repair_sql(
                repair_question,
                failed_sql,
                failure_class,
                error_message,
                candidates,
                _cost_budget,
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

        metadata["guardrail_failures"] = sum(
            1
            for attempt in result.attempts
            if attempt.failure_class is not None
        )

        if result.succeeded:
            metadata["degraded"] = len(result.attempts) > 1

            metadata["estimated_query_cost"] = (
                self._estimate_query_cost(
                    result.sql or "",
                    db_context,
                )
            )

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

            # Query never reached a successful final execution,
            # so we do not have a trustworthy final cost.
            metadata["estimated_query_cost"] = None

            return final_attempt.sql, metadata

        metadata["error"] = "Repair loop produced no attempts."
        metadata["estimated_query_cost"] = None

        return generated_sql, metadata

    async def _generate_consistency_candidate(
        self,
        question: str,
        db_context: dict[str, Any],
    ) -> str:
        """Generate one stochastic SQL candidate for self-consistency."""

        source = db_context.get("source")

        if source == "sqlite":
            sql_dialect = "SQLite"
        elif source == "postgres":
            sql_dialect = "PostgreSQL"
        else:
            raise ValueError(
                f"Unsupported evaluation source: {source!r}"
            )

        response = self.retrieval.retrieve(
            question,
            mode="hybrid",
            limit=20,
        )

        metrics = (
            self.context_assembler.select_metrics(
                question,
                self.catalog.metrics,
            )
            if source == "postgres"
            else []
        )

        context = self.context_assembler.assemble(
            response.results,
            required_tables=[
                table
                for metric in metrics
                for table in metric.tables
            ],
        )

        metrics_context = self.context_assembler._format_metrics(
            metrics
        )

        tables_in_context = (
            self.context_assembler.tables_from_card_ids(
                context.card_ids
            )
        )

        glossary_context = (
            self.context_assembler._format_glossary(
                question,
                tables_in_context,
            )
        )

        table_notes_context = (
            self.context_assembler._format_table_notes(
                tables_in_context
            )
        )

        prompt = self.prompt_template.render(
            schema_context=context.schema,
            metrics_context=metrics_context,
            glossary_context=glossary_context,
            table_notes_context=table_notes_context,
            question=question,
            sql_dialect=sql_dialect,
        )

        response = await self.client.complete(
            prompt,
            temperature=0.7,
            max_tokens=self.max_output_tokens,
        )

        return parse_sql_response(response.text)

    async def _execute_consistency_candidate(
        self,
        sql: str,
        db_context: dict[str, Any],
    ) -> list[tuple[Any, ...]]:
        """Execute one self-consistency SQL candidate."""

        source = db_context.get("source")

        if source == "sqlite":
            database_path = db_context.get(
                "database_path"
            )

            if not isinstance(database_path, Path):
                raise ValueError(
                    "SQLite evaluation requires a valid database_path."
                )

            def execute_sqlite():
                with sqlite3.connect(
                    database_path
                ) as connection:
                    return connection.execute(
                        sql
                    ).fetchall()

            import asyncio

            return await asyncio.to_thread(
                execute_sqlite
            )

        if source == "postgres":
            import asyncio

            import psycopg

            from cardinal.config import get_settings

            settings = get_settings()

            def execute_postgres():
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
                    return cursor.fetchall()

            return await asyncio.to_thread(
                execute_postgres
            )

        raise ValueError(
            f"Unsupported evaluation source: {source!r}"
        )


    def _compute_self_consistency(
        self,
        question: str,
        db_context: dict[str, Any],
    ) -> float:
        """Compute five-sample execution agreement."""

        async def generate_candidate() -> str:
            return await self._generate_consistency_candidate(
                question,
                db_context,
            )

        async def execute_candidate(
            sql: str,
        ) -> list[tuple[Any, ...]]:
            return await self._execute_consistency_candidate(
                sql,
                db_context,
            )

        result = self.loop.run_until_complete(
            run_self_consistency(
                generate_candidate,
                execute_candidate,
                sample_count=5,
            )
        )

        return result.agreement_rate

    def _estimate_query_cost(
        self,
        sql: str,
        db_context: dict[str, Any],
    ) -> float | None:
        """Return PostgreSQL EXPLAIN total cost when available."""

        if db_context.get("source") != "postgres":
            return None

        import psycopg

        from cardinal.config import get_settings

        settings = get_settings()

        try:
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
                cursor.execute(
                    f"EXPLAIN (FORMAT JSON) {sql}"
                )

                row = cursor.fetchone()

                if not row:
                    return None

                plan_payload = row[0]

                plan = (
                    plan_payload[0]
                    if isinstance(plan_payload, list)
                    else plan_payload
                )

                return float(
                    plan["Plan"]["Total Cost"]
                )

        except Exception:
            return None

    def close(self) -> None:
        """Close retrieval resources and the inherited LLM client."""
        super().close()

def _render_sqlite_schema(
    catalog: Catalog,
) -> str:
    """Render the full SQLite schema for BIRD generation."""

    lines: list[str] = []

    for relation in sorted(
        catalog.manifest.relations.values(),
        key=lambda item: item.name.lower(),
    ):
        lines.append(
            f"TABLE: {relation.name}"
        )

        for column in sorted(
            relation.columns.values(),
            key=lambda item: item.name.lower(),
        ):
            data_type = (
                f" ({column.data_type})"
                if column.data_type
                else ""
            )

            lines.append(
                f"  - {column.name}{data_type}"
            )

        lines.append("")

    return "\n".join(lines).strip()