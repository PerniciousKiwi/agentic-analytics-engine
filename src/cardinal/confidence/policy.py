from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ThresholdPolicy:
    threshold: float
    target_accuracy: float
    achieved_accuracy: float
    coverage: float

    def should_abstain(
        self,
        confidence: float,
    ) -> bool:
        return confidence < self.threshold


def choose_threshold(
    confidences: Sequence[float],
    correct: Sequence[int],
    *,
    target_accuracy: float = 0.90,
) -> ThresholdPolicy:
    """Choose the highest-coverage threshold meeting target accuracy."""

    confidence_array = np.asarray(
        confidences,
        dtype=float,
    )

    correct_array = np.asarray(
        correct,
        dtype=int,
    )

    if len(confidence_array) == 0:
        raise ValueError(
            "At least one prediction is required."
        )

    if len(confidence_array) != len(correct_array):
        raise ValueError(
            "confidences and correct must have the same length."
        )

    if not 0.0 < target_accuracy <= 1.0:
        raise ValueError(
            "target_accuracy must be in (0, 1]."
        )

    order = np.argsort(
        -confidence_array
    )

    sorted_confidence = confidence_array[order]
    sorted_correct = correct_array[order]

    cumulative_correct = np.cumsum(
        sorted_correct
    )

    answered = np.arange(
        1,
        len(sorted_correct) + 1,
    )

    selective_accuracy = (
        cumulative_correct / answered
    )

    valid_indices = np.where(
        selective_accuracy >= target_accuracy
    )[0]

    if len(valid_indices) == 0:
        raise ValueError(
            "Target selective accuracy is not achievable."
        )

    chosen_index = int(
        valid_indices[-1]
    )

    threshold = float(
        sorted_confidence[chosen_index]
    )

    achieved_accuracy = float(
        selective_accuracy[chosen_index]
    )

    coverage = float(
        (chosen_index + 1)
        / len(sorted_correct)
    )

    return ThresholdPolicy(
        threshold=threshold,
        target_accuracy=target_accuracy,
        achieved_accuracy=achieved_accuracy,
        coverage=coverage,
    )