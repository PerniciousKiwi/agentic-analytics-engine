from __future__ import annotations

import re
import time
from functools import lru_cache
from pathlib import Path

from cardinal.agent.repair import (
    FailureClass,
    classify_failure,
    identifier_candidates,
)
from cardinal.agent.schemas import (
    ExecuteSqlIn,
    ExecuteSqlOut,
    SchemaCardSummary,
    SearchSchemaIn,
    SearchSchemaOut,
    ToolError,
)
from cardinal.catalog.catalog import Catalog
from cardinal.db.reader import WarehouseReader
from cardinal.guardrails.pipeline import run_guardrails
from cardinal.retrieval.context import SchemaContextAssembler
from cardinal.retrieval.models import RetrievalResult
from cardinal.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@lru_cache
def _get_catalog() -> Catalog:
    """Load the production warehouse catalog once."""
    return Catalog.load(
        PROJECT_ROOT / "warehouse/target/manifest.json",
        PROJECT_ROOT / "warehouse/semantic/metrics.yml",
        PROJECT_ROOT / "warehouse/semantic/glossary.yml",
        PROJECT_ROOT / "warehouse/target/catalog.json",
    )


@lru_cache
def _get_retrieval_service() -> RetrievalService:
    """Create and cache the existing Phase 6 retrieval service."""
    return RetrievalService()


@lru_cache
def _get_context_assembler() -> SchemaContextAssembler:
    """Create the existing Phase 6 pruning/context assembler."""
    return SchemaContextAssembler(
        catalog=_get_catalog(),
    )


def search_schema(request: SearchSchemaIn) -> SearchSchemaOut:
    """Retrieve and prune schema cards for agent consumption.

    No raw exception is allowed to escape this tool boundary.
    """
    try:
        retrieval = _get_retrieval_service()
        assembler = _get_context_assembler()

        response = retrieval.retrieve(
            request.query,
            mode="hybrid",
            limit=20,
        )

        results = response.results

        if request.domain is not None:
            requested_domain = request.domain.strip().lower()

            results = [
                result
                for result in results
                if result.domain.lower() == requested_domain
            ]

        context = assembler.assemble(results)

        selected_ids = set(context.card_ids)

        selected_results = [
            result
            for result in results
            if result.card_id in selected_ids
        ]

        cards = [
            _schema_card_summary(result)
            for result in selected_results
        ]

        top_rrf_score = None
        top_reranker_score = None
        reranker_margin = None

        if selected_results:
            top_result = selected_results[0]

            rrf_score = top_result.metadata.get("rrf_score")
            if isinstance(rrf_score, (int, float)):
                top_rrf_score = float(rrf_score)

            top_reranker_score = float(top_result.score)

            if len(selected_results) >= 2:
                reranker_margin = float(
                    selected_results[0].score
                    - selected_results[1].score
                )

        return SearchSchemaOut(
            cards=cards,
            top_rrf_score=top_rrf_score,
            top_reranker_score=top_reranker_score,
            reranker_margin=reranker_margin,
        )

    except Exception as exc:
        return SearchSchemaOut(
            cards=[],
            error=ToolError(
                message=str(exc),
                failure_class=FailureClass.OTHER,
            ),
        )


def execute_sql(request: ExecuteSqlIn) -> ExecuteSqlOut:
    """Guard and execute SQL through the read-only warehouse boundary.

    Guardrails are enforced before database execution. Guardrail and database
    failures are normalized into the Phase 5 failure taxonomy and enriched
    with identifier candidates where possible.

    No raw exception is allowed to escape this tool boundary.
    """
    started = time.perf_counter()

    try:
        catalog = _get_catalog()

        guarded = run_guardrails(
            request.sql,
            catalog,
            metrics=catalog.metrics,
            role="analyst",
            max_rows=request.row_limit + 1,
            enforce_result_limit=True,
        )

        if not guarded.result.allowed:
            message = "; ".join(guarded.result.reasons)
            failure_class = classify_failure(guarded)

            candidates = _failure_candidates(
                guarded.sql,
                failure_class,
                message,
                catalog,
            )

            return _sql_error(
                started=started,
                failure_class=failure_class,
                message=message,
                candidates=candidates,
            )

        try:
            with WarehouseReader() as reader:
                raw_rows = reader.fetch_all(guarded.sql)

        except Exception as exc:
            failure_class = classify_failure(exc)
            message = str(exc)

            candidates = _failure_candidates(
                guarded.sql,
                failure_class,
                message,
                catalog,
            )

            return _sql_error(
                started=started,
                failure_class=failure_class,
                message=message,
                candidates=candidates,
            )

        truncated = len(raw_rows) > request.row_limit

        visible_rows = raw_rows[: request.row_limit]

        columns = (
            list(visible_rows[0].keys())
            if visible_rows
            else []
        )

        rows = [
            [row.get(column) for column in columns]
            for row in visible_rows
        ]

        return ExecuteSqlOut(
            columns=columns,
            rows=rows,
            row_count=len(visible_rows),
            truncated=truncated,
            elapsed_ms=_elapsed_ms(started),
        )

    except Exception as exc:
        return _sql_error(
            started=started,
            failure_class=FailureClass.OTHER,
            message=str(exc),
            candidates=[],
        )


