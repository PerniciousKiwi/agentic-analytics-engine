from __future__ import annotations

from dataclasses import dataclass

from cardinal.catalog.catalog import Catalog
from cardinal.catalog.models import Metric
from cardinal.guardrails.ast_checks import GuardResult, check_read_only
from cardinal.guardrails.catalog_check import check_catalog
from cardinal.guardrails.join_check import check_cartesian_join
from cardinal.guardrails.limit_check import enforce_limit
from cardinal.guardrails.pii_check import check_pii
from cardinal.guardrails.semantic_check import (
    check_canonical_metric,
    check_mode_question_shape,
    check_superlative,
)


@dataclass
class GuardrailResult:
    sql: str
    result: GuardResult


def run_guardrails(
    sql: str,
    catalog: Catalog,
    *,
    question: str | None = None,
    metrics: list[Metric] | None = None,
    role: str = "analyst",
    max_rows: int = 1000,
    enforce_result_limit: bool = True,
) -> GuardrailResult:
    """Run Phase 4 guardrails plus semantic checks."""

    result = check_read_only(sql)
    if not result.allowed:
        return GuardrailResult(sql=sql, result=result)

    result = check_catalog(sql, catalog)
    if not result.allowed:
        return GuardrailResult(sql=sql, result=result)

    result = check_cartesian_join(sql)
    if not result.allowed:
        return GuardrailResult(sql=sql, result=result)

    result = check_pii(sql, catalog, role=role)
    if not result.allowed:
        return GuardrailResult(sql=sql, result=result)

    result = check_superlative(sql, question)
    if not result.allowed:
        return GuardrailResult(sql=sql, result=result)

    result = check_mode_question_shape(sql, question)
    if not result.allowed:
        return GuardrailResult(sql=sql, result=result)

    result = check_canonical_metric(
        sql,
        metrics or [],
    )
    if not result.allowed:
        return GuardrailResult(sql=sql, result=result)

    if enforce_result_limit:
        sql, result = enforce_limit(sql, max_rows)

    return GuardrailResult(
        sql=sql,
        result=GuardResult(
            allowed=True,
            reasons=[],
        ),
    )
