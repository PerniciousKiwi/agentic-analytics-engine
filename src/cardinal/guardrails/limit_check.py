from __future__ import annotations

import sqlglot
from sqlglot import exp

from cardinal.guardrails.ast_checks import GuardResult


def _apply_limit(expression: exp.Expression, limit: int) -> bool:
    existing_limit = expression.args.get("limit")

    if existing_limit is None:
        expression.set(
            "limit",
            exp.Limit(expression=exp.Literal.number(limit)),
        )
        return True

    existing_value = existing_limit.expression

    if isinstance(existing_value, exp.Literal) and existing_value.is_int:
        requested_limit = int(existing_value.this)

        if requested_limit > limit:
            expression.set(
                "limit",
                exp.Limit(
                    expression=exp.Literal.number(limit),
                ),
            )

    return True


def enforce_limit(sql: str, limit: int) -> tuple[str, GuardResult]:
    try:
        expression = sqlglot.parse_one(sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        return sql, GuardResult(
            allowed=False,
            reasons=[f"SQL_PARSE_ERROR: {exc}"],
        )

    if isinstance(expression, exp.Select):
        _apply_limit(expression, limit)
        return expression.sql(dialect="postgres"), GuardResult(allowed=True)

    if isinstance(expression, exp.Union):
        _apply_limit(expression, limit)
        return expression.sql(dialect="postgres"), GuardResult(allowed=True)

    return sql, GuardResult(
        allowed=False,
        reasons=["READ_ONLY_VIOLATION"],
    )
