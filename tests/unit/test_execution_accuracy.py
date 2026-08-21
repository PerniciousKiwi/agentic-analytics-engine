from __future__ import annotations

from eval.execution_accuracy import rows_equal


def test_empty_results_are_equal() -> None:
    assert rows_equal([], []) is True


def test_one_empty_result_is_not_equal() -> None:
    assert rows_equal([], [(1,)]) is False
    assert rows_equal([(1,)], []) is False


def test_identical_results_are_equal() -> None:
    gold_rows = [
        (1, "Alice"),
        (2, "Bob"),
    ]
    pred_rows = [
        (1, "Alice"),
        (2, "Bob"),
    ]

    assert rows_equal(gold_rows, pred_rows) is True


def test_row_order_does_not_matter() -> None:
    gold_rows = [
        (1, "Alice"),
        (2, "Bob"),
        (3, "Carol"),
    ]
    pred_rows = [
        (3, "Carol"),
        (1, "Alice"),
        (2, "Bob"),
    ]

    assert rows_equal(gold_rows, pred_rows) is True


def test_duplicate_rows_are_preserved() -> None:
    gold_rows = [
        (1, "Alice"),
        (1, "Alice"),
        (2, "Bob"),
    ]
    pred_rows = [
        (2, "Bob"),
        (1, "Alice"),
        (1, "Alice"),
    ]

    assert rows_equal(gold_rows, pred_rows) is True


def test_different_duplicate_counts_are_not_equal() -> None:
    gold_rows = [
        (1, "Alice"),
        (1, "Alice"),
        (2, "Bob"),
    ]
    pred_rows = [
        (1, "Alice"),
        (2, "Bob"),
    ]

    assert rows_equal(gold_rows, pred_rows) is False


def test_column_names_are_irrelevant() -> None:
    gold_rows = [
        (101, 500.0),
        (102, 750.0),
    ]
    pred_rows = [
        (101, 500.0),
        (102, 750.0),
    ]

    assert rows_equal(gold_rows, pred_rows) is True


def test_column_position_matters() -> None:
    gold_rows = [
        (101, 500.0),
    ]
    pred_rows = [
        (500.0, 101),
    ]

    assert rows_equal(gold_rows, pred_rows) is False


def test_column_count_mismatch_is_not_equal() -> None:
    gold_rows = [
        (101, 500.0),
    ]
    pred_rows = [
        (101,),
    ]

    assert rows_equal(gold_rows, pred_rows) is False


def test_null_equals_null() -> None:
    gold_rows = [
        (101, None),
    ]
    pred_rows = [
        (101, None),
    ]

    assert rows_equal(gold_rows, pred_rows) is True


def test_null_does_not_equal_non_null() -> None:
    gold_rows = [
        (101, None),
    ]
    pred_rows = [
        (101, 0),
    ]

    assert rows_equal(gold_rows, pred_rows) is False


def test_float_values_within_tolerance_are_equal() -> None:
    gold_rows = [
        (1.0000000,),
    ]
    pred_rows = [
        (1.0000005,),
    ]

    assert (
        rows_equal(
            gold_rows,
            pred_rows,
            float_tol=1e-6,
        )
        is True
    )


def test_float_values_outside_tolerance_are_not_equal() -> None:
    gold_rows = [
        (1.0000000,),
    ]
    pred_rows = [
        (1.0000020,),
    ]

    assert (
        rows_equal(
            gold_rows,
            pred_rows,
            float_tol=1e-6,
        )
        is False
    )


def test_float_boundary_is_explicit() -> None:
    gold_rows = [
        (1.0,),
    ]
    pred_rows = [
        (1.0 + 1e-6,),
    ]

    assert (
        rows_equal(
            gold_rows,
            pred_rows,
            float_tol=1e-6,
        )
        is True
    )


def test_large_float_uses_relative_tolerance() -> None:
    gold_rows = [
        (1_000_000.0,),
    ]
    pred_rows = [
        (1_000_000.5,),
    ]

    assert (
        rows_equal(
            gold_rows,
            pred_rows,
            float_tol=1e-6,
        )
        is True
    )


def test_numeric_type_difference_does_not_matter_when_values_match() -> None:
    gold_rows = [
        (1,),
    ]
    pred_rows = [
        (1.0,),
    ]

    assert rows_equal(gold_rows, pred_rows) is True


def test_mixed_row_types_are_compared_elementwise() -> None:
    gold_rows = [
        (1, "Alice", None, 10.0),
    ]
    pred_rows = [
        (1, "Alice", None, 10.0000005),
    ]

    assert (
        rows_equal(
            gold_rows,
            pred_rows,
            float_tol=1e-6,
        )
        is True
    )


def test_different_string_values_are_not_equal() -> None:
    gold_rows = [
        (1, "Alice"),
    ]
    pred_rows = [
        (1, "Bob"),
    ]

    assert rows_equal(gold_rows, pred_rows) is False
