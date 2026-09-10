import asyncio
import json
from unittest.mock import MagicMock

import pytest

from cardinal.agent import tools
from cardinal.agent.loop import ToolSpec, run_agent
from cardinal.agent.repair import FailureClass
from cardinal.agent.schemas import ExecuteSqlIn, SearchSchemaIn, SearchSchemaOut
from cardinal.catalog.catalog import Catalog
from cardinal.catalog.manifest import Column, Manifest, Relation
from cardinal.catalog.models import Glossary
from cardinal.guardrails.ast_checks import GuardResult
from cardinal.guardrails.pipeline import GuardrailResult
from cardinal.llm.client import LLMResponse
from cardinal.retrieval.context import RetrievalContext
from cardinal.retrieval.models import RetrievalResponse, RetrievalResult


def _catalog() -> Catalog:
    return Catalog(
        manifest=Manifest(
            relations={
                "model.fct_orders": Relation(
                    unique_id="model.fct_orders",
                    name="fct_orders",
                    schema_name="marts",
                    database=None,
                    resource_type="model",
                    columns={
                        "order_id": Column(
                            name="order_id",
                            data_type="text",
                        ),
                        "customer_id": Column(
                            name="customer_id",
                            data_type="text",
                        ),
                    },
                )
            }
        ),
        metrics=[],
        glossary=Glossary(
            version=1,
            glossary={},
            pii_columns=[],
        ),
    )


def _retrieval_result(
    *,
    card_id: str = "column:marts.fct_orders.customer_id",
    domain: str = "orders",
) -> RetrievalResult:
    return RetrievalResult(
        card_id=card_id,
        card_type="column",
        domain=domain,
        card_name="customer_id",
        card_text=(
            "COLUMN: marts.fct_orders.customer_id\n"
            "DOMAIN: orders\n"
            "Customer identifier.\n"
            "DATA TYPE: text"
        ),
        score=1.0,
        metadata={},
    )


def test_search_schema_uses_existing_retrieval_pipeline(
    monkeypatch,
) -> None:
    retrieval = MagicMock()
    assembler = MagicMock()

    result = _retrieval_result()

    retrieval.retrieve.return_value = RetrievalResponse(
        query="customer orders",
        mode="hybrid",
        results=[result],
    )

    assembler.assemble.return_value = RetrievalContext(
        schema=result.card_text,
        metrics="",
        card_ids=(result.card_id,),
        token_count=20,
    )

    monkeypatch.setattr(
        tools,
        "_get_retrieval_service",
        lambda: retrieval,
    )
    monkeypatch.setattr(
        tools,
        "_get_context_assembler",
        lambda: assembler,
    )

    response = tools.search_schema(
        SearchSchemaIn(
            query="customer orders",
        )
    )

    assert response.error is None
    assert len(response.cards) == 1

    card = response.cards[0]

    assert card.card_type == "column"
    assert card.domain == "orders"
    assert card.name == "customer_id"
    assert card.description == "Customer identifier."
    assert card.data_type == "text"

    retrieval.retrieve.assert_called_once_with(
        "customer orders",
        mode="hybrid",
        limit=20,
    )

    assembler.assemble.assert_called_once_with([result])


def test_search_schema_applies_domain_filter(
    monkeypatch,
) -> None:
    retrieval = MagicMock()
    assembler = MagicMock()

    orders = _retrieval_result(
        card_id="column:marts.fct_orders.customer_id",
        domain="orders",
    )

    customers = _retrieval_result(
        card_id="column:marts.dim_customer.customer_id",
        domain="customers",
    )

    retrieval.retrieve.return_value = RetrievalResponse(
        query="customer",
        mode="hybrid",
        results=[
            orders,
            customers,
        ],
    )

    assembler.assemble.return_value = RetrievalContext(
        schema=customers.card_text,
        metrics="",
        card_ids=(customers.card_id,),
        token_count=10,
    )

    monkeypatch.setattr(
        tools,
        "_get_retrieval_service",
        lambda: retrieval,
    )
    monkeypatch.setattr(
        tools,
        "_get_context_assembler",
        lambda: assembler,
    )

    response = tools.search_schema(
        SearchSchemaIn(
            query="customer",
            domain="customers",
        )
    )

    assert response.error is None
    assert len(response.cards) == 1
    assert response.cards[0].domain == "customers"

    assembler.assemble.assert_called_once_with([customers])


