from __future__ import annotations

from dataclasses import dataclass

from cardinal.catalog.catalog import Catalog
from cardinal.guardrails.ast_checks import GuardResult, check_read_only
from cardinal.guardrails.catalog_check import check_catalog
from cardinal.guardrails.join_check import check_cartesian_join
from cardinal.guardrails.limit_check import enforce_limit
from cardinal.guardrails.pii_check import check_pii


@dataclass
class GuardrailResult:
    sql: str
    result: GuardResult


def run_guardrails(
    sql: str,
    catalog: Catalog,
    *,
    role: str = "analyst",
    max_rows: int = 1000,
) -> GuardrailResult:
    """Run Phase 4 guardrails in their required order."""

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

    sql, result = enforce_limit(sql, max_rows)

    return GuardrailResult(sql=sql, result=result)
