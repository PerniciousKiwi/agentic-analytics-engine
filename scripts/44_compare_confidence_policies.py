from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cardinal.confidence.policy import choose_threshold

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OOF_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_oof_predictions.jsonl"
)

TARGETS = [
    0.70,
    0.75,
    0.80,
    0.85,
    0.90,
    0.95,
]


def load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with OOF_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            if not line.strip():
                continue

            rows.append(
                json.loads(line)
            )

    return rows


def evaluate_group(
    name: str,
    rows: list[dict[str, Any]],
) -> None:
    print()
    print(f"=== {name} ===")
    print(
        f"{'Target':>8} "
        f"{'Threshold':>11} "
        f"{'Accuracy':>10} "
        f"{'Coverage':>10} "
        f"{'Abstain':>10}"
    )

    confidences = [
        float(row["confidence"])
        for row in rows
    ]

    correct = [
        int(row["correct"])
        for row in rows
    ]

    for target in TARGETS:
        try:
            policy = choose_threshold(
                confidences,
                correct,
                target_accuracy=target,
            )

            print(
                f"{target:>7.0%} "
                f"{policy.threshold:>11.6f} "
                f"{policy.achieved_accuracy:>9.2%} "
                f"{policy.coverage:>9.2%} "
                f"{1.0 - policy.coverage:>9.2%}"
            )

        except ValueError:
            print(
                f"{target:>7.0%} "
                f"{'N/A':>11} "
                f"{'N/A':>10} "
                f"{'N/A':>10} "
                f"{'N/A':>10}"
            )


def main() -> None:
    rows = load_rows()

    bird_rows = [
        row
        for row in rows
        if row["suite"] == "bird_dev_200"
    ]

    olist_rows = [
        row
        for row in rows
        if row["suite"] == "olist_gold_150"
    ]

    evaluate_group(
        "combined",
        rows,
    )

    evaluate_group(
        "bird_dev_200",
        bird_rows,
    )

    evaluate_group(
        "olist_gold_150",
        olist_rows,
    )


if __name__ == "__main__":
    main()