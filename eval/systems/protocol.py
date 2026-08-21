from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class EvaluationSystem(Protocol):
    """Interface implemented by every SQL-generation system."""

    def answer(
        self,
        question: str,
        db_context: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Return predicted SQL and execution metadata."""
        ...
