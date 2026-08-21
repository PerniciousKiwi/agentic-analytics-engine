from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = PROJECT_ROOT / "eval" / "suites" / "olist_gold_150.jsonl"

EXPECTED_COUNT = 150

VALID_CATEGORIES = {
    "basic_aggregation",
    "multi_table_join",
    "window_time",
    "semantic_metric",
    "unanswerable",
}

VALID_DIFFICULTIES = {
    "simple",
    "moderate",
    "challenging",
}

REQUIRED_FIELDS = {
    "question_id",
    "question",
    "category",
    "difficulty",
    "answerable",
}


def load_suite() -> list[dict[str, Any]]:
    """Load the Olist evaluation suite."""
    if not SUITE_PATH.exists():
        raise RuntimeError(f"Suite does not exist: {SUITE_PATH}")

    rows: list[dict[str, Any]] = []

    with SUITE_PATH.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                raise RuntimeError(f"Blank line found at line {line_number}.")

            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSON at line {line_number}: {exc}") from exc

            if not isinstance(row, dict):
                raise RuntimeError(f"Line {line_number} must contain a JSON object.")

            rows.append(row)

    return rows


def validate_required_fields(row: dict[str, Any], index: int) -> None:
    """Validate required fields for one suite record."""
    missing = REQUIRED_FIELDS - set(row)

    if missing:
        raise RuntimeError(f"Record {index} is missing fields: {sorted(missing)}")


def validate_record(row: dict[str, Any], index: int) -> None:
    """Validate one Olist suite record."""
    validate_required_fields(row, index)

    question_id = row["question_id"]
    question = row["question"]
    category = row["category"]
    difficulty = row["difficulty"]
    answerable = row["answerable"]

    if not isinstance(question_id, str) or not question_id:
        raise RuntimeError(f"Record {index} has an invalid question_id.")

    if not isinstance(question, str) or not question.strip():
        raise RuntimeError(f"Record {index} has an invalid question.")

    if category not in VALID_CATEGORIES:
        raise RuntimeError(f"Record {index} has invalid category: {category!r}")

    if difficulty not in VALID_DIFFICULTIES:
        raise RuntimeError(f"Record {index} has invalid difficulty: {difficulty!r}")

    if not isinstance(answerable, bool):
        raise RuntimeError(f"Record {index} has non-boolean answerable value.")

    if answerable:
        gold_sql = row.get("gold_sql")

        if not isinstance(gold_sql, str) or not gold_sql.strip():
            raise RuntimeError(f"Record {index} is answerable but has no gold_sql.")

    else:
        if "gold_sql" in row:
            raise RuntimeError(f"Record {index} is unanswerable but contains gold_sql.")

        if category != "unanswerable":
            raise RuntimeError(f"Record {index} is unanswerable but category is {category!r}.")


def validate_suite(rows: list[dict[str, Any]]) -> None:
    """Validate the complete Olist evaluation suite."""
    if len(rows) != EXPECTED_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_COUNT} records, got {len(rows)}.")

    question_ids = [row.get("question_id") for row in rows]

    if len(question_ids) != len(set(question_ids)):
        raise RuntimeError("Duplicate question_id values found.")

    for index, row in enumerate(rows, start=1):
        validate_record(row, index)


def main() -> None:
    """Validate the Olist evaluation suite."""
    print("Olist gold suite validation")
    print("=" * 40)

    rows = load_suite()

    print(f"Records loaded: {len(rows)}")

    validate_suite(rows)

    print("Schema validation: PASS")
    print("Olist gold suite validation: PASS")


if __name__ == "__main__":
    main()
