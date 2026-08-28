from unittest.mock import Mock

from cardinal.catalog.cards import ColumnCard, TableCard
from cardinal.retrieval.postgres import PostgresCardStore


def test_store_uses_configured_engine() -> None:
    engine = Mock()

    store = PostgresCardStore(engine=engine)

    assert store.engine is engine


def test_metadata_for_table_card() -> None:
    card = TableCard(
        card_id="table:marts.fct_orders",
        domain="orders",
        card_name="fct_orders",
        card_description="Orders.",
        schema_name="marts",
        table_name="fct_orders",
        row_count=100,
    )

    metadata = PostgresCardStore._metadata(card)

    assert '"schema_name":"marts"' in metadata
    assert '"table_name":"fct_orders"' in metadata


def test_metadata_for_column_card() -> None:
    card = ColumnCard(
        card_id="column:marts.fct_orders.order_id",
        domain="orders",
        card_name="order_id",
        card_description="Order identifier.",
        schema_name="marts",
        table_name="fct_orders",
        column_name="order_id",
        data_type="text",
        is_pii=True,
    )

    metadata = PostgresCardStore._metadata(card)

    assert '"column_name":"order_id"' in metadata
    assert '"is_pii":true' in metadata


def test_metadata_for_metric_card() -> None:
    from cardinal.catalog.cards import MetricCard

    card = MetricCard(
        card_id="metric:gmv",
        domain="orders",
        card_name="GMV",
        card_description="Gross merchandise value.",
        name="gmv",
        label="GMV",
        definition="Gross merchandise value.",
        sql="SUM(price)",
        grain="day",
        caveats="Refunds excluded.",
        tables=["marts.fct_orders"],
    )

    metadata = PostgresCardStore._metadata(card)

    assert '"name":"gmv"' in metadata
    assert '"tables":["marts.fct_orders"]' in metadata
