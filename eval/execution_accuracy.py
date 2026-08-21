from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Real
from typing import Any


def _values_equal(
    gold_value: Any,
    predicted_value: Any,
    float_tol: float,
) -> bool:
    """Compare two SQL result values using evaluation semantics."""
    if gold_value is None or predicted_value is None:
        return gold_value is None and predicted_value is None

    if isinstance(gold_value, Real) and isinstance(predicted_value, Real):
        if isinstance(gold_value, bool) or isinstance(predicted_value, bool):
            return gold_value == predicted_value

        return math.isclose(
            float(gold_value),
            float(predicted_value),
            rel_tol=float_tol,
            abs_tol=float_tol,
        )

    return gold_value == predicted_value


def _rows_equal(
    gold_row: Sequence[Any],
    predicted_row: Sequence[Any],
    float_tol: float,
) -> bool:
    """Compare two rows positionally."""
    if len(gold_row) != len(predicted_row):
        return False

    return all(
        _values_equal(gold_value, predicted_value, float_tol)
        for gold_value, predicted_value in zip(
            gold_row,
            predicted_row,
            strict=True,
        )
    )


def _row_matches(
    gold_row: Sequence[Any],
    predicted_row: Sequence[Any],
    float_tol: float,
) -> bool:
    """Provide a hashable-independent row matching predicate."""
    return _rows_equal(gold_row, predicted_row, float_tol)


def rows_equal(
    gold_rows: Sequence[Sequence[Any]],
    pred_rows: Sequence[Sequence[Any]],
    float_tol: float = 1e-6,
) -> bool:
    """Compare SQL result sets as unordered multisets.

    Result comparison intentionally treats NULL == NULL because the
    comparator evaluates whether two executed result values represent
    the same answer. It is not reproducing SQL's three-valued logic.

    Row order is ignored, but duplicate rows are preserved. Column names
    are intentionally irrelevant because this function receives values
    only; column positions remain significant.
    """
    if len(gold_rows) != len(pred_rows):
        return False

    if not gold_rows:
        return True

    if any(
        len(gold_row) != len(pred_row)
        for gold_row, pred_row in zip(
            gold_rows,
            pred_rows,
            strict=True,
        )
    ):
        return False

    unmatched_predictions = list(pred_rows)

    for gold_row in gold_rows:
        match_index = next(
            (
                index
                for index, predicted_row in enumerate(unmatched_predictions)
                if _row_matches(gold_row, predicted_row, float_tol)
            ),
            None,
        )

        if match_index is None:
            return False

        unmatched_predictions.pop(match_index)

    return not unmatched_predictions
