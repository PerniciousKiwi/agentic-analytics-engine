from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.systems.ambiguity_aware import AmbiguityAwareSystem


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SUITE_PATH = (
    PROJECT_ROOT
    / "eval"
    / "suites"
    / "ambiguity_100.jsonl"
)


def load_subset(
    per_type: int = 5,
) -> list[dict[str, Any]]:
    """Take a balanced small subset from all five ambiguity types."""

    buckets: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    with SUITE_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line in file:
            if not line.strip():
                continue

            row = json.loads(line)

            ambiguity_type = str(
                row["ambiguity_type"]
            )

            bucket = buckets.setdefault(
                ambiguity_type,
                [],
            )

            if len(bucket) < per_type:
                bucket.append(row)

    rows: list[dict[str, Any]] = []

    for ambiguity_type in (
        "metric",
        "time_grain",
        "entity",
        "filter",
        "tiebreak",
    ):
        rows.extend(
            buckets.get(
                ambiguity_type,
                [],
            )
        )

    return rows


def evaluate_mode(
    system: AmbiguityAwareSystem,
    rows: list[dict[str, Any]],
    *,
    include_schema: bool,
) -> dict[str, Any]:
    """Evaluate one detector context configuration."""

    detector = system.ambiguity_detector

    detector.include_retrieved_schema = (
        include_schema
    )

    detected = 0
    correct_type = 0
    fallback_count = 0

    total_latency_ms = 0.0
    total_tokens_in = 0
    total_tokens_out = 0

    for index, row in enumerate(
        rows,
        start=1,
    ):
        decision, metadata = detector.detect(
            str(row["question"])
        )

        if decision.ambiguous:
            detected += 1

        if (
            decision.ambiguous
            and decision.ambiguity_type is not None
            and decision.ambiguity_type.value
            == row["ambiguity_type"]
        ):
            correct_type += 1

        if decision.parse_fallback:
            fallback_count += 1

        total_latency_ms += float(
            metadata.get(
                "ambiguity_latency_ms"
            )
            or 0
        )

        total_tokens_in += int(
            metadata.get(
                "ambiguity_tokens_in"
            )
            or 0
        )

        total_tokens_out += int(
            metadata.get(
                "ambiguity_tokens_out"
            )
            or 0
        )

        print(
            f"{index:02d}/{len(rows):02d} "
            f"expected={row['ambiguity_type']} "
            f"predicted="
            f"{decision.ambiguity_type.value if decision.ambiguity_type else None} "
            f"ambiguous={decision.ambiguous}"
        )

    n = len(rows)

    return {
        "mode": (
            "semantic_plus_schema"
            if include_schema
            else "semantic_only"
        ),
        "n": n,
        "detection_rate": (
            detected / n
        ),
        "type_accuracy": (
            correct_type / n
        ),
        "parse_fallback_count": (
            fallback_count
        ),
        "mean_llm_latency_ms": (
            total_latency_ms / n
        ),
        "mean_tokens_in": (
            total_tokens_in / n
        ),
        "mean_tokens_out": (
            total_tokens_out / n
        ),
    }


def main() -> None:
    rows = load_subset(
        per_type=5
    )

    if len(rows) != 25:
        raise ValueError(
            "Expected 25 balanced questions "
            f"but found {len(rows)}."
        )

    system = AmbiguityAwareSystem()

    try:
        print(
            "\n=== semantic_only ==="
        )

        semantic_only = evaluate_mode(
            system,
            rows,
            include_schema=False,
        )

        print(
            "\n=== semantic_plus_schema ==="
        )

        semantic_plus_schema = (
            evaluate_mode(
                system,
                rows,
                include_schema=True,
            )
        )

    finally:
        system.close()

    results = [
        semantic_only,
        semantic_plus_schema,
    ]

    print(
        "\n=== Context ablation results ==="
    )

    print(
        json.dumps(
            results,
            indent=2,
        )
    )

    print(
        "\nDecision rule:"
    )

    print(
        "Keep semantic_only unless adding retrieved "
        "schema produces a meaningful accuracy gain "
        "that justifies extra latency and retrieval cost."
    )


if __name__ == "__main__":
    main()