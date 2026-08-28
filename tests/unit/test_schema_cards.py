from pathlib import Path

from cardinal.catalog.cards import ColumnCard, ColumnSummary, MetricCard, SampleRow, TableCard
from cardinal.catalog.manifest import load_metrics


def test_table_card_to_text() -> None:
    card = TableCard(
        card_id="table:marts.fct_orders",
        domain="orders",
        card_name="fct_orders",
        card_description="Order-level fact table.",
        schema_name="marts",
        table_name="fct_orders",
        grain="one row per order",
        row_count=100,
        columns=[
            ColumnSummary(
                name="order_id",
                data_type="text",
                description="Unique order identifier.",
            ),
            ColumnSummary(
                name="order_status",
                data_type="text",
                description="Current order status.",
            ),
        ],
        relationships=[],
        metrics=["revenue", "order_count"],
        sample_rows=[
            SampleRow(
                values={
                    "order_status": "delivered",
                },
            ),
        ],
    )

    text = card.to_text()

    assert "TABLE: marts.fct_orders" in text
    assert "DOMAIN: orders" in text
    assert "Order-level fact table." in text
    assert "GRAIN: one row per order" in text
    assert "ROW COUNT: 100" in text
    assert "order_id" in text
    assert "Unique order identifier." in text
    assert "revenue" in text
    assert "order_count" in text
    assert "delivered" in text


def test_column_card_to_text() -> None:
    card = ColumnCard(
        card_id="column:marts.fct_orders.order_status",
        domain="orders",
        card_name="order_status",
        card_description="Current order status.",
        schema_name="marts",
        table_name="fct_orders",
        column_name="order_status",
        data_type="text",
        description="Current order status.",
        null_rate=0.05,
        distinct_count=8,
        top_values=["delivered", "shipped", "canceled"],
    )

    text = card.to_text()

    assert "COLUMN: marts.fct_orders.order_status" in text
    assert "DOMAIN: orders" in text
    assert "Current order status." in text
    assert "DATA TYPE: text" in text
    assert "NULL RATE: 0.05" in text
    assert "DISTINCT COUNT: 8" in text
    assert "delivered" in text
    assert "shipped" in text
    assert "canceled" in text


def test_metric_card_to_text() -> None:
    card = MetricCard(
        card_id="metric:revenue",
        domain="orders",
        card_name="Revenue",
        card_description="Total calculated order value.",
        name="revenue",
        label="Revenue",
        definition="Total calculated order value.",
        sql="SUM(calculated_order_value)",
        filters=["calculated_order_value IS NOT NULL"],
        grain="order",
        caveats="Excludes orders without order-item records.",
        tables=["marts.fct_orders"],
    )

    text = card.to_text()

    assert "METRIC: Revenue" in text
    assert "DOMAIN: orders" in text
    assert "Total calculated order value." in text
    assert "SUM(calculated_order_value)" in text
    assert "order" in text
    assert "marts.fct_orders" in text
    assert "Excludes orders without order-item records." in text


def test_metric_loads_explicit_table_dependencies() -> None:
    metrics_path = Path("warehouse/semantic/metrics.yml")

    metrics = load_metrics(metrics_path)

    revenue = next(metric for metric in metrics if metric.name == "revenue")
    avg_review_score = next(metric for metric in metrics if metric.name == "avg_review_score")

    assert revenue.tables == ["marts.fct_orders"]
    assert avg_review_score.tables == ["marts.fct_reviews"]


def test_all_metrics_have_explicit_table_dependencies() -> None:
    metrics_path = Path("warehouse/semantic/metrics.yml")

    metrics = load_metrics(metrics_path)

    assert len(metrics) == 20
    assert all(metric.tables for metric in metrics)
