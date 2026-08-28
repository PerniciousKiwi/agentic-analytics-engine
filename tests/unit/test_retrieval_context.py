from cardinal.catalog.models import Metric
from cardinal.retrieval.context import SchemaContextAssembler
from cardinal.retrieval.models import RetrievalResult


def _result(
    card_id: str,
    card_type: str,
    card_text: str | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        card_id=card_id,
        card_type=card_type,
        domain="orders",
        card_name=card_id,
        card_text=card_text or card_id,
        score=1.0,
    )


def test_column_selection_includes_parent_table() -> None:
    assembler = SchemaContextAssembler()

    results = [
        _result(
            "column:marts.fct_orders.order_id",
            "column",
            "COLUMN: marts.fct_orders.order_id",
        ),
        _result(
            "table:marts.fct_orders",
            "table",
            "TABLE: marts.fct_orders\nRELATIONSHIPS:\n"
            "fct_orders.customer_unique_id -> dim_customer.customer_unique_id",
        ),
    ]

    context = assembler.assemble(results, [])

    assert "table:marts.fct_orders" in context.card_ids
    assert "column:marts.fct_orders.order_id" in context.card_ids
    assert "RELATIONSHIPS:" in context.schema


def test_parent_table_is_added_even_when_column_ranks_first() -> None:
    assembler = SchemaContextAssembler()

    results = [
        _result(
            "column:marts.fct_orders.customer_unique_id",
            "column",
        ),
        _result(
            "table:marts.fct_orders",
            "table",
            "TABLE: marts.fct_orders",
        ),
    ]

    context = assembler.assemble(results, [])

    assert context.card_ids[:2] == (
        "table:marts.fct_orders",
        "column:marts.fct_orders.customer_unique_id",
    )


def test_duplicate_cards_are_removed() -> None:
    assembler = SchemaContextAssembler()

    result = _result(
        "table:marts.fct_orders",
        "table",
    )

    context = assembler.assemble(
        [result, result],
        [],
    )

    assert context.card_ids == ("table:marts.fct_orders",)


def test_multiple_columns_share_one_parent_table() -> None:
    assembler = SchemaContextAssembler()

    results = [
        _result(
            "column:marts.fct_orders.order_id",
            "column",
        ),
        _result(
            "column:marts.fct_orders.order_status",
            "column",
        ),
        _result(
            "table:marts.fct_orders",
            "table",
        ),
    ]

    context = assembler.assemble(results, [])

    assert context.card_ids.count("table:marts.fct_orders") == 1
    assert "column:marts.fct_orders.order_id" in context.card_ids
    assert "column:marts.fct_orders.order_status" in context.card_ids


def test_max_tables_is_respected() -> None:
    assembler = SchemaContextAssembler()

    results = [
        _result("table:marts.fct_orders", "table"),
        _result("table:marts.dim_customer", "table"),
        _result("table:marts.dim_products", "table"),
    ]

    assembler.max_tables = 2

    context = assembler.assemble(results, [])

    assert (
        len(
            {
                card_id.removeprefix("table:")
                for card_id in context.card_ids
                if card_id.startswith("table:")
            },
        )
        == 2
    )


def test_metrics_are_preserved() -> None:
    assembler = SchemaContextAssembler()

    context = assembler.assemble([], [])

    assert context.metrics == ""
    assert context.card_ids == ()


