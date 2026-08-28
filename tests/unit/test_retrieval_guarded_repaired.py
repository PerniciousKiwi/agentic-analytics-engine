from pathlib import Path
from unittest.mock import MagicMock

from eval.systems.retrieval_guarded_repaired import (
    RetrievalGuardedRepairedSystem,
)

from cardinal.agent.repair import FailureClass
from cardinal.catalog.models import Metric
from cardinal.guardrails.semantic_check import check_canonical_metric
from cardinal.retrieval.models import RetrievalResponse, RetrievalResult


def _result(
    card_id: str,
    card_type: str = "table",
) -> RetrievalResult:
    return RetrievalResult(
        card_id=card_id,
        card_type=card_type,
        domain="orders",
        card_name=card_id,
        card_text=f"CARD: {card_id}",
        score=1.0,
    )


def _system() -> RetrievalGuardedRepairedSystem:
    system = object.__new__(RetrievalGuardedRepairedSystem)

    system.retrieval = MagicMock()
    system.context_assembler = MagicMock()
    system.client = MagicMock()
    system.loop = MagicMock()

    system.catalog = MagicMock()
    system.catalog.metrics = []

    system.prompt_template = MagicMock()
    system.repair_template = MagicMock()

    system.temperature = 0.0
    system.max_output_tokens = 100
    system.prompt_hash = "test-prompt-hash"
    system._last_context = None

    return system


def test_generate_sql_uses_retrieved_context() -> None:
    system = _system()

    retrieval_response = RetrievalResponse(
        query="total revenue",
        mode="hybrid",
        results=[
            _result("table:marts.fct_orders"),
            _result("column:marts.fct_orders.calculated_order_value", "column"),
        ],
    )

    context = MagicMock()
    context.schema = "TABLE: marts.fct_orders"
    context.metrics = "Metric: revenue"
    context.card_ids = (
        "table:marts.fct_orders",
        "column:marts.fct_orders.calculated_order_value",
    )
    context.token_count = 25

    llm_response = MagicMock()
    llm_response.text = "SELECT SUM(calculated_order_value) FROM marts.fct_orders;"
    llm_response.tokens_in = 100
    llm_response.tokens_out = 20
    llm_response.latency_ms = 50.0
    llm_response.attempts = 1
    llm_response.retried = False

    system.retrieval.retrieve.return_value = retrieval_response
    system.context_assembler.assemble.return_value = context
    system.prompt_template.render.return_value = "rendered retrieval prompt"

    system.loop.run_until_complete.return_value = llm_response

    sql, metadata = system._generate_sql(
        "total revenue",
        {"source": "postgres"},
    )

    assert sql == "SELECT SUM(calculated_order_value) FROM marts.fct_orders;"

    system.retrieval.retrieve.assert_called_once_with(
        "total revenue",
        mode="hybrid",
        limit=20,
    )

    system.context_assembler.assemble.assert_called_once()

    system.prompt_template.render.assert_called_once_with(
        schema_context="TABLE: marts.fct_orders",
        metrics_context="Metric: revenue",
        question="total revenue",
        sql_dialect="PostgreSQL",
    )

    assert metadata["retrieval_mode"] == "hybrid"
    assert metadata["retrieved_card_count"] == 2
    assert metadata["context_card_count"] == 2
    assert metadata["context_token_count"] == 25


def test_generate_sql_uses_sqlite_dialect() -> None:
    system = _system()

    retrieval_response = RetrievalResponse(
        query="orders",
        mode="hybrid",
        results=[],
    )

    context = MagicMock()
    context.schema = ""
    context.metrics = ""
    context.card_ids = ()
    context.token_count = 0

    llm_response = MagicMock()
    llm_response.text = "SELECT COUNT(*) FROM orders;"
    llm_response.tokens_in = 10
    llm_response.tokens_out = 5
    llm_response.latency_ms = 10.0
    llm_response.attempts = 1
    llm_response.retried = False

    system.retrieval.retrieve.return_value = retrieval_response
    system.context_assembler.assemble.return_value = context
    system.prompt_template.render.return_value = "rendered prompt"
    system.loop.run_until_complete.return_value = llm_response

    sql, _ = system._generate_sql(
        "orders",
        {
            "source": "sqlite",
            "database_path": Path("test.db"),
        },
    )

    assert sql == "SELECT COUNT(*) FROM orders;"

    system.prompt_template.render.assert_called_once_with(
        schema_context="",
        metrics_context="",
        question="orders",
        sql_dialect="SQLite",
    )