def test_search_schema_converts_exception_to_tool_error(
    monkeypatch,
) -> None:
    retrieval = MagicMock()
    retrieval.retrieve.side_effect = RuntimeError(
        "retrieval unavailable",
    )

    monkeypatch.setattr(
        tools,
        "_get_retrieval_service",
        lambda: retrieval,
    )

    response = tools.search_schema(
        SearchSchemaIn(
            query="orders",
        )
    )

    assert response.cards == []
    assert response.error is not None
    assert response.error.failure_class == FailureClass.OTHER
    assert "retrieval unavailable" in response.error.message


def test_execute_sql_runs_guardrails_before_reader(
    monkeypatch,
) -> None:
    catalog = _catalog()

    guarded = GuardrailResult(
        sql="SELECT customer_id FROM marts.fct_orders LIMIT 3",
        result=GuardResult(
            allowed=True,
            reasons=[],
        ),
    )

    guardrails = MagicMock(return_value=guarded)

    reader = MagicMock()
    reader.fetch_all.return_value = [
        {"customer_id": "c1"},
        {"customer_id": "c2"},
    ]

    reader_context = MagicMock()
    reader_context.__enter__.return_value = reader

    monkeypatch.setattr(
        tools,
        "_get_catalog",
        lambda: catalog,
    )
    monkeypatch.setattr(
        tools,
        "run_guardrails",
        guardrails,
    )
    monkeypatch.setattr(
        tools,
        "WarehouseReader",
        MagicMock(return_value=reader_context),
    )

    response = tools.execute_sql(
        ExecuteSqlIn(
            sql="SELECT customer_id FROM marts.fct_orders",
            row_limit=2,
        )
    )

    assert response.error is None
    assert response.columns == ["customer_id"]
    assert response.rows == [
        ["c1"],
        ["c2"],
    ]
    assert response.row_count == 2
    assert response.truncated is False

    guardrails.assert_called_once_with(
        "SELECT customer_id FROM marts.fct_orders",
        catalog,
        metrics=catalog.metrics,
        role="analyst",
        max_rows=3,
        enforce_result_limit=True,
    )

    reader.fetch_all.assert_called_once_with(
        "SELECT customer_id FROM marts.fct_orders LIMIT 3"
    )


def test_execute_sql_marks_result_as_truncated(
    monkeypatch,
) -> None:
    catalog = _catalog()

    guarded = GuardrailResult(
        sql="SELECT customer_id FROM marts.fct_orders LIMIT 3",
        result=GuardResult(
            allowed=True,
            reasons=[],
        ),
    )

    reader = MagicMock()
    reader.fetch_all.return_value = [
        {"customer_id": "c1"},
        {"customer_id": "c2"},
        {"customer_id": "c3"},
    ]

    reader_context = MagicMock()
    reader_context.__enter__.return_value = reader

    monkeypatch.setattr(
        tools,
        "_get_catalog",
        lambda: catalog,
    )
    monkeypatch.setattr(
        tools,
        "run_guardrails",
        MagicMock(return_value=guarded),
    )
    monkeypatch.setattr(
        tools,
        "WarehouseReader",
        MagicMock(return_value=reader_context),
    )

    response = tools.execute_sql(
        ExecuteSqlIn(
            sql="SELECT customer_id FROM marts.fct_orders",
            row_limit=2,
        )
    )

    assert response.error is None
    assert response.row_count == 2
    assert response.truncated is True

    assert response.rows == [
        ["c1"],
        ["c2"],
    ]


def test_execute_sql_returns_guardrail_failure(
    monkeypatch,
) -> None:
    catalog = _catalog()

    guarded = GuardrailResult(
        sql="SELECT custmer_id FROM marts.fct_orders",
        result=GuardResult(
            allowed=False,
            reasons=[
                "UNKNOWN_COLUMN: custmer_id",
            ],
        ),
    )

    warehouse_reader = MagicMock()

    monkeypatch.setattr(
        tools,
        "_get_catalog",
        lambda: catalog,
    )
    monkeypatch.setattr(
        tools,
        "run_guardrails",
        MagicMock(return_value=guarded),
    )
    monkeypatch.setattr(
        tools,
        "WarehouseReader",
        warehouse_reader,
    )

    response = tools.execute_sql(
        ExecuteSqlIn(
            sql="SELECT custmer_id FROM marts.fct_orders",
        )
    )

    assert response.error is not None
    assert response.error.failure_class == FailureClass.UNKNOWN_COLUMN
    assert "fct_orders.customer_id" in response.error.candidates

    warehouse_reader.assert_not_called()


