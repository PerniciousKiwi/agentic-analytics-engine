from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from difflib import get_close_matches
from enum import StrEnum
from typing import Any

import sqlglot
from sqlglot import exp

from cardinal.catalog.catalog import Catalog
from cardinal.guardrails.ast_checks import GuardResult
from cardinal.guardrails.pipeline import GuardrailResult


class FailureClass(StrEnum):
    UNKNOWN_COLUMN = "UNKNOWN_COLUMN"
    UNKNOWN_TABLE = "UNKNOWN_TABLE"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    AMBIGUOUS_COLUMN = "AMBIGUOUS_COLUMN"
    SYNTAX = "SYNTAX"
    TIMEOUT = "TIMEOUT"
    AGGREGATION_ERROR = "AGGREGATION_ERROR"
    OTHER = "OTHER"


_GUARD_FAILURE_MAP: dict[str, FailureClass] = {
    "UNKNOWN_COLUMN": FailureClass.UNKNOWN_COLUMN,
    "UNKNOWN_TABLE": FailureClass.UNKNOWN_TABLE,
    "AMBIGUOUS_COLUMN": FailureClass.AMBIGUOUS_COLUMN,
    "SQL_PARSE_ERROR": FailureClass.SYNTAX,
    "SUPERLATIVE_MISMATCH": FailureClass.OTHER,
    "MODE_MISMATCH": FailureClass.OTHER,
}


_SQLSTATE_FAILURE_MAP: dict[str, FailureClass] = {
    "42703": FailureClass.UNKNOWN_COLUMN,
    "42P01": FailureClass.UNKNOWN_TABLE,
    "42702": FailureClass.AMBIGUOUS_COLUMN,
    "42601": FailureClass.SYNTAX,
    "42803": FailureClass.AGGREGATION_ERROR,
    "22P02": FailureClass.TYPE_MISMATCH,
    "42804": FailureClass.TYPE_MISMATCH,
    "57014": FailureClass.TIMEOUT,
}


@dataclass
class RepairAttempt:
    attempt_number: int
    sql: str
    failure_class: FailureClass | None
    error_message: str | None


@dataclass
class RepairResult:
    sql: str | None
    succeeded: bool
    attempts: list[RepairAttempt]


def _classify_guard_result(result: GuardResult) -> FailureClass:
    for reason in result.reasons:
        code = reason.split(":", 1)[0].strip().upper()

        failure_class = _GUARD_FAILURE_MAP.get(code)
        if failure_class is not None:
            return failure_class

    return FailureClass.OTHER


def _get_sqlstate(exc: BaseException) -> str | None:
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate:
        return str(sqlstate)

    diag = getattr(exc, "diag", None)
    if diag is not None:
        sqlstate = getattr(diag, "sqlstate", None)
        if sqlstate:
            return str(sqlstate)

    return None


def classify_failure(
    failure: GuardResult | GuardrailResult | BaseException,
) -> FailureClass:
    """Map guardrail results and database exceptions to one failure taxonomy."""
    if isinstance(failure, GuardrailResult):
        return _classify_guard_result(failure.result)

    if isinstance(failure, GuardResult):
        return _classify_guard_result(failure)

    if isinstance(failure, BaseException):
        sqlstate = _get_sqlstate(failure)

        if sqlstate is not None:
            return _SQLSTATE_FAILURE_MAP.get(
                sqlstate,
                FailureClass.OTHER,
            )

        return FailureClass.OTHER

    return FailureClass.OTHER


def identifier_candidates(
    sql: str,
    failure_class: FailureClass,
    identifier: str,
    catalog: Catalog,
    *,
    limit: int = 5,
    cutoff: float = 0.4,
) -> list[str]:
    """Return the closest real catalog identifiers for a failed SQL identifier."""
    if failure_class == FailureClass.UNKNOWN_TABLE:
        candidate_pool = _relation_names(catalog)

        return get_close_matches(
            identifier,
            candidate_pool,
            n=limit,
            cutoff=cutoff,
        )

    if failure_class in {
        FailureClass.UNKNOWN_COLUMN,
        FailureClass.AMBIGUOUS_COLUMN,
    }:
        candidate_pool = _column_candidates(
            sql,
            identifier,
            catalog,
        )

        return get_close_matches(
            identifier.split(".")[-1],
            candidate_pool,
            n=limit,
            cutoff=cutoff,
        )

    return []


