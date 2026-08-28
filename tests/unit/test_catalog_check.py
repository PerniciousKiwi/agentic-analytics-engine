import pytest

from cardinal.catalog.catalog import Catalog
from cardinal.catalog.manifest import Column, Manifest, Relation
from cardinal.catalog.models import Glossary
from cardinal.guardrails.catalog_check import check_catalog


@pytest.fixture
def catalog() -> Catalog:
    relation = Relation(
        unique_id="model.marts.fct_orders",
        name="fct_orders",
        schema_name="marts",
        database=None,
        resource_type="model",
        columns={
            "order_id": Column(name="order_id"),
            "order_purchase_timestamp": Column(
                name="order_purchase_timestamp",
            ),
            "customer_unique_id": Column(
                name="customer_unique_id",
            ),
        },
    )

    revenue_relation = Relation(
        unique_id="model.marts.agg_daily_revenue",
        name="agg_daily_revenue",
        schema_name="marts",
        database=None,
        resource_type="model",
        columns={
            "date_day": Column(name="date_day"),
            "revenue": Column(name="revenue"),
        },
    )

    return Catalog(
        manifest=Manifest(
            relations={
                relation.unique_id: relation,
                revenue_relation.unique_id: revenue_relation,
            },
        ),
        metrics=[],
        glossary=Glossary(
            version=1,
            glossary={},
            pii_columns=[],
        ),
    )


def test_cte_output_column_is_not_unknown(catalog: Catalog) -> None:
    sql = """
        WITH monthly AS (
            SELECT
                DATE_TRUNC('month', order_purchase_timestamp) AS month
            FROM marts.fct_orders
        )
        SELECT month
        FROM monthly
    """

    result = check_catalog(sql, catalog)

    assert result.allowed, result.reasons


def test_cte_derived_alias_is_not_unknown(catalog: Catalog) -> None:
    sql = """
        WITH orders AS (
            SELECT
                order_purchase_timestamp AS order_date
            FROM marts.fct_orders
        )
        SELECT order_date
        FROM orders
    """

    result = check_catalog(sql, catalog)

    assert result.allowed, result.reasons


def test_window_alias_is_not_unknown(catalog: Catalog) -> None:
    sql = """
        SELECT
            date_day,
            RANK() OVER (ORDER BY revenue DESC) AS rank
        FROM marts.agg_daily_revenue
    """

    result = check_catalog(sql, catalog)

    assert result.allowed, result.reasons


def test_unknown_physical_column_is_rejected(catalog: Catalog) -> None:
    sql = """
        SELECT definitely_not_a_column
        FROM marts.fct_orders
    """

    result = check_catalog(sql, catalog)

    assert not result.allowed
    assert any(reason.startswith("UNKNOWN_COLUMN") for reason in result.reasons)


def test_unknown_table_is_rejected(catalog: Catalog) -> None:
    sql = """
        SELECT *
        FROM marts.definitely_not_a_table
    """

    result = check_catalog(sql, catalog)

    assert not result.allowed
    assert any(reason.startswith("UNKNOWN_TABLE") for reason in result.reasons)
