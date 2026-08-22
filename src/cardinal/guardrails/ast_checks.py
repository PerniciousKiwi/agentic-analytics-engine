from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp


@dataclass
class GuardResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def check_read_only(sql: str) -> GuardResult:
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        return GuardResult(
            allowed=False,
            reasons=[f"SQL_PARSE_ERROR: {exc}"],
        )

    if not statements:
        return GuardResult(
            allowed=False,
            reasons=["EMPTY_SQL"],
        )

    if len(statements) > 1:
        return GuardResult(
            allowed=False,
            reasons=["READ_ONLY_VIOLATION: MULTI_STATEMENT"],
        )

    reasons: list[str] = []

    forbidden = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.TruncateTable,
        exp.Merge,
    )

    for statement in statements:
        for node in statement.walk():
            if isinstance(node, forbidden):
                reasons.append(
                    f"READ_ONLY_VIOLATION: {node.key.upper()}",
                )

    return GuardResult(
        allowed=not reasons,
        reasons=sorted(set(reasons)),
    )