def _relation_names(catalog: Catalog) -> list[str]:
    """Return real relation names from the catalog."""
    return sorted(
        {relation.name for relation in catalog.manifest.relations.values()},
        key=str.lower,
    )


def _column_candidates(
    sql: str,
    identifier: str,
    catalog: Catalog,
) -> list[str]:
    """Build a relevant column candidate pool for the SQL statement."""
    try:
        expression = sqlglot.parse_one(sql, read="postgres")
    except sqlglot.errors.ParseError:
        return _all_column_names(catalog)

    table_reference = identifier.split(".", 1)[0] if "." in identifier else None

    relations = _referenced_relations(
        expression,
        catalog,
    )

    if table_reference:
        relation = _resolve_referenced_relation(
            expression,
            table_reference,
            catalog,
        )

        if relation is not None:
            return sorted(
                relation.columns,
                key=str.lower,
            )

        return _qualified_column_names(relations)

    return _qualified_column_names(relations)


def _referenced_relations(
    expression: exp.Expression,
    catalog: Catalog,
) -> list[object]:
    """Return physical catalog relations referenced by the SQL."""
    relations: list[object] = []
    seen: set[int] = set()

    for table in expression.find_all(exp.Table):
        relation = catalog.manifest.get_relation(table.name)

        if relation is None:
            continue

        relation_id = id(relation)

        if relation_id not in seen:
            relations.append(relation)
            seen.add(relation_id)

    return relations


def _resolve_referenced_relation(
    expression: exp.Expression,
    table_reference: str,
    catalog: Catalog,
):
    """Resolve a table reference, including aliases, to a catalog relation."""
    table_reference = table_reference.lower()

    for table in expression.find_all(exp.Table):
        if table.alias_or_name.lower() != table_reference:
            continue

        relation = catalog.manifest.get_relation(table.name)

        if relation is not None:
            return relation

    return catalog.manifest.get_relation(table_reference)


def _qualified_column_names(
    relations: list[object],
) -> list[str]:
    """Return columns qualified with their relation name."""
    candidates: list[str] = []

    for relation in relations:
        candidates.extend(f"{relation.name}.{column_name}" for column_name in relation.columns)

    return sorted(
        set(candidates),
        key=str.lower,
    )


def _all_column_names(
    catalog: Catalog,
) -> list[str]:
    """Return all catalog column names as a fallback."""
    return sorted(
        {
            column_name
            for relation in catalog.manifest.relations.values()
            for column_name in relation.columns
        },
        key=str.lower,
    )


def _normalize_sql(sql: str) -> str:
    """Normalize SQL enough to detect whitespace-only duplicates."""
    return " ".join(sql.lower().split())


def _extract_identifier(
    failure_class: FailureClass,
    error_message: str,
) -> str | None:
    """Extract the failed identifier from a guardrail/DB error message."""
    if failure_class not in {
        FailureClass.UNKNOWN_COLUMN,
        FailureClass.UNKNOWN_TABLE,
        FailureClass.AMBIGUOUS_COLUMN,
    }:
        return None

    if ":" not in error_message:
        return None

    identifier = error_message.split(":", 1)[1].strip()

    if not identifier:
        return None

    return identifier


def _is_policy_failure(error_message: str) -> bool:
    """Return whether a failure should abstain instead of attempting repair."""
    return any(
        code in error_message.upper()
        for code in {
            "PII_VIOLATION",
            "CARTESIAN_JOIN",
            "READ_ONLY_VIOLATION",
        }
    )


GenerateFn = Callable[[str], str]
GuardFn = Callable[[str, Catalog, float], GuardrailResult]
ExecuteFn = Callable[[str], Any]
RepairFn = Callable[
    [str, str, FailureClass, str, list[str], float],
    str,
]


