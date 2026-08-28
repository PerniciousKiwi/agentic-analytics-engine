from __future__ import annotations

from pathlib import Path

import yaml
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from cardinal.config import get_settings


class DenseRetriever:
    """Retrieve schema cards using dense vector similarity."""

    def __init__(
        self,
        client: QdrantClient | None = None,
        model: SentenceTransformer | None = None,
        config_path: Path | str = "configs/retrieval.yaml",
    ) -> None:
        config = yaml.safe_load(
            Path(config_path).read_text(encoding="utf-8"),
        )

        embedding_config = config.get("embedding", {})
        qdrant_config = config.get("qdrant", {})
        dense_config = config.get("dense", {})

        self.model_name = str(
            embedding_config.get(
                "model_name",
                "BAAI/bge-small-en-v1.5",
            ),
        )

        self.dimension = int(
            embedding_config.get("dimension", 384),
        )

        self.collection_name = str(
            qdrant_config.get(
                "collection_name",
                "schema_cards",
            ),
        )

        self.top_k = int(
            dense_config.get("top_k", 50),
        )

        self.client = client or QdrantClient(
            url=get_settings().qdrant_url,
        )

        self.model = model or SentenceTransformer(
            self.model_name,
        )

    def search(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[tuple[str, float]]:
        """Return card IDs ranked by dense similarity."""
        if not query.strip():
            return []

        top_k = self.top_k if limit is None else min(limit, self.top_k)

        if top_k <= 0:
            return []

        vector = self.model.encode(
            query,
            normalize_embeddings=True,
        )

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=vector.tolist(),
            limit=top_k,
            with_payload=True,
        ).points

        return [
            (
                str(result.payload["card_id"]),
                float(result.score),
            )
            for result in results
        ]