def test_execute_sql_returns_database_failure(
    monkeypatch,
) -> None:
    catalog = _catalog()

    guarded = GuardrailResult(
        sql="SELECT customer_id FROM marts.fct_orders LIMIT 1001",
        result=GuardResult(
            allowed=True,
            reasons=[],
        ),
    )

    class DatabaseError(Exception):
        sqlstate = "42703"

    reader = MagicMock()
    reader.fetch_all.side_effect = DatabaseError(
        'column "custmer_id" does not exist'
    )

    reader_context = MagicMock()
    reader_context.__enter__.return_value = reader

    monkeypatch.setattr(
        tools,
        "_get_catalog",
        lambda: catalog,
    )
    monkeypatch.setattr(
        tools,
        "run_guardrails",
        MagicMock(return_value=guarded),
    )
    monkeypatch.setattr(
        tools,
        "WarehouseReader",
        MagicMock(return_value=reader_context),
    )

    response = tools.execute_sql(
        ExecuteSqlIn(
            sql="SELECT custmer_id FROM marts.fct_orders",
        )
    )

    assert response.error is not None
    assert response.error.failure_class == FailureClass.UNKNOWN_COLUMN
    assert "fct_orders.customer_id" in response.error.candidates


def test_execute_sql_converts_unexpected_exception(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        tools,
        "_get_catalog",
        MagicMock(
            side_effect=RuntimeError(
                "unexpected catalog failure",
            )
        ),
    )

    response = tools.execute_sql(
        ExecuteSqlIn(
            sql="SELECT 1",
        )
    )

    assert response.error is not None
    assert response.error.failure_class == FailureClass.OTHER
    assert "unexpected catalog failure" in response.error.message


def test_schema_summary_does_not_treat_sample_values_as_description() -> None:
    result = RetrievalResult(
        card_id="column:marts.agg_daily_revenue.revenue",
        card_type="column",
        domain="orders",
        card_name="revenue",
        card_text=(
            "COLUMN: marts.agg_daily_revenue.revenue\n"
            "DOMAIN: orders\n"
            "\n"
            "DATA TYPE: numeric\n"
            "TOP VALUES:\n"
            "100.0, 200.0, 300.0"
        ),
        score=1.0,
        metadata={},
    )

    summary = tools._schema_card_summary(result)

    assert summary.description == ""
    assert summary.data_type == "numeric"


def test_schema_summary_does_not_treat_table_columns_as_description() -> None:
    result = RetrievalResult(
        card_id="table:marts.agg_daily_revenue",
        card_type="table",
        domain="orders",
        card_name="agg_daily_revenue",
        card_text=(
            "TABLE: marts.agg_daily_revenue\n"
            "DOMAIN: orders\n"
            "\n"
            "ROW COUNT: 100\n"
            "COLUMNS:\n"
            "date_day: date —"
        ),
        score=1.0,
        metadata={},
    )

    summary = tools._schema_card_summary(result)

    assert summary.description == ""


@pytest.mark.asyncio
async def test_agent_awaits_async_callable_tool_object():
    """Regression: objects with async __call__ must be awaited, not sent to a thread."""

    class AsyncCallableTool:
        def __init__(self) -> None:
            self.call_count = 0
            self.queries: list[str] = []

        async def __call__(
            self,
            request: SearchSchemaIn,
        ) -> SearchSchemaOut:
            self.call_count += 1
            self.queries.append(request.query)

            await asyncio.sleep(0)

            return SearchSchemaOut(cards=[])

    class ScriptedClient:
        def __init__(self) -> None:
            self.call_count = 0

        async def complete(
            self,
            _prompt: str,
            **_kwargs,
        ) -> LLMResponse:
            self.call_count += 1

            if self.call_count == 1:
                text = json.dumps(
                    {
                        "tool": "search_schema",
                        "args": {
                            "query": "customer orders",
                        },
                    }
                )
            else:
                text = json.dumps(
                    {
                        "final": "done",
                    }
                )

            return LLMResponse(
                text=text,
                tokens_in=1,
                tokens_out=1,
                latency_ms=0.0,
                model="fake",
                attempts=1,
                retried=False,
            )

    tool = AsyncCallableTool()

    tools = {
        "search_schema": ToolSpec(
            input_model=SearchSchemaIn,
            handler=tool,
            description="Search schema.",
        )
    }

    trace = await run_agent(
        "How many customer orders are there?",
        ScriptedClient(),
        tools=tools,
        max_steps=6,
        step_timeout_s=1.0,
    )

    assert tool.call_count == 1
    assert tool.queries == ["customer orders"]

    assert trace.status == "completed"
    assert trace.final_answer == "done"

    assert len(trace.steps) == 2
    assert trace.steps[0].tool_calls[0].tool == "search_schema"