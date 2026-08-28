# ruff: noqa: S608

from __future__ import annotations

import re
from pathlib import Path

import yaml

from cardinal.catalog.cards import ColumnCard, SampleRow, TableCard
from cardinal.db.reader import WarehouseReader


class CardProfiler:
    """Enrich schema cards with runtime warehouse statistics."""

    def __init__(
        self,
        reader: WarehouseReader,
        config_path: Path | str = "configs/catalog.yaml",
    ) -> None:
        self.reader = reader
        self.config_path = Path(config_path)

        config = yaml.safe_load(
            self.config_path.read_text(encoding="utf-8"),
        )

        profiling = config.get("profiling", {})

        self.low_cardinality_threshold = int(
            profiling.get("low_cardinality_threshold", 50),
        )
        self.top_values_limit = int(
            profiling.get("top_values_limit", 10),
        )
        self.sample_rows_limit = int(
            profiling.get("sample_rows", 3),
        )

    def profile_table(self, card: TableCard) -> TableCard:
        table = self._qualified_table(
            card.schema_name,
            card.table_name,
        )

        row_count = self.reader.fetch_scalar(
            f"SELECT COUNT(*) FROM {table}",
        )

        card.row_count = int(row_count)

        sample_columns = [column.name for column in card.columns if not column.is_pii]

        if sample_columns:
            quoted_columns = ", ".join(self._quote_identifier(column) for column in sample_columns)

            sample_rows = self.reader.fetch_all(
                (f"SELECT {quoted_columns} FROM {table} LIMIT {self.sample_rows_limit}"),
            )

            allowed_columns = set(sample_columns)

            card.sample_rows = [
                SampleRow(
                    values={
                        key: value for key, value in dict(row).items() if key in allowed_columns
                    },
                )
                for row in sample_rows
            ]

        return card

    def profile_column(self, card: ColumnCard) -> ColumnCard:
        table = self._qualified_table(
            card.schema_name,
            card.table_name,
        )
        column = self._quote_identifier(card.column_name)

        statistics = self.reader.fetch_all(
            (
                "SELECT "
                "CASE "
                "WHEN COUNT(*) = 0 THEN 0.0 "
                f"ELSE COUNT(*) FILTER (WHERE {column} IS NULL)::double precision "
                "/ COUNT(*)::double precision "
                "END AS null_rate, "
                f"COUNT(DISTINCT {column}) AS distinct_count "
                f"FROM {table}"
            ),
        )

        if statistics:
            card.null_rate = statistics[0]["null_rate"]
            card.distinct_count = statistics[0]["distinct_count"]

        if card.is_pii:
            return card

        if (
            card.distinct_count is not None and card.distinct_count < self.low_cardinality_threshold
        ) or self._supports_min_max(card.data_type):
            top_values = self.reader.fetch_all(
                (
                    f"SELECT {column} AS value, "
                    "COUNT(*) AS count "
                    f"FROM {table} "
                    f"WHERE {column} IS NOT NULL "
                    f"GROUP BY {column} "
                    "ORDER BY count DESC "
                    f"LIMIT {self.top_values_limit}"
                ),
            )

            card.top_values = [row["value"] for row in top_values]

        if self._supports_min_max(card.data_type):
            bounds = self.reader.fetch_all(
                (f"SELECT MIN({column}) AS min_value, MAX({column}) AS max_value FROM {table}"),
            )

            if bounds:
                card.min_value = bounds[0]["min_value"]
                card.max_value = bounds[0]["max_value"]

        return card

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        if not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*",
            identifier,
        ):
            raise ValueError(
                f"Invalid SQL identifier: {identifier!r}",
            )

        return f'"{identifier}"'

    @classmethod
    def _qualified_table(
        cls,
        schema_name: str,
        table_name: str,
    ) -> str:
        return f"{cls._quote_identifier(schema_name)}.{cls._quote_identifier(table_name)}"

    @staticmethod
    def _supports_min_max(data_type: str | None) -> bool:
        if data_type is None:
            return False

        normalized = data_type.lower()

        return any(
            type_name in normalized
            for type_name in (
                "numeric",
                "integer",
                "bigint",
                "smallint",
                "decimal",
                "real",
                "double",
                "date",
                "timestamp",
            )
        )
