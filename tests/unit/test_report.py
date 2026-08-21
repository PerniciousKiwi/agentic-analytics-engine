from __future__ import annotations

import json
from pathlib import Path

from eval.report import build_report, load_results


def test_load_results(tmp_path: Path) -> None:
    results_path = tmp_path / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "suite": "test_suite",
                "generated_at": "2026-08-21T00:00:00+00:00",
                "results": [
                    {
                        "question": "Q1",
                        "gold_sql": "SELECT 1;",
                        "predicted_sql": "SELECT 1;",
                        "executed_ok": True,
                        "correct": True,
                        "latency_ms": 10.0,
                        "tokens_in": 100,
                        "tokens_out": 20,
                        "confidence": None,
                        "abstained": False,
                        "failure_class": None,
                    },
                    {
                        "question": "Q2",
                        "gold_sql": "SELECT 2;",
                        "predicted_sql": "SELECT 3;",
                        "executed_ok": True,
                        "correct": False,
                        "latency_ms": 30.0,
                        "tokens_in": 200,
                        "tokens_out": 40,
                        "confidence": None,
                        "abstained": False,
                        "failure_class": None,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = load_results(results_path)

    assert payload["suite"] == "test_suite"
    assert len(payload["results"]) == 2


def test_build_report_contains_required_metrics() -> None:
    payload = {
        "suite": "test_suite",
        "generated_at": "2026-08-21T00:00:00+00:00",
        "results": [
            {
                "question": "Q1",
                "gold_sql": "SELECT 1;",
                "predicted_sql": "SELECT 1;",
                "executed_ok": True,
                "correct": True,
                "latency_ms": 10.0,
                "tokens_in": 100,
                "tokens_out": 20,
                "confidence": None,
                "abstained": False,
                "failure_class": None,
            },
            {
                "question": "Q2",
                "gold_sql": "SELECT 2;",
                "predicted_sql": "SELECT 3;",
                "executed_ok": True,
                "correct": False,
                "latency_ms": 30.0,
                "tokens_in": 200,
                "tokens_out": 40,
                "confidence": None,
                "abstained": False,
                "failure_class": None,
            },
        ],
    }

    report = build_report(payload)

    assert "| Metric | Value |" in report
    assert "Question count" in report
    assert "Accuracy" in report
    assert "Mean latency (ms)" in report
    assert "Mean tokens in" in report
    assert "Mean tokens out" in report
    assert "50.00%" in report
