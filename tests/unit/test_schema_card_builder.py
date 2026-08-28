from pathlib import Path

from cardinal.catalog.builder import SchemaCardBuilder
from cardinal.catalog.cards import ColumnCard, MetricCard, TableCard
from cardinal.catalog.catalog import Catalog


def test_build_table_cards() -> None:
    catalog = Catalog.load(
        manifest_path=Path("warehouse/target/manifest.json"),
        metrics_path=Path("warehouse/semantic/metrics.yml"),
        glossary_path=Path("warehouse/semantic/glossary.yml"),
        catalog_path=Path("warehouse/target/catalog.json"),
    )

    builder = SchemaCardBuilder(
        catalog=catalog,
        schema_path=Path("warehouse/models/schema.yml"),
    )

    cards = builder.build_table_cards()

    orders = next(card for card in cards if card.table_name == "fct_orders")

    assert orders.card_id == "table:marts.fct_orders"
    assert orders.domain == "orders"
    assert orders.card_description == "Order-level fact table."
    assert orders.row_count == 0

    order_id = next(column for column in orders.columns if column.name == "order_id")

    assert order_id.data_type == "text"
    assert order_id.description == "Unique identifier for an order."

    assert any(
        relationship.from_column == "customer_unique_id"
        and relationship.to_table == "dim_customer"
        and relationship.to_column == "customer_unique_id"
        for relationship in orders.relationships
    )

    assert "revenue" in orders.metrics


def test_build_column_cards_preserves_pii() -> None:
    catalog = Catalog.load(
        manifest_path=Path("warehouse/target/manifest.json"),
        metrics_path=Path("warehouse/semantic/metrics.yml"),
        glossary_path=Path("warehouse/semantic/glossary.yml"),
        catalog_path=Path("warehouse/target/catalog.json"),
    )

    builder = SchemaCardBuilder(
        catalog=catalog,
        schema_path=Path("warehouse/models/schema.yml"),
    )

    cards = builder.build_column_cards()

    customer_id = next(
        card
        for card in cards
        if (
            isinstance(card, ColumnCard)
            and card.table_name == "dim_customer"
            and card.column_name == "customer_id"
        )
    )

    assert customer_id.is_pii is True


def test_build_metric_cards_preserves_dependencies() -> None:
    catalog = Catalog.load(
        manifest_path=Path("warehouse/target/manifest.json"),
        metrics_path=Path("warehouse/semantic/metrics.yml"),
        glossary_path=Path("warehouse/semantic/glossary.yml"),
        catalog_path=Path("warehouse/target/catalog.json"),
    )

    builder = SchemaCardBuilder(
        catalog=catalog,
        schema_path=Path("warehouse/models/schema.yml"),
    )

    cards = builder.build_metric_cards()

    revenue = next(
        card for card in cards if isinstance(card, MetricCard) and card.name == "revenue"
    )

    avg_review_score = next(
        card for card in cards if isinstance(card, MetricCard) and card.name == "avg_review_score"
    )

    assert revenue.tables == ["marts.fct_orders"]
    assert avg_review_score.tables == ["marts.fct_reviews"]


def test_build_all_returns_all_card_types() -> None:
    catalog = Catalog.load(
        manifest_path=Path("warehouse/target/manifest.json"),
        metrics_path=Path("warehouse/semantic/metrics.yml"),
        glossary_path=Path("warehouse/semantic/glossary.yml"),
        catalog_path=Path("warehouse/target/catalog.json"),
    )

    builder = SchemaCardBuilder(
        catalog=catalog,
        schema_path=Path("warehouse/models/schema.yml"),
    )

    cards = builder.build_all()

    assert any(isinstance(card, TableCard) for card in cards)
    assert any(isinstance(card, ColumnCard) for card in cards)
    assert any(isinstance(card, MetricCard) for card in cards)
