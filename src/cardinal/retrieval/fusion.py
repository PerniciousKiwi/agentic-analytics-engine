from __future__ import annotations

from cardinal.retrieval.models import RetrievalResult


class ReciprocalRankFusion:
    """Fuse ranked retrieval results using reciprocal rank fusion."""

    def __init__(self, k: int = 60) -> None:
        if k <= 0:
            raise ValueError("RRF k must be greater than zero.")

        self.k = k

    def fuse(
        self,
        result_lists: list[list[RetrievalResult]],
        limit: int,
    ) -> list[RetrievalResult]:
        """Merge ranked result lists using reciprocal rank fusion."""
        if limit <= 0:
            return []

        results_by_id: dict[str, RetrievalResult] = {}
        scores: dict[str, float] = {}

        for results in result_lists:
            for rank, result in enumerate(results, start=1):
                results_by_id.setdefault(result.card_id, result)

                scores[result.card_id] = scores.get(result.card_id, 0.0) + 1.0 / (self.k + rank)

        ranked_ids = sorted(
            scores,
            key=lambda card_id: (-scores[card_id], card_id),
        )

        return [
            results_by_id[card_id].model_copy(
                update={"score": scores[card_id]},
            )
            for card_id in ranked_ids[:limit]
        ]
