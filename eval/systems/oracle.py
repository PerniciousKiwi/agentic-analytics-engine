from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class OracleSystem:
    """Return the gold SQL supplied in the evaluation context."""

    def answer(
        self,
        question: str,
        db_context: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Return the question's gold SQL without modification."""
        del question

        gold_sql = db_context.get("gold_sql")

        if not isinstance(gold_sql, str) or not gold_sql.strip():
            raise ValueError("Oracle requires a non-empty gold_sql value.")

        return gold_sql, {}
