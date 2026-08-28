from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cardinal.catalog.cards import (
    ColumnCard,
    ColumnSummary,
    MetricCard,
    Relationship,
    SchemaCard,
    TableCard,
)
from cardinal.catalog.catalog import Catalog


class SchemaCardBuilder:
    """Build static schema cards from the catalog and dbt schema metadata."""

    def __init__(
        self,
        catalog: Catalog,
        schema_path: Path | str,
    ) -> None:
        self.catalog = catalog
        self.schema_path = Path(schema_path)

    def build_all(self) -> list[SchemaCard]:
        cards: list[SchemaCard] = []

        cards.extend(self.build_table_cards())
        cards.extend(self.build_column_cards())
        cards.extend(self.build_metric_cards())

        return cards

    def build_table_cards(self) -> list[TableCard]:
        schema_metadata = self._load_schema_metadata()
        cards: list[TableCard] = []

        for relation in self.catalog.manifest.relations.values():
            metadata = schema_metadata.get(relation.name, {})

            columns = [
                ColumnSummary(
                    name=column.name,
                    data_type=column.data_type,
                    description=self._column_description(
                        metadata,
                        column.name,
                    ),
                    is_pii=column.is_pii,
                )
                for column in relation.columns.values()
            ]

            relationships = self._relationships(
                relation.name,
                metadata,
            )

            metrics = [
                metric.name
                for metric in self.catalog.metrics
                if any(
                    table.lower() == f"{relation.schema_name}.{relation.name}".lower()
                    for table in metric.tables
                )
            ]

            cards.append(
                TableCard(
                    card_id=f"table:{relation.schema_name}.{relation.name}",
                    domain=self._domain(relation.name),
                    card_name=relation.name,
                    card_description=metadata.get("description", ""),
                    schema_name=relation.schema_name,
                    table_name=relation.name,
                    row_count=0,
                    columns=columns,
                    relationships=relationships,
                    metrics=metrics,
                ),
            )

        return cards

    def build_column_cards(self) -> list[ColumnCard]:
        schema_metadata = self._load_schema_metadata()
        cards: list[ColumnCard] = []

        for relation in self.catalog.manifest.relations.values():
            metadata = schema_metadata.get(relation.name, {})

            for column in relation.columns.values():
                description = self._column_description(
                    metadata,
                    column.name,
                )

                cards.append(
                    ColumnCard(
                        card_id=(f"column:{relation.schema_name}.{relation.name}.{column.name}"),
                        domain=self._domain(relation.name),
                        card_name=column.name,
                        card_description=description,
                        schema_name=relation.schema_name,
                        table_name=relation.name,
                        column_name=column.name,
                        data_type=column.data_type,
                        description=description,
                        is_pii=column.is_pii,
                    ),
                )

        return cards

    def build_metric_cards(self) -> list[MetricCard]:
        return [
            MetricCard(
                card_id=f"metric:{metric.name}",
                domain=self._metric_domain(metric.tables),
                card_name=metric.label,
                card_description=metric.definition,
                name=metric.name,
                label=metric.label,
                definition=metric.definition,
                sql=metric.sql,
                filters=metric.filters,
                grain=metric.grain,
                caveats=metric.caveats,
                tables=metric.tables,
            )
            for metric in self.catalog.metrics
        ]

    def _load_schema_metadata(self) -> dict[str, dict[str, Any]]:
        payload = yaml.safe_load(
            self.schema_path.read_text(encoding="utf-8"),
        )

        return {model["name"]: model for model in payload.get("models", [])}

    @staticmethod
    def _column_description(
        metadata: dict[str, Any],
        column_name: str,
    ) -> str:
        for column in metadata.get("columns", []):
            if column.get("name") == column_name:
                return column.get("description", "")

        return ""

    @staticmethod
    def _relationships(
        table_name: str,
        metadata: dict[str, Any],
    ) -> list[Relationship]:
        relationships: list[Relationship] = []

        for column in metadata.get("columns", []):
            from_column = column["name"]

            for test in column.get("tests", []):
                if not isinstance(test, dict):
                    continue

                relationship_test = test.get("relationships")
                if relationship_test is None:
                    continue

                arguments = relationship_test.get("arguments", {})
                target = arguments.get("to")
                target_column = arguments.get("field")

                if not target or not target_column:
                    continue

                target_table = SchemaCardBuilder._ref_name(target)

                relationships.append(
                    Relationship(
                        from_table=table_name,
                        from_column=from_column,
                        to_table=target_table,
                        to_column=target_column,
                    ),
                )

        return relationships

    @staticmethod
    def _ref_name(value: str) -> str:
        if value.startswith("ref('") and value.endswith("')"):
            return value[5:-2]

        return value

    @staticmethod
    def _domain(table_name: str) -> str:
        mapping = {
            "fct_orders": "orders",
            "fct_order_items": "orders",
            "fct_reviews": "reviews",
            "fct_payments": "orders",
            "dim_customer": "customers",
            "dim_products": "products",
            "dim_sellers": "sellers",
            "dim_geography": "geography",
            "dim_date": "orders",
            "agg_customer_lifetime": "customers",
            "agg_daily_revenue": "orders",
            "agg_seller_performance": "sellers",
        }

        return mapping.get(table_name, "unknown")

    def _metric_domain(self, tables: list[str]) -> str:
        if not tables:
            return "unknown"

        table_name = tables[0].split(".")[-1]
        return self._domain(table_name)
