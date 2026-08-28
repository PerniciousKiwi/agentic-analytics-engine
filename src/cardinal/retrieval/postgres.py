from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from cardinal.catalog.cards import SchemaCard
from cardinal.config import get_settings


class PostgresCardStore:
    """Persist and search schema cards using PostgreSQL full-text search."""

    TABLE_NAME = "schema_cards"

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(
            get_settings().postgres_rw_dsn,
        )

    def initialize(self) -> None:
        """Create the catalog table and its search index."""
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE SCHEMA IF NOT EXISTS app;

                    DROP TABLE IF EXISTS app.schema_cards;

                    CREATE TABLE app.schema_cards (
                        card_id TEXT PRIMARY KEY,
                        card_type TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        card_name TEXT NOT NULL,
                        card_description TEXT NOT NULL,
                        card_values_text TEXT NOT NULL DEFAULT '',
                        card_text TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        search_vector TSVECTOR GENERATED ALWAYS AS (
                            to_tsvector(
                                'english',
                                card_name || ' ' ||
                                domain || ' ' ||
                                card_description || ' ' ||
                                card_values_text || ' ' ||
                                card_text
                            )
                        ) STORED
                    );

                    CREATE INDEX ix_schema_cards_search_vector
                    ON app.schema_cards
                    USING GIN (search_vector);

                    CREATE INDEX ix_schema_cards_card_type
                    ON app.schema_cards (card_type);

                    CREATE INDEX ix_schema_cards_domain
                    ON app.schema_cards (domain);
                    """
                )
            )

    def replace_all(self, cards: Sequence[SchemaCard]) -> None:
        """Replace the complete persisted catalog with the supplied cards."""
        with self.engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE app.schema_cards"))

            for card in cards:
                connection.execute(
                    text(
                        """
                        INSERT INTO app.schema_cards (
                            card_id,
                            card_type,
                            domain,
                            card_name,
                            card_description,
                            card_values_text,
                            card_text,
                            metadata
                        )
                        VALUES (
                            :card_id,
                            :card_type,
                            :domain,
                            :card_name,
                            :card_description,
                            :card_values_text,
                            :card_text,
                            CAST(:metadata AS JSONB)
                        )
                        """
                    ),
                    {
                        "card_id": card.card_id,
                        "card_type": card.card_type,
                        "domain": card.domain,
                        "card_name": card.card_name,
                        "card_description": card.card_description,
                        "card_values_text": card.card_values_text,
                        "card_text": card.to_text(),
                        "metadata": self._metadata(card),
                    },
                )

    def count(self) -> int:
        """Return the number of persisted cards."""
        with self.engine.connect() as connection:
            result = connection.execute(text("SELECT COUNT(*) FROM app.schema_cards"))
            return int(result.scalar_one())

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Run PostgreSQL full-text search over persisted cards."""
        if not query.strip():
            return []

        with self.engine.connect() as connection:
            result = connection.execute(
                text(
                    """
                    SELECT
                        card_id,
                        card_type,
                        domain,
                        card_name,
                        card_description,
                        card_values_text,
                        card_text,
                        metadata,
                        ts_rank_cd(
                            search_vector,
                            websearch_to_tsquery('english', :query)
                        ) AS score
                    FROM app.schema_cards
                    WHERE search_vector @@
                        websearch_to_tsquery('english', :query)
                    ORDER BY score DESC, card_id
                    LIMIT :limit
                    """
                ),
                {
                    "query": query,
                    "limit": limit,
                },
            )

            return [dict(row) for row in result.mappings().all()]

    @staticmethod
    def _metadata(card: SchemaCard) -> str:
        """Serialize card-specific metadata for PostgreSQL JSONB."""
        if card.card_type == "table":
            return card.model_dump_json(
                include={
                    "schema_name",
                    "table_name",
                    "grain",
                    "row_count",
                }
            )

        if card.card_type == "column":
            return card.model_dump_json(
                include={
                    "schema_name",
                    "table_name",
                    "column_name",
                    "data_type",
                    "description",
                    "is_pii",
                }
            )

        return card.model_dump_json(
            include={
                "name",
                "label",
                "definition",
                "filters",
                "grain",
                "caveats",
                "tables",
            }
        )
