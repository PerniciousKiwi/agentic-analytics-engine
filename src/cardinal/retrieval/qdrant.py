from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from cardinal.catalog.cards import SchemaCard
from cardinal.config import get_settings
from cardinal.retrieval.models import RetrievalResult


class QdrantCardStore:
    """Persist and search schema-card embeddings using Qdrant."""

    def __init__(
        self,
        client: QdrantClient | None = None,
        model: SentenceTransformer | None = None,
        config_path: Path | str = "configs/retrieval.yaml",
    ) -> None:
        config_path = Path(config_path)
        config = yaml.safe_load(
            config_path.read_text(encoding="utf-8"),
        )

        embedding_config = config.get("embedding", {})
        qdrant_config = config.get("qdrant", {})

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

        distance_name = str(
            qdrant_config.get("distance", "cosine"),
        ).lower()

        if distance_name != "cosine":
            raise ValueError(
                "Only cosine distance is supported for dense retrieval.",
            )

        self.client = client or QdrantClient(
            url=get_settings().qdrant_url,
        )
        self.model = model or SentenceTransformer(self.model_name)

    def initialize(self) -> None:
        """Create the Qdrant collection if it does not already exist."""
        if self.client.collection_exists(self.collection_name):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.dimension,
                distance=Distance.COSINE,
            ),
        )

    def replace_all(self, cards: list[SchemaCard]) -> None:
        """Replace all dense retrieval points with the supplied cards."""
        self.initialize()

        self.client.delete_collection(
            collection_name=self.collection_name,
        )

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.dimension,
                distance=Distance.COSINE,
            ),
        )

        if not cards:
            return

        texts = [card.to_text() for card in cards]

        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
        )

        points = [
            PointStruct(
                id=self._point_id(card.card_id),
                vector=vector.tolist(),
                payload={
                    "card_id": card.card_id,
                    "card_type": card.card_type,
                    "domain": card.domain,
                    "card_name": card.card_name,
                    "card_text": card.to_text(),
                    "metadata": self._metadata(card),
                },
            )
            for card, vector in zip(cards, vectors, strict=True)
        ]

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Return the most semantically similar schema cards."""
        if not query.strip() or limit <= 0:
            return []

        vector = self.model.encode(
            query,
            normalize_embeddings=True,
        )

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=vector.tolist(),
            limit=limit,
            with_payload=True,
        ).points

        return [
            RetrievalResult(
                card_id=str(result.payload["card_id"]),
                card_type=result.payload["card_type"],
                domain=str(result.payload["domain"]),
                card_name=str(result.payload["card_name"]),
                card_text=str(result.payload["card_text"]),
                score=float(result.score),
                metadata=dict(result.payload.get("metadata", {})),
            )
            for result in results
        ]

    @staticmethod
    def _point_id(card_id: str) -> int:
        """Create a deterministic unsigned Qdrant point ID."""
        digest = hashlib.sha256(
            card_id.encode("utf-8"),
        ).digest()

        return int.from_bytes(
            digest[:8],
            byteorder="big",
            signed=False,
        )

    @staticmethod
    def _metadata(card: SchemaCard) -> dict[str, Any]:
        """Serialize card-specific metadata for Qdrant payloads."""
        if card.card_type == "table":
            return card.model_dump(
                include={
                    "schema_name",
                    "table_name",
                    "grain",
                    "row_count",
                },
            )

        if card.card_type == "column":
            return card.model_dump(
                include={
                    "schema_name",
                    "table_name",
                    "column_name",
                    "data_type",
                    "description",
                    "is_pii",
                },
            )

        return card.model_dump(
            include={
                "name",
                "label",
                "definition",
                "filters",
                "grain",
                "caveats",
                "tables",
            },
        )
