from pathlib import Path

from cardinal.catalog.catalog import Catalog
from cardinal.guardrails.ast_checks import check_read_only
from cardinal.guardrails.catalog_check import check_catalog
from cardinal.guardrails.cost_check import CostBudget, check_cost
from cardinal.guardrails.join_check import check_cartesian_join
from cardinal.guardrails.limit_check import enforce_limit
from cardinal.guardrails.pii_check import check_pii
from cardinal.guardrails.pipeline import run_guardrails

CATALOG = Catalog.load(
    Path("warehouse/target/manifest.json"),
    Path("warehouse/semantic/metrics.yml"),
    Path("warehouse/semantic/glossary.yml"),
    Path("warehouse/target/catalog.json"),
)


def test_dml_is_blocked() -> None:
    result = check_read_only("DELETE FROM marts.fct_orders")
    assert result.allowed is False


def test_unknown_table_is_blocked() -> None:
    result = check_catalog(
        "SELECT * FROM marts.fake_table",
        CATALOG,
    )
    assert result.allowed is False


def test_unknown_column_is_blocked() -> None:
    result = check_catalog(
        "SELECT fake_column FROM marts.fct_orders",
        CATALOG,
    )
    assert result.allowed is False


def test_ambiguous_column_is_blocked() -> None:
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


def test_limit_is_injected() -> None:
    sql, result = enforce_limit(
        "SELECT * FROM marts.fct_orders",
        100,
    )

    assert result.allowed is True
    assert "LIMIT 100" in sql


def test_limit_is_reduced() -> None:
    sql, result = enforce_limit(
        "SELECT * FROM marts.fct_orders LIMIT 500",
        100,
    )

    assert result.allowed is True
    assert "LIMIT 100" in sql


def test_cross_join_is_blocked() -> None:
    result = check_cartesian_join(
        """
        SELECT *
        FROM marts.fct_orders o
        CROSS JOIN marts.dim_customer c
        """
    )

    assert result.allowed is False


def test_join_without_condition_is_blocked() -> None:
    result = check_cartesian_join(
        """
        SELECT *
        FROM marts.fct_orders o
        JOIN marts.dim_customer c
        """
    )

    assert result.allowed is False


def test_pii_is_blocked_for_analyst() -> None:
    result = check_pii(
        "SELECT customer_id FROM marts.dim_customer",
        CATALOG,
        role="analyst",
    )

    assert result.allowed is False


def test_pii_is_allowed_for_privileged_role() -> None:
    result = check_pii(
        "SELECT customer_id FROM marts.dim_customer",
        CATALOG,
        role="privileged",
    )

    assert result.allowed is True


def test_cost_limit_is_enforced() -> None:
    def explain(sql: str) -> dict:
        return {
            "Plan": {
                "Total Cost": 250.0,
            }
        }

    result = check_cost(
        "SELECT * FROM marts.fct_orders",
        explain,
        CostBudget(max_cost=100.0),
    )

    assert result.allowed is False


def test_pipeline_blocks_read_only_violation() -> None:
    result = run_guardrails(
        "DELETE FROM marts.fct_orders",
        CATALOG,
    )

    assert result.result.allowed is False
    assert result.result.reasons[0].startswith("READ_ONLY_VIOLATION")


def test_pipeline_blocks_unknown_column() -> None:
    result = run_guardrails(
        "SELECT fake_column FROM marts.fct_orders",
        CATALOG,
    )

    assert result.result.allowed is False
    assert result.result.reasons[0] == "UNKNOWN_COLUMN: fake_column"


def test_pipeline_blocks_cartesian_join() -> None:
    result = run_guardrails(
        """
        SELECT *
        FROM marts.fct_orders o
        CROSS JOIN marts.dim_customer c
        """,
        CATALOG,
    )

    assert result.result.allowed is False
    assert result.result.reasons[0] == "CARTESIAN_JOIN: CROSS JOIN"


def test_pipeline_applies_limit() -> None:
    result = run_guardrails(
        "SELECT * FROM marts.fct_orders",
        CATALOG,
        max_rows=100,
    )

    assert result.result.allowed is True
    assert "LIMIT 100" in result.sql


def test_pipeline_can_skip_limit_for_evaluation() -> None:
    result = run_guardrails(
        "SELECT * FROM marts.fct_orders",
        CATALOG,
        max_rows=100,
        enforce_result_limit=False,
    )

    assert result.result.allowed is True
    assert "LIMIT" not in result.sql.upper()
