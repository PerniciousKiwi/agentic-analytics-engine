from unittest.mock import Mock

from cardinal.catalog.cards import ColumnCard, TableCard
from cardinal.catalog.profiler import CardProfiler


def test_profile_table_sets_row_count() -> None:
    reader = Mock()
    reader.fetch_scalar.return_value = 123

    profiler = CardProfiler(reader)

    card = TableCard(
        card_id="table:marts.fct_orders",
        domain="orders",
        card_name="fct_orders",
        card_description="Orders.",
        schema_name="marts",
        table_name="fct_orders",
        row_count=0,
    )

    result = profiler.profile_table(card)

    assert result.row_count == 123
    reader.fetch_scalar.assert_called_once()


def test_profile_column_sets_statistics() -> None:
    reader = Mock()

    reader.fetch_all.side_effect = [
        [{"null_rate": 0.05, "distinct_count": 8}],
        [
            {"value": "delivered", "count": 100},
            {"value": "shipped", "count": 50},
        ],
    ]

    profiler = CardProfiler(reader)

    card = ColumnCard(
        card_id="column:marts.fct_orders.order_status",
        domain="orders",
        card_name="order_status",
        card_description="Order status.",
        schema_name="marts",
        table_name="fct_orders",
        column_name="order_status",
        data_type="text",
    )

    result = profiler.profile_column(card)

    assert result.null_rate == 0.05
    assert result.distinct_count == 8
    assert result.top_values == ["delivered", "shipped"]
    assert result.min_value is None
    assert result.max_value is None

    assert reader.fetch_all.call_count == 2


def test_profile_numeric_column_sets_min_max() -> None:
    reader = Mock()

    reader.fetch_all.side_effect = [
        [{"null_rate": 0.01, "distinct_count": 100}],
        [
            {"value": 10, "count": 50},
            {"value": 20, "count": 25},
        ],
        [{"min_value": 1, "max_value": 999}],
    ]

    profiler = CardProfiler(reader)

    card = ColumnCard(
        card_id="column:marts.fct_orders.item_value",
        domain="orders",
        card_name="item_value",
        card_description="Item value.",
        schema_name="marts",
        table_name="fct_orders",
        column_name="item_value",
        data_type="numeric",
    )

    result = profiler.profile_column(card)

    assert result.min_value == 1
    assert result.max_value == 999


def test_profile_high_cardinality_column_skips_top_values() -> None:
    reader = Mock()

    reader.fetch_all.side_effect = [
        [{"null_rate": 0.0, "distinct_count": 100}],
    ]

    profiler = CardProfiler(reader)

    card = ColumnCard(
        card_id="column:marts.fct_orders.order_id",
        domain="orders",
        card_name="order_id",
        card_description="Order identifier.",
        schema_name="marts",
        table_name="fct_orders",
        column_name="order_id",
        data_type="text",
    )

    result = profiler.profile_column(card)

    assert result.distinct_count == 100
    assert result.top_values == []
    assert result.min_value is None
    assert result.max_value is None

    reader.fetch_all.assert_called_once()


def test_profile_pii_column_does_not_fetch_values() -> None:
    reader = Mock()

    reader.fetch_all.return_value = [
        {"null_rate": 0.0, "distinct_count": 100},
    ]

    profiler = CardProfiler(reader)

    card = ColumnCard(
        card_id="column:marts.dim_customer.customer_id",
        domain="customers",
        card_name="customer_id",
        card_description="Customer identifier.",
        schema_name="marts",
        table_name="dim_customer",
        column_name="customer_id",
        data_type="text",
        is_pii=True,
    )

    result = profiler.profile_column(card)

    assert result.null_rate == 0.0
    assert result.distinct_count == 100
    assert result.top_values == []
    assert result.min_value is None
    assert result.max_value is None

    assert reader.fetch_all.call_count == 1


def test_profile_pii_column_does_not_include_column_values_in_sql() -> None:
    reader = Mock()
    reader.fetch_all.return_value = [
        {"null_rate": 0.0, "distinct_count": 100},
    ]

    profiler = CardProfiler(reader)

    card = ColumnCard(
        card_id="column:marts.dim_customer.customer_unique_id",
        domain="customers",
        card_name="customer_unique_id",
        card_description="Customer identifier.",
        schema_name="marts",
        table_name="dim_customer",
        column_name="customer_unique_id",
        data_type="text",
        is_pii=True,
    )

    profiler.profile_column(card)

    assert reader.fetch_all.call_count == 1

    sql = reader.fetch_all.call_args.args[0]

    assert "customer_unique_id" in sql
    assert "GROUP BY" not in sql
    assert "LIMIT" not in sql


def test_profile_table_adds_safe_sample_rows() -> None:
    from cardinal.catalog.cards import ColumnSummary

    reader = Mock()

    reader.fetch_scalar.return_value = 123

    reader.fetch_all.return_value = [
        {
            "order_id": "1001",
            "order_status": "delivered",
        },
        {
            "order_id": "1002",
            "order_status": "shipped",
        },
        {
            "order_id": "1003",
            "order_status": "canceled",
        },
    ]

    profiler = CardProfiler(reader)

    card = TableCard(
        card_id="table:marts.fct_orders",
        domain="orders",
        card_name="fct_orders",
        card_description="Orders.",
        schema_name="marts",
        table_name="fct_orders",
        row_count=0,
        columns=[
            ColumnSummary(
                name="order_id",
                data_type="text",
                description="Order identifier.",
                is_pii=True,
            ),
            ColumnSummary(
                name="order_status",
                data_type="text",
                description="Order status.",
            ),
        ],
    )

    result = profiler.profile_table(card)

    assert len(result.sample_rows) == 3
    assert result.sample_rows[0].values == {
        "order_status": "delivered",
    }


def test_supports_min_max_only_for_numeric_and_date_types() -> None:
    assert CardProfiler._supports_min_max("numeric")
    assert CardProfiler._supports_min_max("integer")
    assert CardProfiler._supports_min_max("bigint")
    assert CardProfiler._supports_min_max("date")
    assert CardProfiler._supports_min_max("timestamp without time zone")

    assert not CardProfiler._supports_min_max("text")
    assert not CardProfiler._supports_min_max("varchar")
    assert not CardProfiler._supports_min_max("boolean")
