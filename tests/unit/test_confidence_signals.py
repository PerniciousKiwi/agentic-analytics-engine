from datetime import datetime

from eval.execution_accuracy import rows_equal

from cardinal.confidence.grounding import (
    extract_grounding_claims,
    grounding_score,
)
from cardinal.confidence.signals import (
    build_failure_feature_vector,
    date_out_of_bounds_signal,
    empty_result_signal,
    excessive_row_count_signal,
    high_null_rate_signal,
    negative_value_signal,
)


def test_empty_result_signal() -> None:
    assert empty_result_signal([]) == 1
    assert empty_result_signal([[1]]) == 0


def test_high_null_rate_signal() -> None:
    rows = [
        [None, None],
        [None, 1],
    ]

    assert high_null_rate_signal(rows) == 1


def test_high_null_rate_signal_not_triggered_at_half() -> None:
    rows = [
        [None, 1],
        [None, 2],
    ]

    assert high_null_rate_signal(rows) == 0


def test_negative_value_signal() -> None:
    columns = [
        "customer_state",
        "revenue",
    ]

    rows = [
        ["SP", 100.0],
        ["RJ", -5.0],
    ]

    assert (
        negative_value_signal(
            columns,
            rows,
            {"revenue"},
        )
        == 1
    )


def test_negative_value_ignores_unmarked_fields() -> None:
    columns = ["revenue_change"]

    rows = [[-100.0]]

    assert (
        negative_value_signal(
            columns,
            rows,
            {"revenue"},
        )
        == 0
    )


def test_excessive_row_count_signal() -> None:
    references = {
        "multi_table_join": 20.0,
    }

    assert (
        excessive_row_count_signal(
            201,
            "multi_table_join",
            references,
        )
        == 1
    )

    assert (
        excessive_row_count_signal(
            200,
            "multi_table_join",
            references,
        )
        == 0
    )


def test_date_out_of_bounds_signal() -> None:
    bounds = {
        "min_order_purchase_timestamp": "2016-09-04T00:00:00",
        "max_order_purchase_timestamp": "2018-10-17T00:00:00",
    }

    rows = [
        [
            datetime(
                2019,
                1,
                1,
            )
        ]
    ]

    assert (
        date_out_of_bounds_signal(
            rows,
            bounds,
        )
        == 1
    )


def test_date_within_bounds_does_not_trigger() -> None:
    bounds = {
        "min_order_purchase_timestamp": "2016-09-04T00:00:00",
        "max_order_purchase_timestamp": "2018-10-17T00:00:00",
    }

    rows = [
        [
            datetime(
                2017,
                6,
                1,
            )
        ]
    ]

    assert (
        date_out_of_bounds_signal(
            rows,
            bounds,
        )
        == 0
    )


def test_failure_sentinel() -> None:
    features = build_failure_feature_vector()

    assert features.execution_failed == 1
    assert features.agreement_rate == 0.0
    assert features.grounding_score == 0.0
    assert features.retrieval_signals_available == 0


def test_grounding_score_for_grounded_answer() -> None:
    rows = [
        ["SP", 1250],
    ]

    answer = "SP had 1250 orders."

    assert grounding_score(answer, rows) == 1.0


def test_grounding_score_detects_unsupported_number() -> None:
    rows = [
        ["SP", 1250],
    ]

    answer = "SP had 9999 orders."

    assert grounding_score(answer, rows) < 1.0


def test_extract_grounding_claims_finds_numbers() -> None:
    claims = extract_grounding_claims(
        "Revenue was 1,250.50."
    )

    assert "1,250.50" in claims


def test_agreement_rate_three_of_five_match() -> None:
    from cardinal.confidence.signals import agreement_rate

    result_sets = [
        [[1], [2]],
        [[1], [2]],
        [[1], [2]],
        [[3]],
        [[4]],
    ]

    score = agreement_rate(
        result_sets,
        comparator=rows_equal,
    )

    assert score == 0.6