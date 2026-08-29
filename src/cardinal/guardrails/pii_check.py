from __future__ import annotations

import sqlglot
from sqlglot import exp

from cardinal.catalog.catalog import Catalog
from cardinal.guardrails.ast_checks import GuardResult


def check_pii(
    sql: str,
    catalog: Catalog,
    role: str = "analyst",
) -> GuardResult:
    if role == "privileged":
        return GuardResult(allowed=True)

    try:
        expression = sqlglot.parse_one(sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        return GuardResult(
            allowed=False,
            reasons=[f"SQL_PARSE_ERROR: {exc}"],
        )

    pii_columns = {column.lower() for column in catalog.glossary.pii_columns}
    pii_names = {column.split(".")[-1] for column in pii_columns}

    reasons: list[str] = []

    for column in expression.find_all(exp.Column):
        column_name = column.name.lower()

        if column_name not in pii_names:
            continue

        # PII may be used internally to establish table relationships.
        # It must not be exposed or used elsewhere in the query.
        if column.find_ancestor(exp.Join):
            continue

        reasons.append(f"PII_COLUMN_FORBIDDEN: {column.name}")

    return GuardResult(
        allowed=not reasons,
        reasons=sorted(set(reasons)),
    )
