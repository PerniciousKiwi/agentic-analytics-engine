from __future__ import annotations

from cardinal.retrieval.fusion import ReciprocalRankFusion
from cardinal.retrieval.models import (
    RetrievalMode,
    RetrievalResponse,
    RetrievalResult,
)
from cardinal.retrieval.postgres import PostgresCardStore
from cardinal.retrieval.qdrant import QdrantCardStore
from cardinal.retrieval.rerank import SchemaCardReranker


class RetrievalService:
    """Coordinate lexical, dense, hybrid, and reranked retrieval."""

    def __init__(
        self,
        lexical_store: PostgresCardStore | None = None,
        dense_store: QdrantCardStore | None = None,
        reranker: SchemaCardReranker | None = None,
        fusion: ReciprocalRankFusion | None = None,
    ) -> None:
        self.lexical_store = lexical_store or PostgresCardStore()
        self.dense_store = dense_store or QdrantCardStore()
        self.reranker = reranker or SchemaCardReranker()
        self.fusion = fusion or ReciprocalRankFusion()

    def retrieve(
        self,
        query: str,
        mode: RetrievalMode = "hybrid",
        limit: int = 10,
    ) -> RetrievalResponse:
        """Retrieve schema cards using the requested retrieval mode."""
        if limit <= 0 or not query.strip():
            return RetrievalResponse(
                query=query,
                mode=mode,
                results=[],
            )

        if mode == "lexical":
            results = self._lexical(query, limit)
        elif mode == "dense":
            results = self._dense(query, limit)
        elif mode == "hybrid":
            results = self._hybrid(query, limit)
        else:
            raise ValueError(f"Unsupported retrieval mode: {mode}")

        return RetrievalResponse(
            query=query,
            mode=mode,
            results=results,
        )

    def _lexical(
        self,
        query: str,
        limit: int,
    ) -> list[RetrievalResult]:
        return [
            self._to_result(row)
            for row in self.lexical_store.search(
                query,
                limit=limit,
            )
        ]

    def _dense(
        self,
        query: str,
        limit: int,
    ) -> list[RetrievalResult]:
        return self.dense_store.search(
            query,
            limit=limit,
        )

    def _hybrid(
        self,
        query: str,
        limit: int,
    ) -> list[RetrievalResult]:
        candidate_limit = max(limit, self.reranker.input_top_k)

        lexical_results = self._lexical(query, candidate_limit)
        dense_results = self._dense(query, candidate_limit)

        fused = self.fusion.fuse(
            [lexical_results, dense_results],
            limit=self.reranker.input_top_k,
        )

        fused_with_rrf_metadata = [
            result.model_copy(
                update={
                    "metadata": {
                        **result.metadata,
                        "rrf_score": result.score,
                    }
                }
            )
            for result in fused
        ]

        reranked = self.reranker.rerank(
            query,
            fused_with_rrf_metadata,
            limit=limit,
        )

        return [
            result.model_copy(
                update={
                    "metadata": {
                        **result.metadata,
                        "reranker_score": result.score,
                    }
                }
            )
            for result in reranked
        ]
    @staticmethod
    def _to_result(row: dict) -> RetrievalResult:
        return RetrievalResult(
            card_id=row["card_id"],
            card_type=row["card_type"],
            domain=row["domain"],
            card_name=row["card_name"],
            card_text=row["card_text"],
            score=float(row["score"]),
            metadata=dict(row.get("metadata", {})),
        )
