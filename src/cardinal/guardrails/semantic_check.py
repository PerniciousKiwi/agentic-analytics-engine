from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from cardinal.catalog.models import Metric
from cardinal.guardrails.ast_checks import GuardResult

_SUPERLATIVE_PATTERNS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("fastest", "quickest"), "ASC", "minimum"),
    (("slowest",), "DESC", "maximum"),
    (("highest", "largest", "greatest"), "DESC", "maximum"),
    (("lowest", "smallest"), "ASC", "minimum"),
    (("earliest",), "ASC", "minimum"),
    (("latest", "most recent"), "DESC", "maximum"),
)

_MODE_STRICT_PHRASES: tuple[str, ...] = (
    "most common",
    "most frequent",
)

_MODE_AMBIGUOUS_PHRASES: tuple[str, ...] = (
    "most popular",
    "most typical",
)

_MAXIMUM_PHRASES: tuple[str, ...] = (
    "maximum",
    "highest",
    "largest",
    "greatest",
    "maximum value",
)


def _detect_superlative(question: str) -> tuple[str, str] | None:
    """Return expected ordering and semantic direction for high-confidence terms."""
    normalized = question.lower()

    for terms, expected_direction, semantic_direction in _SUPERLATIVE_PATTERNS:
        for term in terms:
            if re.search(
                rf"\b{re.escape(term)}\b",
                normalized,
            ):
                return expected_direction, semantic_direction

    return None


def _has_limit(expression: exp.Expression) -> bool:
    """Return whether the query contains a LIMIT clause."""
    return expression.find(exp.Limit) is not None


def _order_directions(expression: exp.Expression) -> list[str]:
    """Return ORDER BY directions in query order."""
    directions: list[str] = []

    for ordered in expression.find_all(exp.Ordered):
        descending = ordered.args.get("desc")

        if descending is True:
            directions.append("DESC")
        else:
            directions.append("ASC")

    return directions


def _has_group_by_count(expression: exp.Expression) -> bool:
    """Return whether SQL groups rows and counts them."""
    has_group_by = expression.args.get("group") is not None
    has_count = any(isinstance(node, exp.Count) for node in expression.walk())

    return has_group_by and has_count


def _has_superlative_shape(expression: exp.Expression) -> bool:
    """Return whether SQL uses an explicit superlative shape."""
    has_order_limit = (
        expression.args.get("limit") is not None
        and expression.args.get("order") is not None
    )

    has_max_min = any(
        isinstance(node, exp.Max | exp.Min)
        for node in expression.walk()
    )

    return has_order_limit or has_max_min


def check_superlative(
    sql: str,
    question: str | None,
) -> GuardResult:
    """Check high-confidence superlative wording against SQL ordering."""
    if not question:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    detected = _detect_superlative(question)

    if detected is None:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    expected_direction, semantic_direction = detected

    try:
        expression = sqlglot.parse_one(
            sql,
            read="postgres",
        )
    except sqlglot.errors.ParseError:
        # Syntax validation is handled by the existing catalog/SQL
        # validation path. This check should not duplicate it.
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    order_directions = _order_directions(expression)

    if not order_directions:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    if expected_direction not in order_directions:
        return GuardResult(
            allowed=False,
            reasons=[
                "SUPERLATIVE_MISMATCH: "
                f"question implies a {semantic_direction} result, "
                f"but SQL orders {order_directions[-1]}",
            ],
        )

    if not _has_limit(expression):
        return GuardResult(
            allowed=False,
            reasons=[
                "SUPERLATIVE_MISMATCH: "
                f"question asks for a {semantic_direction} result, "
                "but SQL does not limit the ordered result",
            ],
        )

    return GuardResult(
        allowed=True,
        reasons=[],
    )


def check_mode_question_shape(
    sql: str,
    question: str | None,
) -> GuardResult:
    """Check mode-like wording against an appropriate SQL shape."""
    if not question:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    normalized = question.lower()

    try:
        expression = sqlglot.parse_one(
            sql,
            read="postgres",
        )
    except sqlglot.errors.ParseError:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    is_strict_mode = any(
        re.search(
            rf"\b{re.escape(phrase)}\b",
            normalized,
        )
        for phrase in _MODE_STRICT_PHRASES
    )

    is_ambiguous_mode = any(
        re.search(
            rf"\b{re.escape(phrase)}\b",
            normalized,
        )
        for phrase in _MODE_AMBIGUOUS_PHRASES
    )

    if not is_strict_mode and not is_ambiguous_mode:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    has_group_by_count = _has_group_by_count(expression)

    if is_strict_mode and not has_group_by_count:
        return GuardResult(
            allowed=False,
            reasons=[
                "MODE_MISMATCH: "
                "'most common/frequent' requires computing "
                "a frequency with GROUP BY + COUNT",
            ],
        )

    if is_ambiguous_mode and not (
        has_group_by_count or _has_superlative_shape(expression)
    ):
        return GuardResult(
            allowed=False,
            reasons=[
                "SEMANTIC_SHAPE_MISMATCH: "
                "expected either GROUP BY + COUNT "
                "or a MAX/superlative pattern",
            ],
        )

    has_maximum_requirement = any(
        re.search(
            rf"\b{re.escape(phrase)}\b",
            normalized,
        )
        for phrase in _MAXIMUM_PHRASES
    )

    if has_maximum_requirement and expression.find(exp.Max) is None:
        return GuardResult(
            allowed=False,
            reasons=[
                "MODE_MISMATCH: "
                "question combines a mode with a maximum requirement, "
                "but SQL does not preserve the MAX() condition",
            ],
        )

    return GuardResult(
        allowed=True,
        reasons=[],
    )


def _unwrap_parens(expression: exp.Expression) -> exp.Expression:
    """Remove insignificant parentheses from a SQL expression."""
    while isinstance(expression, exp.Paren):
        expression = expression.this

    return expression


def check_canonical_metric(
    sql: str,
    metrics: list[Metric],
) -> GuardResult:
    """Ensure a uniquely selected canonical metric is not transformed."""
    if len(metrics) != 1:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    metric = metrics[0]

    try:
        expression = sqlglot.parse_one(
            sql,
            read="postgres",
        )
        canonical = sqlglot.parse_one(
            metric.sql,
            read="postgres",
        )
    except sqlglot.errors.ParseError:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    select_expressions = expression.expressions

    if len(select_expressions) != 1:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    generated = select_expressions[0]

    if isinstance(generated, exp.Alias):
        generated = generated.this

    # Parentheses around the canonical metric are semantically
    # insignificant, so normalize them before comparing ASTs.
    generated = _unwrap_parens(generated)
    canonical = _unwrap_parens(canonical)

    if generated == canonical:
        return GuardResult(
            allowed=True,
            reasons=[],
        )

    # Reject transformations such as:
    #
    #     canonical_metric * 100
    #
    # while still allowing harmless parentheses around the canonical
    # expression.
    if isinstance(generated, exp.Mul):
        left = _unwrap_parens(generated.this)
        right = _unwrap_parens(generated.expression)

        if right.is_number and left == canonical:
            return GuardResult(
                allowed=False,
                reasons=[
                    "CANONICAL_METRIC_MISMATCH: "
                    f"metric {metric.name!r} was transformed "
                    "instead of using its canonical calculation exactly",
                ],
            )

    return GuardResult(
        allowed=True,
        reasons=[],
    )