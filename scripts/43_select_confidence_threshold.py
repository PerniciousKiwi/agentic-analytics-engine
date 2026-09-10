from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cardinal.confidence.policy import (
    choose_threshold,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OOF_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_oof_predictions.jsonl"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_policy.json"
)

TARGET_ACCURACY = 0.85


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


def main() -> None:
    rows = load_rows()

    confidences = [
        float(row["confidence"])
        for row in rows
    ]

    correct = [
        int(row["correct"])
        for row in rows
    ]

    policy = choose_threshold(
        confidences,
        correct,
        target_accuracy=TARGET_ACCURACY,
    )

    output = {
        "target_accuracy": (
            policy.target_accuracy
        ),
        "threshold": (
            policy.threshold
        ),
        "achieved_accuracy": (
            policy.achieved_accuracy
        ),
        "coverage": (
            policy.coverage
        ),
        "abstention_rate": (
            1.0 - policy.coverage
        ),
        "selection_source": (
            "out_of_fold_predictions"
        ),
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            output,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"Target accuracy:   "
        f"{policy.target_accuracy:.2%}"
    )
    print(
        f"Threshold:         "
        f"{policy.threshold:.6f}"
    )
    print(
        f"Achieved accuracy: "
        f"{policy.achieved_accuracy:.2%}"
    )
    print(
        f"Coverage:          "
        f"{policy.coverage:.2%}"
    )
    print(
        f"Abstention rate:   "
        f"{1.0 - policy.coverage:.2%}"
    )
    print()
    print(
        f"Saved: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()