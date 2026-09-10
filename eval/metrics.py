from __future__ import annotations

import numpy as np


def risk_coverage(
    confidences: list[float] | np.ndarray,
    correct: list[int] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return coverage and risk ordered by descending confidence."""

    confidence_array = np.asarray(
        confidences,
        dtype=float,
    )

    correct_array = np.asarray(
        correct,
        dtype=float,
    )

    if confidence_array.ndim != 1:
        raise ValueError(
            "confidences must be one-dimensional."
        )

    if correct_array.ndim != 1:
        raise ValueError(
            "correct must be one-dimensional."
        )

    if len(confidence_array) != len(correct_array):
        raise ValueError(
            "confidences and correct must have the same length."
        )

    if len(confidence_array) == 0:
        raise ValueError(
            "risk_coverage requires at least one prediction."
        )

    order = np.argsort(-confidence_array)

    sorted_correct = correct_array[order]

    answered = np.arange(
        1,
        len(sorted_correct) + 1,
        dtype=float,
    )

    coverage = answered / len(sorted_correct)

    selective_accuracy = (
        np.cumsum(sorted_correct)
        / answered
    )

    risk = 1.0 - selective_accuracy

    return coverage, risk


def aurc(
    coverage: list[float] | np.ndarray,
    risk: list[float] | np.ndarray,
) -> float:
    """Compute area under the risk-coverage curve."""

    coverage_array = np.asarray(
        coverage,
        dtype=float,
    )

    risk_array = np.asarray(
        risk,
        dtype=float,
    )

    if len(coverage_array) != len(risk_array):
        raise ValueError(
            "coverage and risk must have the same length."
        )

    if len(coverage_array) == 0:
        raise ValueError(
            "aurc requires at least one point."
        )

    return float(
        np.trapezoid(
            risk_array,
            coverage_array,
        )
    )