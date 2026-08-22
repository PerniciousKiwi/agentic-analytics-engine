from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from cardinal.guardrails.ast_checks import GuardResult


def check_cartesian_join(
    sql: str,
    allow_cartesian: bool = False,
) -> GuardResult:
    try:
        expression = sqlglot.parse_one(sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        return GuardResult(
            allowed=False,
            reasons=[f"SQL_PARSE_ERROR: {exc}"],
        )

    if allow_cartesian:
        return GuardResult(allowed=True)

    reasons: list[str] = []

    normalized_sql = " ".join(sql.upper().split())

    if "CROSS JOIN" in normalized_sql:
        reasons.append("CARTESIAN_JOIN: CROSS JOIN")

    explicit_join = re.search(
        r"\b(?:INNER|LEFT|RIGHT|FULL|OUTER)?\s*JOIN\b",
        sql,
        flags=re.IGNORECASE,
    )

    for join in expression.find_all(exp.Join):
        has_condition = join.args.get("on") is not None or join.args.get("using") is not None

        if explicit_join and not has_condition:
            reasons.append("CARTESIAN_JOIN: JOIN WITHOUT CONDITION")

    # SQLGlot represents comma-separated FROM items as Join nodes.
    # A comma join is safe only when the WHERE predicate actually
    # correlates columns belonging to different relations.
    if not explicit_join:
        joins = list(expression.find_all(exp.Join))

        if joins:
            where = expression.args.get("where")

            if where is None:
                reasons.append(
                    "CARTESIAN_JOIN: COMMA JOIN WITHOUT CONDITION",
                )
            else:
                tables = {table.alias_or_name.lower() for table in expression.find_all(exp.Table)}

                correlated = False

                for predicate in where.find_all(exp.Predicate):
                    columns = list(predicate.find_all(exp.Column))
                    referenced_tables = {column.table.lower() for column in columns if column.table}

                    if len(referenced_tables & tables) >= 2:
                        correlated = True
                        break

                if not correlated:
                    reasons.append(
                        "CARTESIAN_JOIN: COMMA JOIN WITHOUT CORRELATION",
                    )

    return GuardResult(
        allowed=not reasons,
        reasons=sorted(set(reasons)),
    )
