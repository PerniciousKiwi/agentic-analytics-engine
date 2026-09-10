from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OOF_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_oof_predictions.jsonl"
)

POLICY_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_policy.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "selected_policy_metrics.json"
)


def load_jsonl(
    path: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            if line.strip():
                rows.append(
                    json.loads(line)
                )

    return rows


def evaluate(
    rows: list[dict[str, Any]],
    threshold: float,
) -> dict[str, float | int]:
    answered = [
        row
        for row in rows
        if float(row["confidence"]) >= threshold
    ]

    total = len(rows)
    answered_count = len(answered)

    if answered_count == 0:
        selective_accuracy = 0.0
    else:
        selective_accuracy = (
            sum(
                int(row["correct"])
                for row in answered
            )
            / answered_count
        )

    always_answer_accuracy = (
        sum(
            int(row["correct"])
            for row in rows
        )
        / total
    )

    coverage = answered_count / total

    return {
        "rows": total,
        "answered": answered_count,
        "abstained": total - answered_count,
        "coverage": coverage,
        "abstention_rate": 1.0 - coverage,
        "selective_accuracy": selective_accuracy,
        "always_answer_accuracy": always_answer_accuracy,
    }


def main() -> None:
    rows = load_jsonl(
        OOF_PATH
    )

    policy = json.loads(
        POLICY_PATH.read_text(
            encoding="utf-8",
        )
    )

    threshold = float(
        policy["threshold"]
    )

    groups = {
        "combined": rows,
        "bird_dev_200": [
            row
            for row in rows
            if row["suite"] == "bird_dev_200"
        ],
        "olist_gold_150": [
            row
            for row in rows
            if row["suite"] == "olist_gold_150"
        ],
    }

    results = {
        name: evaluate(
            group_rows,
            threshold,
        )
        for name, group_rows in groups.items()
    }

    output = {
        "threshold": threshold,
        "target_accuracy": policy[
            "target_accuracy"
        ],
        "groups": results,
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            output,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"Global threshold: {threshold:.6f}"
    )

    for name, metrics in results.items():
        print()
        print(f"=== {name} ===")
        print(
            f"Rows:               "
            f"{metrics['rows']}"
        )
        print(
            f"Answered:           "
            f"{metrics['answered']}"
        )
        print(
            f"Coverage:           "
            f"{metrics['coverage']:.2%}"
        )
        print(
            f"Selective accuracy: "
            f"{metrics['selective_accuracy']:.2%}"
        )
        print(
            f"Always-answer acc.: "
            f"{metrics['always_answer_accuracy']:.2%}"
        )

    print()
    print(
        f"Saved: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()