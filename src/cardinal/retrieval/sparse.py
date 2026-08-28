from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from cardinal.config import get_settings


class SparseRetriever:
    """Retrieve schema cards using PostgreSQL full-text search."""

    def __init__(
        self,
        engine: Engine | None = None,
        config_path: Path | str = "configs/retrieval.yaml",
    ) -> None:
        config = yaml.safe_load(
            Path(config_path).read_text(encoding="utf-8"),
        )

        sparse_config = config.get("sparse", {})
        self.top_k = int(sparse_config.get("top_k", 50))

        self.engine = engine or create_engine(
            get_settings().postgres_rw_dsn,
        )

    def search(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[tuple[str, float]]:
        """Return card IDs ranked by PostgreSQL cover-density search."""
        if not query.strip():
            return []

        top_k = self.top_k if limit is None else min(limit, self.top_k)

        if top_k <= 0:
            return []

        with self.engine.connect() as connection:
            result = connection.execute(
                text(
                    """
                    SELECT
                        card_id,
                        ts_rank_cd(
                            search_vector,
                            plainto_tsquery('english', :query)
                        ) AS score
                    FROM app.schema_cards
                    WHERE search_vector @@
                        plainto_tsquery('english', :query)
                    ORDER BY score DESC, card_id
                    LIMIT :limit
                    """
                ),
                {
                    "query": query,
                    "limit": top_k,
                },
            )

            return [(str(row["card_id"]), float(row["score"])) for row in result.mappings().all()]
