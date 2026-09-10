from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from eval.systems.ambiguity_aware import AmbiguityAwareSystem


PROJECT_ROOT = Path(__file__).resolve().parents[1]

AMBIGUITY_PATH = (
    PROJECT_ROOT
    / "eval"
    / "suites"
    / "ambiguity_100.jsonl"
)

OLIST_GOLD_PATH = (
    PROJECT_ROOT
    / "eval"
    / "suites"
    / "olist_gold_150.jsonl"
)

RAW_RESULTS_PATH = (
    PROJECT_ROOT
    / "results"
    / "ambiguity_detection_raw.json"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "results"
    / "ambiguity_detection.md"
)


def load_jsonl(
    path: Path,
) -> list[dict[str, Any]]:
    """Load JSONL records."""

    rows: list[dict[str, Any]] = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path} "
                    f"line {line_number}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"{path} line {line_number} "
                    "must contain a JSON object."
                )

            rows.append(record)

    return rows


def choose_unambiguous_negatives(
    rows: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Reuse answerable Olist gold questions as negatives."""

    answerable = [
        row
        for row in rows
        if row.get("answerable", True)
    ]

    # Prefer simple aggregation and multi-table join questions
    # when the suite has a category/type label.
    preferred: list[dict[str, Any]] = []

    for row in answerable:
        category = str(
            row.get(
                "category",
                row.get(
                    "type",
                    "",
                ),
            )
        ).lower()

        normalized = category.replace(
            "_",
            " ",
        ).replace(
            "-",
            " ",
        )

        if normalized in {
            "simple aggregation",
            "multi table join",
        }:
            preferred.append(row)

    pool = preferred if len(preferred) >= limit else answerable

    return pool[:limit]


def evaluate_rows(
    system: AmbiguityAwareSystem,
    rows: list[dict[str, Any]],
    *,
    expected_ambiguous: bool,
) -> list[dict[str, Any]]:
    """Run only the ambiguity detector, not SQL generation."""

    outputs: list[dict[str, Any]] = []

    for index, row in enumerate(
        rows,
        start=1,
    ):
        question = str(
            row["question"]
        )

        decision, metadata = (
            system.ambiguity_detector.detect(
                question
            )
        )

        output = {
            "id": row.get("id"),
            "question": question,
            "expected_ambiguous": expected_ambiguous,
            "expected_type": (
                row.get("ambiguity_type")
                if expected_ambiguous
                else None
            ),
            "predicted_ambiguous": (
                decision.ambiguous
            ),
            "predicted_type": (
                decision.ambiguity_type.value
                if decision.ambiguity_type
                else None
            ),
            "clarifying_question": (
                decision.clarifying_question
            ),
            "parse_fallback": (
                decision.parse_fallback
            ),
            "latency_ms": metadata.get(
                "ambiguity_latency_ms"
            ),
            "tokens_in": metadata.get(
                "ambiguity_tokens_in"
            ),
            "tokens_out": metadata.get(
                "ambiguity_tokens_out"
            ),
        }

        outputs.append(output)

        print(
            f"{index:03d}/{len(rows):03d} "
            f"ambiguous={decision.ambiguous} "
            f"type={output['predicted_type']} "
            f"| {question}"
        )

    return outputs


def calculate_statistics(
    positives: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate Phase 9 detection metrics."""

    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in positives:
        expected_type = str(
            row["expected_type"]
        )

        grouped[
            expected_type
        ].append(row)

    per_type: dict[
        str,
        dict[str, Any],
    ] = {}

    for ambiguity_type in (
        "metric",
        "time_grain",
        "entity",
        "filter",
        "tiebreak",
    ):
        rows = grouped[
            ambiguity_type
        ]

        if not rows:
            continue

        detected = sum(
            1
            for row in rows
            if row[
                "predicted_ambiguous"
            ]
        )

        correctly_typed = sum(
            1
            for row in rows
            if (
                row[
                    "predicted_ambiguous"
                ]
                and row[
                    "predicted_type"
                ]
                == ambiguity_type
            )
        )

        per_type[
            ambiguity_type
        ] = {
            "n": len(rows),
            "detected": detected,
            "correctly_typed": (
                correctly_typed
            ),
            "detection_rate": (
                detected / len(rows)
            ),
            "type_accuracy": (
                correctly_typed
                / len(rows)
            ),
        }

    total_detected = sum(
        1
        for row in positives
        if row[
            "predicted_ambiguous"
        ]
    )

    false_positives = sum(
        1
        for row in negatives
        if row[
            "predicted_ambiguous"
        ]
    )

    fallback_count = sum(
        1
        for row in (
            positives
            + negatives
        )
        if row[
            "parse_fallback"
        ]
    )

    return {
        "positive_n": len(
            positives
        ),
        "negative_n": len(
            negatives
        ),
        "overall_detection_rate": (
            total_detected
            / len(positives)
        ),
        "false_positive_rate": (
            false_positives
            / len(negatives)
            if negatives
            else 0.0
        ),
        "false_positive_count": (
            false_positives
        ),
        "parse_fallback_count": (
            fallback_count
        ),
        "per_type": per_type,
    }


def build_report(
    statistics: dict[str, Any],
) -> str:
    """Render Markdown evaluation report."""

    lines = [
        "# Phase 9 — Ambiguity Detection",
        "",
        "## Context configuration",
        "",
        (
            "The detector currently uses the complete "
            "`metrics.yml` and `glossary.yml` semantic context "
            "without retrieved schema context."
        ),
        "",
        "## Results",
        "",
        (
            "| Ambiguity type | N | Detection rate | "
            "Correct-type rate |"
        ),
        "|---|---:|---:|---:|",
    ]

    for ambiguity_type in (
        "metric",
        "time_grain",
        "entity",
        "filter",
        "tiebreak",
    ):
        stats = statistics[
            "per_type"
        ].get(
            ambiguity_type
        )

        if stats is None:
            continue

        lines.append(
            f"| {ambiguity_type} "
            f"| {stats['n']} "
            f"| {stats['detection_rate']:.1%} "
            f"| {stats['type_accuracy']:.1%} |"
        )

    lines.extend(
        [
            "",
            (
                "**Overall ambiguity detection rate:** "
                f"{statistics['overall_detection_rate']:.1%}"
            ),
            "",
            (
                "**False-positive rate on reused "
                "Olist gold questions:** "
                f"{statistics['false_positive_rate']:.1%} "
                f"({statistics['false_positive_count']}/"
                f"{statistics['negative_n']})"
            ),
            "",
            (
                "**Parser fail-closed fallbacks:** "
                f"{statistics['parse_fallback_count']}"
            ),
            "",
            "## Interpretation",
            "",
            (
                "Detection rate measures whether an actually ambiguous "
                "question was flagged at all."
            ),
            "",
            (
                "Correct-type rate is stricter: the detector must both "
                "flag the question and assign the same ambiguity type "
                "as the authored dataset."
            ),
            "",
            (
                "False-positive rate measures how often previously "
                "validated Olist gold questions were incorrectly "
                "blocked by the ambiguity gate."
            ),
            "",
        ]
    )

    return "\n".join(
        lines
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Phase 9 ambiguity detection."
        )
    )

    parser.add_argument(
        "--negative-n",
        type=int,
        default=50,
        help=(
            "Number of Olist gold questions "
            "to reuse as unambiguous negatives."
        ),
    )

    args = parser.parse_args()

    if args.negative_n <= 0:
        raise ValueError(
            "--negative-n must be greater than zero."
        )

    ambiguity_rows = load_jsonl(
        AMBIGUITY_PATH
    )

    if len(ambiguity_rows) != 100:
        raise ValueError(
            "ambiguity_100.jsonl must contain "
            f"exactly 100 questions; found "
            f"{len(ambiguity_rows)}."
        )

    gold_rows = load_jsonl(
        OLIST_GOLD_PATH
    )

    negatives = choose_unambiguous_negatives(
        gold_rows,
        args.negative_n,
    )

    print(
        "\n=== Ambiguous positives ==="
    )

    system = AmbiguityAwareSystem()

    try:
        positive_results = evaluate_rows(
            system,
            ambiguity_rows,
            expected_ambiguous=True,
        )

        print(
            "\n=== Unambiguous negatives ==="
        )

        negative_results = evaluate_rows(
            system,
            negatives,
            expected_ambiguous=False,
        )

    finally:
        system.close()

    statistics = calculate_statistics(
        positive_results,
        negative_results,
    )

    RAW_RESULTS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    RAW_RESULTS_PATH.write_text(
        json.dumps(
            {
                "statistics": statistics,
                "positives": positive_results,
                "negatives": negative_results,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        build_report(
            statistics
        ),
        encoding="utf-8",
    )

    print(
        "\n=== Phase 9 results ==="
    )

    for ambiguity_type, stats in (
        statistics[
            "per_type"
        ].items()
    ):
        print(
            f"{ambiguity_type:10s} "
            f"detection="
            f"{stats['detection_rate']:.1%} "
            f"type="
            f"{stats['type_accuracy']:.1%}"
        )

    print(
        "\nOverall detection: "
        f"{statistics['overall_detection_rate']:.1%}"
    )

    print(
        "False-positive rate: "
        f"{statistics['false_positive_rate']:.1%}"
    )

    print(
        "Parser fallbacks: "
        f"{statistics['parse_fallback_count']}"
    )

    print(
        f"\nRaw results: {RAW_RESULTS_PATH}"
    )

    print(
        f"Report:      {REPORT_PATH}"
    )


if __name__ == "__main__":
    main()