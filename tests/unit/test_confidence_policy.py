from __future__ import annotations

import pytest

from cardinal.confidence.policy import (
    choose_threshold,
)


def test_choose_threshold_maximizes_coverage() -> None:
    confidences = [
        0.95,
        0.90,
        0.80,
        0.40,
    ]

    correct = [
        1,
        1,
        1,
        0,
    ]

    policy = choose_threshold(
        confidences,
        correct,
        target_accuracy=0.90,
    )

    assert policy.threshold == pytest.approx(
        0.80
    )

    assert policy.coverage == pytest.approx(
        0.75
    )

    assert policy.achieved_accuracy == pytest.approx(
        1.0
    )


def test_policy_abstains_below_threshold() -> None:
    policy = choose_threshold(
        [0.9, 0.8, 0.2],
        [1, 1, 0],
        target_accuracy=0.9,
    )

    assert policy.should_abstain(
        policy.threshold - 0.01
    )

    assert not policy.should_abstain(
        policy.threshold
    )


def test_unachievable_target_raises() -> None:
    with pytest.raises(
        ValueError,
        match="not achievable",
    ):
        choose_threshold(
            [0.9, 0.8],
            [0, 0],
            target_accuracy=0.9,
        )