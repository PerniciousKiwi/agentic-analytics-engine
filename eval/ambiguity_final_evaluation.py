from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.ambiguity_detection import (
    AMBIGUITY_PATH,
    OLIST_GOLD_PATH,
    build_report,
    calculate_statistics,
    choose_unambiguous_negatives,
    evaluate_rows,
    load_jsonl,
)
from eval.systems.ambiguity_aware import (
    AmbiguityAwareSystem,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_RESULTS_PATH = (
    PROJECT_ROOT
    / "results"
    / "ambiguity_detection_final_raw.json"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "results"
    / "ambiguity_detection.md"
)


def question_key(
    row: dict[str, Any],
) -> str:
    return str(row["question"]).strip()


def main() -> None:
    ambiguity_rows = load_jsonl(
        AMBIGUITY_PATH
    )

    if len(ambiguity_rows) != 100:
        raise ValueError(
            "Expected exactly 100 ambiguity questions."
        )

    gold_rows = load_jsonl(
        OLIST_GOLD_PATH
    )

    # Reconstruct every negative region that was already
    # exposed during detector development.
    first_50 = choose_unambiguous_negatives(
        gold_rows,
        50,
    )

    first_100_pool = choose_unambiguous_negatives(
        gold_rows,
        100,
    )

    development_50_to_100 = (
        first_100_pool[50:100]
    )

    used_questions = {
        question_key(row)
        for row in (
            first_50
            + development_50_to_100
        )
    }

    # Final negatives must be answerable gold questions
    # that were never used during prompt/architecture tuning.
    unseen_negatives = [
        row
        for row in gold_rows
        if (
            row.get("answerable", True)
            and question_key(row)
            not in used_questions
        )
    ]

    final_negatives = unseen_negatives[:50]

    if not final_negatives:
        raise ValueError(
            "No unseen negative questions remain."
        )

    print(
        "Previously exposed negative questions:",
        len(used_questions),
    )

    print(
        "Final unseen negatives:",
        len(final_negatives),
    )

    system = AmbiguityAwareSystem()

    # Freeze final production architecture.
    system.ambiguity_detector.enable_verification = False
    system.ambiguity_detector.include_retrieved_schema = False

    try:
        print(
            "\n=== FINAL: ambiguous positives ==="
        )

        positive_results = evaluate_rows(
            system,
            ambiguity_rows,
            expected_ambiguous=True,
        )

        print(
            "\n=== FINAL: unseen clear negatives ==="
        )

        negative_results = evaluate_rows(
            system,
            final_negatives,
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
                "configuration": {
                    "context": "semantic_only",
                    "verification": False,
                    "negative_split": (
                        "unseen_after_development"
                    ),
                },
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
        build_report(statistics),
        encoding="utf-8",
    )

    print(
        "\n=== FINAL PHASE 9 RESULTS ==="
    )

    for ambiguity_type, stats in (
        statistics["per_type"].items()
    ):
        print(
            f"{ambiguity_type:10s} "
            f"detection="
            f"{stats['detection_rate']:.1%} "
            f"type="
            f"{stats['type_accuracy']:.1%}"
        )

    print(
        "\nOverall detection:",
        f"{statistics['overall_detection_rate']:.1%}",
    )

    print(
        "Final unseen false-positive rate:",
        f"{statistics['false_positive_rate']:.1%}",
    )

    print(
        "False positives:",
        f"{statistics['false_positive_count']}/"
        f"{statistics['negative_n']}",
    )

    print(
        "Parser fallbacks:",
        statistics["parse_fallback_count"],
    )

    print(
        "\nRaw results:",
        RAW_RESULTS_PATH,
    )

    print(
        "Report:",
        REPORT_PATH,
    )


if __name__ == "__main__":
    main()