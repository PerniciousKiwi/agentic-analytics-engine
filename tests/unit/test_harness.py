from __future__ import annotations

import json
from pathlib import Path

import pytest
from eval.harness import RESULT_FIELDS, load_suite


def test_result_fields_match_phase_9_contract() -> None:
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
        "abstain_reason",
        "ambiguity_type",
        "clarifying_question",
        "generation_skipped",
        "failure_class",
        "repair_attempts",
        "degraded",
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


def test_run_suite_classifies_missing_predicted_sql_as_other() -> None:
    class EmptySystem:
        def answer(
            self,
            question: str,
            db_context: dict,
        ) -> tuple[str, dict]:
            return "", {}

    suite = [
        {
            "question": "How many business customers have placed at least one order?",
            "gold_sql": "SELECT 1;",
            "db_id": None,
        }
    ]

    config = {
        "float_tolerance": 1e-6,
    }

    from eval.harness import run_suite

    results = run_suite(
        suite=suite,
        system=EmptySystem(),
        config=config,
        suite_name="olist_gold_150",
    )

    assert len(results) == 1
    assert results[0]["predicted_sql"] == ""
    assert results[0]["executed_ok"] is False
    assert results[0]["correct"] is False
    assert results[0]["failure_class"] == "OTHER"
    assert results[0]["error"] == "Evaluation system returned no predicted SQL."
