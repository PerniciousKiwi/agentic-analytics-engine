from __future__ import annotations

from pathlib import Path
from typing import Any

from cardinal.catalog.catalog import Catalog
from cardinal.guardrails.pipeline import run_guardrails
from eval.systems.baseline import BaselineSystem

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class BaselineGuardedSystem(BaselineSystem):
    """Baseline SQL generator wrapped with Phase 4 guardrails."""

    def __init__(self) -> None:
        super().__init__()

        self.catalog = Catalog.load(
            PROJECT_ROOT / "warehouse/target/manifest.json",
            PROJECT_ROOT / "warehouse/semantic/metrics.yml",
            PROJECT_ROOT / "warehouse/semantic/glossary.yml",
            PROJECT_ROOT / "warehouse/target/catalog.json",
        )

    def answer(
        self,
        question: str,
        db_context: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        predicted_sql, metadata = super().answer(
            question,
            db_context,
        )

        guardrail_result = run_guardrails(
            predicted_sql,
            self.catalog,
            role="analyst",
            max_rows=1000,
            enforce_result_limit=False,
        )

        result = guardrail_result.result

        if not result.allowed:
            metadata["failure_class"] = result.reasons[0]
            return guardrail_result.sql, metadata

        return guardrail_result.sql, metadata

    def close(self) -> None:
        super().close()
