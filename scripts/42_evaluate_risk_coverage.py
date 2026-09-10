from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.metrics import aurc, risk_coverage

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OOF_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_oof_predictions.jsonl"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "risk_coverage_metrics.json"
)


def load_predictions() -> list[dict[str, Any]]:
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


def evaluate_rows(
    rows: list[dict[str, Any]],
) -> dict[str, float | int]:
    if not rows:
        raise ValueError(
            "Cannot evaluate an empty prediction set."
        )

    confidences = [
        float(row["confidence"])
        for row in rows
    ]

    correct = [
        int(row["correct"])
        for row in rows
    ]

    coverage, risk = risk_coverage(
        confidences,
        correct,
    )

    accuracy = (
        sum(correct)
        / len(correct)
    )

    return {
        "rows": len(rows),
        "correct": sum(correct),
        "incorrect": (
            len(correct) - sum(correct)
        ),
        "always_answer_accuracy": accuracy,
        "always_answer_risk": 1.0 - accuracy,
        "aurc": aurc(
            coverage,
            risk,
        ),
    }


def main() -> None:
    rows = load_predictions()

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

    results = {
        "combined": evaluate_rows(rows),
        "bird_dev_200": evaluate_rows(
            bird_rows
        ),
        "olist_gold_150": evaluate_rows(
            olist_rows
        ),
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            results,
            indent=2,
        ),
        encoding="utf-8",
    )

    for name, metrics in results.items():
        print()
        print(f"=== {name} ===")
        print(
            f"Rows: {metrics['rows']}"
        )
        print(
            "Always-answer accuracy: "
            f"{metrics['always_answer_accuracy']:.4f}"
        )
        print(
            "Always-answer risk: "
            f"{metrics['always_answer_risk']:.4f}"
        )
        print(
            f"AURC: {metrics['aurc']:.4f}"
        )

    print()
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()