def _schema_card_summary(
    result: RetrievalResult,
) -> SchemaCardSummary:
    """Convert an internal retrieval result to agent-facing structured data."""
    metadata = result.metadata

    description = (
        _optional_string(metadata.get("card_description"))
        or _optional_string(metadata.get("description"))
        or _optional_string(metadata.get("definition"))
        or _description_from_text(result)
    )

    data_type = (
        _optional_string(metadata.get("data_type"))
        or _data_type_from_text(result.card_text)
    )

    return SchemaCardSummary(
        card_type=result.card_type,
        domain=result.domain,
        name=result.card_name,
        description=description,
        data_type=data_type,
    )


def _description_from_text(
    result: RetrievalResult,
) -> str:
    """Extract the card description without exposing sample values."""
    lines = result.card_text.splitlines()

    # SchemaCard.to_text() implementations always place the description
    # on the third rendered line:
    #
    # TABLE/COLUMN/METRIC
    # DOMAIN
    # DESCRIPTION
    #
    # Preserve blank lines here. Removing them would cause column lists,
    # sample values, or other metadata to be mistaken for descriptions.
    if len(lines) >= 3:
        description = lines[2].strip()

        if description:
            return description

    if result.card_type == "metric":
        for line in lines:
            stripped = line.strip()

            if stripped.upper().startswith("DEFINITION:"):
                return stripped.split(":", 1)[1].strip()

    return ""


def _data_type_from_text(card_text: str) -> str | None:
    """Extract column data type from a rendered schema card."""
    for line in card_text.splitlines():
        stripped = line.strip()

        if stripped.upper().startswith("DATA TYPE:"):
            value = stripped.split(":", 1)[1].strip()
            return value or None

    return None


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _failure_candidates(
    sql: str,
    failure_class: FailureClass,
    message: str,
    catalog: Catalog,
) -> list[str]:
    """Attach edit-distance identifier candidates for relevant failures."""
    identifier = _extract_failed_identifier(
        failure_class,
        message,
    )

    if identifier is None:
        return []

    return identifier_candidates(
        sql,
        failure_class,
        identifier,
        catalog,
    )


def _extract_failed_identifier(
    failure_class: FailureClass,
    message: str,
) -> str | None:
    """Extract an identifier from guardrail or PostgreSQL error text."""
    if failure_class not in {
        FailureClass.UNKNOWN_COLUMN,
        FailureClass.UNKNOWN_TABLE,
        FailureClass.AMBIGUOUS_COLUMN,
    }:
        return None

    guardrail_prefixes = {
        FailureClass.UNKNOWN_COLUMN: "UNKNOWN_COLUMN:",
        FailureClass.UNKNOWN_TABLE: "UNKNOWN_TABLE:",
        FailureClass.AMBIGUOUS_COLUMN: "AMBIGUOUS_COLUMN:",
    }

    prefix = guardrail_prefixes[failure_class]

    for part in message.split(";"):
        stripped = part.strip()

        if stripped.upper().startswith(prefix):
            identifier = stripped.split(":", 1)[1].strip()

            if identifier:
                return identifier

    patterns = {
        FailureClass.UNKNOWN_COLUMN: (
            r'column ["\']?([^"\']+)["\']? does not exist'
        ),
        FailureClass.UNKNOWN_TABLE: (
            r'relation ["\']?([^"\']+)["\']? does not exist'
        ),
        FailureClass.AMBIGUOUS_COLUMN: (
            r'column reference ["\']?([^"\']+)["\']? is ambiguous'
        ),
    }

    match = re.search(
        patterns[failure_class],
        message,
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    return match.group(1).strip()


def _sql_error(
    *,
    started: float,
    failure_class: FailureClass,
    message: str,
    candidates: list[str],
) -> ExecuteSqlOut:
    return ExecuteSqlOut(
        columns=[],
        rows=[],
        row_count=0,
        truncated=False,
        elapsed_ms=_elapsed_ms(started),
        error=ToolError(
            message=message,
            failure_class=failure_class,
            candidates=candidates,
        ),
    )


def _elapsed_ms(started: float) -> int:
    return max(
        0,
        round((time.perf_counter() - started) * 1000),
    )