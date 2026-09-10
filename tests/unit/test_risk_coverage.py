from __future__ import annotations

import numpy as np
import pytest
from eval.metrics import aurc, risk_coverage


def test_risk_coverage_orders_by_confidence() -> None:
    confidences = [
        0.9,
        0.2,
        0.8,
        0.4,
    ]

    correct = [
        1,
        0,
        1,
        0,
    ]

    coverage, risk = risk_coverage(
        confidences,
        correct,
    )

    expected_coverage = np.asarray(
        [
            0.25,
            0.50,
            0.75,
            1.00,
        ]
    )

    expected_risk = np.asarray(
        [
            0.0,
            0.0,
            1.0 / 3.0,
            0.5,
        ]
    )

    np.testing.assert_allclose(
        coverage,
        expected_coverage,
    )

    np.testing.assert_allclose(
        risk,
        expected_risk,
    )


def test_aurc_matches_manual_trapezoid() -> None:
    coverage = np.asarray(
        [
            0.25,
            0.50,
            0.75,
            1.00,
        ]
    )

    risk = np.asarray(
        [
            0.0,
            0.0,
            1.0 / 3.0,
            0.5,
        ]
    )

    expected = float(
        np.trapezoid(
            risk,
            coverage,
        )
    )

    assert aurc(
        coverage,
        risk,
    ) == pytest.approx(expected)


def test_risk_coverage_rejects_length_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="same length",
    ):
        risk_coverage(
            [0.9, 0.8],
            [1],
        )


def test_risk_coverage_rejects_empty_input() -> None:
    with pytest.raises(
        ValueError,
        match="at least one",
    ):
        risk_coverage(
            [],
            [],
        )