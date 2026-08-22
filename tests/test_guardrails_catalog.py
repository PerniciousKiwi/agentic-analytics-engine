from pathlib import Path

from cardinal.catalog.catalog import Catalog
from cardinal.guardrails.catalog_check import check_catalog

CATALOG = Catalog.load(
    Path("warehouse/target/manifest.json"),
    Path("warehouse/semantic/metrics.yml"),
    Path("warehouse/semantic/glossary.yml"),
)


def test_valid_column() -> None:
    result = check_catalog(
        "SELECT order_id FROM marts.fct_orders",
        CATALOG,
    )

    assert result.allowed is True


def test_unknown_table() -> None:
    result = check_catalog(
        "SELECT * FROM marts.fake_table",
        CATALOG,
    )

    assert result.allowed is False
    assert "UNKNOWN_TABLE: fake_table" in result.reasons


def test_unknown_column() -> None:
    result = check_catalog(
        "SELECT fake_column FROM marts.fct_orders",
        CATALOG,
    )

    assert result.allowed is False
    assert "UNKNOWN_COLUMN: fake_column" in result.reasons


def test_ambiguous_column() -> None:
    result = check_catalog(
        """
        SELECT order_id
        FROM marts.fct_orders o
        JOIN marts.fct_order_items i
            ON o.order_id = i.order_id
        """,
        CATALOG,
    )

    assert result.allowed is False
    assert "AMBIGUOUS_COLUMN: order_id" in result.reasons


def test_schema_qualified_invalid_column_is_blocked() -> None:
    result = check_catalog(
        """
        SELECT dim_customer.customer_state
        FROM marts.fct_reviews
        JOIN marts.dim_customer
          ON marts.fct_reviews.customer_id = marts.dim_customer.customer_id
        """,
        CATALOG,
    )

    assert result.allowed is False


def test_unqualified_hallucinated_column_is_blocked() -> None:
    result = check_catalog(
        """
        SELECT AVG(fcalculated_order_value)
        FROM marts.fct_orders
        """,
        CATALOG,
    )

    assert result.allowed is False
    assert "UNKNOWN_COLUMN: fcalculated_order_value" in result.reasons


def test_subquery_alias_shadowing_real_table() -> None:
    result = check_catalog(
        "SELECT x FROM (SELECT 1 AS x) AS dim_customer",
        CATALOG,
    )

    assert result.allowed is True


def test_cte_shadowing_real_table_name() -> None:
    result = check_catalog(
        """
        WITH dim_customer AS (
            SELECT 1 AS y
        )
        SELECT y FROM dim_customer
        """,
        CATALOG,
    )

    assert result.allowed is True