def test_generate_sql_records_retrieved_card_ids() -> None:
    system = _system()

    retrieval_response = RetrievalResponse(
        query="orders",
        mode="hybrid",
        results=[
            _result("table:marts.fct_orders"),
            _result("table:marts.fct_reviews"),
        ],
    )

    context = MagicMock()
    context.schema = "schema"
    context.metrics = ""
    context.card_ids = ("table:marts.fct_orders",)
    context.token_count = 10

    llm_response = MagicMock()
    llm_response.text = "SELECT 1;"
    llm_response.tokens_in = 10
    llm_response.tokens_out = 5
    llm_response.latency_ms = 10.0
    llm_response.attempts = 1
    llm_response.retried = False

    system.retrieval.retrieve.return_value = retrieval_response
    system.context_assembler.assemble.return_value = context
    system.prompt_template.render.return_value = "prompt"
    system.loop.run_until_complete.return_value = llm_response

    _, metadata = system._generate_sql(
        "orders",
        {"source": "postgres"},
    )

    assert metadata["retrieved_card_ids"] == [
        "table:marts.fct_orders",
        "table:marts.fct_reviews",
    ]


def test_repair_sql_uses_last_retrieved_context() -> None:
    system = _system()

    context = MagicMock()
    context.schema = "TABLE: marts.fct_orders"
    context.metrics = "Metric: revenue"
    context.card_ids = ("table:marts.fct_orders",)
    context.token_count = 20

    system._last_context = context

    system.repair_template.render.return_value = "repair prompt"

    llm_response = MagicMock()
    llm_response.text = "SELECT SUM(calculated_order_value) FROM marts.fct_orders;"

    system.loop.run_until_complete.return_value = llm_response

    result = system._repair_sql(
        question="What is total revenue?",
        failed_sql="SELECT SUM(revenue) FROM marts.fct_orders;",
        failure_class=FailureClass.UNKNOWN_COLUMN,
        error_message="UNKNOWN_COLUMN: revenue",
        candidates=["calculated_order_value"],
        cost_budget=100.0,
        db_context={"source": "postgres"},
    )

    assert result == ("SELECT SUM(calculated_order_value) FROM marts.fct_orders;")

    system.repair_template.render.assert_called_once_with(
        schema_dump="TABLE: marts.fct_orders",
        metrics_context="Metric: revenue",
        question="What is total revenue?",
        sql_dialect="PostgreSQL",
        failed_sql="SELECT SUM(revenue) FROM marts.fct_orders;",
        failure_class="UNKNOWN_COLUMN",
        error_message="UNKNOWN_COLUMN: revenue",
        candidates=["calculated_order_value"],
        cost_budget=100.0,
    )


def test_generate_sql_rejects_unknown_source() -> None:
    system = _system()

    try:
        system._generate_sql(
            "orders",
            {"source": "unknown"},
        )
    except ValueError as exc:
        assert "Unsupported evaluation source" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_canonical_metric_guard_rejects_percentage_scaling() -> None:
    metric = Metric(
        name="delivered_order_rate",
        label="Delivered Order Rate",
        definition="Share of orders that have a delivered customer timestamp.",
        sql=(
            "COUNT(*) FILTER "
            "(WHERE order_delivered_customer_date IS NOT NULL)::numeric "
            "/ NULLIF(COUNT(*), 0)"
        ),
        filters=[],
        grain="order",
        caveats="",
        tables=["marts.fct_orders"],
    )

    sql = (
        "SELECT "
        "(COUNT(*) FILTER "
        "(WHERE order_delivered_customer_date IS NOT NULL)::numeric "
        "/ NULLIF(COUNT(*), 0)) * 100 AS delivered_order_rate "
        "FROM marts.fct_orders;"
    )

    result = check_canonical_metric(sql, [metric])

    assert result.allowed is False
    assert result.reasons == [
        "CANONICAL_METRIC_MISMATCH: "
        "metric 'delivered_order_rate' was transformed "
        "instead of using its canonical calculation exactly",
    ]
