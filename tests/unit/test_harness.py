from __future__ import annotations

import json
from pathlib import Path

import pytest
from eval.harness import RESULT_FIELDS, load_suite


def test_result_fields_match_phase_2_contract() -> None:
    assert RESULT_FIELDS == (
        "question",
        "gold_sql",
        "predicted_sql",
        "executed_ok",
        "correct",
        "latency_ms",
        "tokens_in",
        "tokens_out",
        "prompt_hash",
        "confidence",
        "abstained",
        "failure_class",
    )


def test_load_suite_returns_jsonl_records(tmp_path: Path) -> None:
    suite_path = tmp_path / "suite.jsonl"
    suite_path.write_text(
        json.dumps(
            {
                "question": "How many rows?",
                "gold_sql": "SELECT COUNT(*) FROM orders;",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_suite(suite_path)

    assert len(rows) == 1
    assert rows[0]["question"] == "How many rows?"
    assert rows[0]["gold_sql"] == "SELECT COUNT(*) FROM orders;"


def test_load_suite_rejects_invalid_json(tmp_path: Path) -> None:
    suite_path = tmp_path / "suite.jsonl"
    suite_path.write_text("{not valid json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON"):
        load_suite(suite_path)
