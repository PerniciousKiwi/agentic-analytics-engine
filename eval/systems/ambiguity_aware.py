from __future__ import annotations

from typing import Any

from cardinal.ambiguity.detector import AmbiguityDetector
from cardinal.ambiguity.models import AbstainReason
from eval.systems.retrieval_guarded_repaired import (
    RetrievalGuardedRepairedSystem,
)


class AmbiguityAwareSystem(RetrievalGuardedRepairedSystem):
    """Phase 9 ambiguity gate in front of the Phase 8 pipeline."""

    def __init__(self) -> None:
        super().__init__()

        self.ambiguity_detector = AmbiguityDetector(
            catalog=self.catalog,
            client=self.client,
            loop=self.loop,
            retrieval=self.retrieval,
            context_assembler=self.context_assembler,
            include_retrieved_schema=False,
        )

    def answer(
        self,
        question: str,
        db_context: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Check ambiguity before running SQL generation."""

        # The ambiguity dataset is Olist-specific.
        # BIRD questions should continue through the existing system.
        if db_context.get("source") != "postgres":
            return super().answer(
                question,
                db_context,
            )

        decision, ambiguity_metadata = (
            self.ambiguity_detector.detect(
                question
            )
        )

        if decision.ambiguous:
            return "", {
                **ambiguity_metadata,
                "abstained": True,
                "abstain_reason": (
                    AbstainReason.AMBIGUOUS.value
                ),
                "confidence": None,
                "repair_attempts": 0,
                "degraded": False,
                "generation_skipped": True,
            }

        sql, metadata = super().answer(
            question,
            db_context,
        )

        metadata.update(
            ambiguity_metadata
        )

        metadata.setdefault(
            "abstained",
            False,
        )

        metadata.setdefault(
            "abstain_reason",
            None,
        )

        metadata["generation_skipped"] = False

        return sql, metadata