def test_select_metrics_prefers_exact_metric_name() -> None:
    metrics = [
        Metric(
            name="revenue",
            label="Revenue",
            definition="Total calculated order value.",
            sql="SUM(calculated_order_value)",
            filters=[],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
        Metric(
            name="gmv",
            label="GMV",
            definition="Total merchandise value before freight.",
            sql="SUM(item_value)",
            filters=[],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
    ]

    selected = SchemaContextAssembler.select_metrics(
        "What is the total GMV across all orders?",
        metrics,
    )

    assert selected[0].name == "gmv"


def test_select_metrics_prefers_metric_label() -> None:
    metrics = [
        Metric(
            name="revenue",
            label="Revenue",
            definition="Total calculated order value.",
            sql="SUM(calculated_order_value)",
            filters=[],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
        Metric(
            name="cancelled_order_rate",
            label="Cancelled Order Rate",
            definition="Share of orders with order status equal to canceled.",
            sql="COUNT(*) FILTER (WHERE order_status = 'canceled')",
            filters=[],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
    ]

    selected = SchemaContextAssembler.select_metrics(
        "What percentage of orders were cancelled?",
        metrics,
    )

    assert selected[0].name == "cancelled_order_rate"


def test_select_metrics_prefers_on_time_delivery_rate() -> None:
    metrics = [
        Metric(
            name="delivered_order_rate",
            label="Delivered Order Rate",
            definition="Share of orders delivered to the customer.",
            sql="COUNT(*) FILTER (WHERE order_delivered_customer_date IS NOT NULL)",
            filters=[],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
        Metric(
            name="late_delivery_rate",
            label="Late Delivery Rate",
            definition="Share of eligible orders delivered late.",
            sql="AVG(CASE WHEN delivery_delay_days > 0 THEN 1.0 ELSE 0.0 END)",
            filters=["delivery_delay_days IS NOT NULL"],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
        Metric(
            name="on_time_delivery_rate",
            label="On-Time Delivery Rate",
            definition="Share of eligible orders delivered on or before the promised date.",
            sql="AVG(CASE WHEN delivery_delay_days <= 0 THEN 1.0 ELSE 0.0 END)",
            filters=["delivery_delay_days IS NOT NULL"],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
    ]

    selected = SchemaContextAssembler.select_metrics(
        "What percentage of eligible orders were delivered on time?",
        metrics,
    )

    assert [metric.name for metric in selected] == [
        "on_time_delivery_rate",
    ]


def test_select_metrics_matches_freight_ratio_from_definition() -> None:
    metrics = [
        Metric(
            name="aov",
            label="Average Order Value",
            definition="Average calculated order value.",
            sql="AVG(calculated_order_value)",
            filters=[],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
        Metric(
            name="freight_ratio",
            label="Freight Ratio",
            definition="Proportion of calculated order value made up of freight.",
            sql="SUM(freight_value) / NULLIF(SUM(calculated_order_value), 0)",
            filters=["calculated_order_value IS NOT NULL"],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
    ]

    selected = SchemaContextAssembler.select_metrics(
        "What proportion of calculated order value was made up of freight?",
        metrics,
    )

    assert [metric.name for metric in selected] == ["freight_ratio"]


def test_select_metrics_matches_reviews_rate_from_definition() -> None:
    metrics = [
        Metric(
            name="avg_review_score",
            label="Average Review Score",
            definition="Average customer review score.",
            sql="AVG(review_score)",
            filters=[],
            grain="order",
            caveats="",
            tables=["marts.fct_reviews"],
        ),
        Metric(
            name="orders_with_reviews_rate",
            label="Orders With Reviews Rate",
            definition="Share of orders with at least one customer review.",
            sql="COUNT(*) FILTER (WHERE review_count > 0)::numeric / NULLIF(COUNT(*), 0)",
            filters=[],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
    ]

    selected = SchemaContextAssembler.select_metrics(
        "What percentage of orders have at least one customer review?",
        metrics,
    )

    assert [metric.name for metric in selected] == ["orders_with_reviews_rate"]


def test_select_metrics_matches_repeat_customer_rate_from_definition() -> None:
    metrics = [
        Metric(
            name="new_customers",
            label="New Customers",
            definition="Number of customers whose first observed order occurred in the period.",
            sql="COUNT(*)",
            filters=[],
            grain="customer",
            caveats="",
            tables=["marts.agg_customer_lifetime"],
        ),
        Metric(
            name="repeat_customer_rate",
            label="Repeat Customer Rate",
            definition="Share of business customers who have placed more than one order.",
            sql="COUNT(*) FILTER (WHERE total_orders > 1)::numeric / NULLIF(COUNT(*), 0)",
            filters=[],
            grain="customer",
            caveats="",
            tables=["marts.agg_customer_lifetime"],
        ),
    ]

    selected = SchemaContextAssembler.select_metrics(
        "What percentage of business customers have placed more than one order?",
        metrics,
    )

    assert [metric.name for metric in selected] == ["repeat_customer_rate"]


def test_select_metrics_matches_revenue_per_state_from_definition() -> None:
    metrics = [
        Metric(
            name="revenue",
            label="Revenue",
            definition="Total revenue.",
            sql="SUM(calculated_order_value)",
            filters=[],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
        Metric(
            name="revenue_per_state",
            label="Revenue Per State",
            definition="Average revenue per order for customers in a state.",
            sql="SUM(calculated_order_value) / NULLIF(COUNT(DISTINCT order_id), 0)",
            filters=["calculated_order_value IS NOT NULL"],
            grain="order",
            caveats="",
            tables=["marts.fct_orders"],
        ),
    ]

    selected = SchemaContextAssembler.select_metrics(
        "What was the average revenue per order for customers in SÃ£o Paulo state?",
        metrics,
    )

    assert [metric.name for metric in selected] == ["revenue_per_state"]