def run_with_repair(
    question: str,
    catalog: Catalog,
    generate_fn: GenerateFn,
    guard_pipeline_fn: GuardFn,
    execute_fn: ExecuteFn,
    repair_fn: RepairFn,
    *,
    max_attempts: int = 3,
    cost_budget: float | None = None,
) -> RepairResult:
    """Generate, guard, execute, repair, and retry SQL."""
    attempts: list[RepairAttempt] = []
    tried_sql: set[str] = set()

    current_sql = generate_fn(question)
    current_budget = cost_budget

    for attempt_number in range(1, max_attempts + 1):
        normalized_sql = _normalize_sql(current_sql)

        if normalized_sql in tried_sql:
            return RepairResult(
                sql=None,
                succeeded=False,
                attempts=attempts,
            )

        tried_sql.add(normalized_sql)

        try:
            guardrail_result = guard_pipeline_fn(
                current_sql,
                catalog,
                current_budget if current_budget is not None else float("inf"),
            )
        except Exception as exc:
            failure_class = classify_failure(exc)
            error_message = str(exc)

            attempts.append(
                RepairAttempt(
                    attempt_number=attempt_number,
                    sql=current_sql,
                    failure_class=failure_class,
                    error_message=error_message,
                )
            )

            if attempt_number >= max_attempts:
                break

            if _is_policy_failure(error_message):
                break

            if failure_class == FailureClass.TIMEOUT and current_budget is not None:
                current_budget /= 2

            identifier = _extract_identifier(
                failure_class,
                error_message,
            )

            candidates = (
                identifier_candidates(
                    current_sql,
                    failure_class,
                    identifier,
                    catalog,
                )
                if identifier
                else []
            )

            current_sql = repair_fn(
                question,
                current_sql,
                failure_class,
                error_message,
                candidates,
                current_budget if current_budget is not None else float("inf"),
            )
            continue

        if not guardrail_result.result.allowed:
            error_message = "; ".join(
                guardrail_result.result.reasons,
            )
            failure_class = classify_failure(guardrail_result)

            attempts.append(
                RepairAttempt(
                    attempt_number=attempt_number,
                    sql=guardrail_result.sql,
                    failure_class=failure_class,
                    error_message=error_message,
                )
            )

            if attempt_number >= max_attempts:
                break

            if _is_policy_failure(error_message):
                break

            identifier = _extract_identifier(
                failure_class,
                error_message,
            )

            candidates = (
                identifier_candidates(
                    guardrail_result.sql,
                    failure_class,
                    identifier,
                    catalog,
                )
                if identifier
                else []
            )

            current_sql = repair_fn(
                question,
                guardrail_result.sql,
                failure_class,
                error_message,
                candidates,
                current_budget if current_budget is not None else float("inf"),
            )
            continue

        current_sql = guardrail_result.sql

        try:
            execute_fn(current_sql)
        except Exception as exc:
            failure_class = classify_failure(exc)
            error_message = str(exc)

            attempts.append(
                RepairAttempt(
                    attempt_number=attempt_number,
                    sql=current_sql,
                    failure_class=failure_class,
                    error_message=error_message,
                )
            )

            if attempt_number >= max_attempts:
                break

            if failure_class == FailureClass.TIMEOUT and current_budget is not None:
                current_budget /= 2

            identifier = _extract_identifier(
                failure_class,
                error_message,
            )

            candidates = (
                identifier_candidates(
                    current_sql,
                    failure_class,
                    identifier,
                    catalog,
                )
                if identifier
                else []
            )

            current_sql = repair_fn(
                question,
                current_sql,
                failure_class,
                error_message,
                candidates,
                current_budget if current_budget is not None else float("inf"),
            )
            continue

        attempts.append(
            RepairAttempt(
                attempt_number=attempt_number,
                sql=current_sql,
                failure_class=None,
                error_message=None,
            )
        )

        return RepairResult(
            sql=current_sql,
            succeeded=True,
            attempts=attempts,
        )

    return RepairResult(
        sql=None,
        succeeded=False,
        attempts=attempts,
    )
