from __future__ import annotations

import asyncio
import time

import pytest

from cardinal.agent.loop import ToolSpec, run_agent
from cardinal.agent.schemas import (
    ExecuteSqlIn,
    ExecuteSqlOut,
    SearchSchemaIn,
    SearchSchemaOut,
)
from cardinal.llm.client import LLMResponse


class ScriptedLLM:
    """Fake deterministic LLM that returns responses in fixed order."""

    def __init__(
        self,
        responses: list[str],
    ) -> None:
        self.responses = responses
        self.call_count = 0
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: str,
        **_overrides,
    ) -> LLMResponse:
        self.prompts.append(prompt)

        if self.call_count >= len(self.responses):
            raise AssertionError(
                "Scripted LLM received more calls than expected."
            )

        text = self.responses[self.call_count]
        self.call_count += 1

        return LLMResponse(
            text=text,
            tokens_in=10,
            tokens_out=10,
            latency_ms=1.0,
            model="fake",
            attempts=1,
            retried=False,
        )


@pytest.mark.asyncio
async def test_agent_follows_scripted_tool_sequence() -> None:
    llm = ScriptedLLM(
        responses=[
            (
                '{"tool":"search_schema",'
                '"args":{"query":"total revenue"}}'
            ),
            (
                '{"tool":"execute_sql",'
                '"args":{"sql":"SELECT SUM(revenue) FROM orders"}}'
            ),
            '{"final":"Total revenue is 100."}',
        ]
    )

    call_order: list[tuple[str, object]] = []

    def fake_search(
        request: SearchSchemaIn,
    ) -> SearchSchemaOut:
        call_order.append(
            (
                "search_schema",
                request.query,
            )
        )

        return SearchSchemaOut(
            cards=[],
        )

    def fake_execute(
        request: ExecuteSqlIn,
    ) -> ExecuteSqlOut:
        call_order.append(
            (
                "execute_sql",
                request.sql,
            )
        )

        return ExecuteSqlOut(
            columns=["revenue"],
            rows=[[100]],
            row_count=1,
            truncated=False,
            elapsed_ms=1,
        )

    tools = {
        "search_schema": ToolSpec(
            input_model=SearchSchemaIn,
            handler=fake_search,
            description="Search schema.",
        ),
        "execute_sql": ToolSpec(
            input_model=ExecuteSqlIn,
            handler=fake_execute,
            description="Execute SQL.",
        ),
    }

    trace = await run_agent(
        "What is total revenue?",
        llm,
        tools=tools,
        max_steps=6,
        step_timeout_s=1.0,
    )

    assert trace.status == "completed"
    assert trace.final_answer == "Total revenue is 100."
    assert trace.error is None

    assert call_order == [
        (
            "search_schema",
            "total revenue",
        ),
        (
            "execute_sql",
            "SELECT SUM(revenue) FROM orders",
        ),
    ]

    assert len(trace.steps) == 3

    assert trace.steps[0].tool_calls[0].tool == "search_schema"
    assert trace.steps[0].tool_calls[0].args == {
        "query": "total revenue",
    }

    assert trace.steps[1].tool_calls[0].tool == "execute_sql"
    assert trace.steps[1].tool_calls[0].args == {
        "sql": "SELECT SUM(revenue) FROM orders",
    }

    assert trace.steps[2].tool_calls == []


class InfiniteToolLLM:
    """Fake LLM that never produces a final answer."""

    def __init__(self) -> None:
        self.call_count = 0

    async def complete(
        self,
        prompt: str,
        **_overrides,
    ) -> LLMResponse:
        del prompt

        self.call_count += 1

        return LLMResponse(
            text=(
                '{"tool":"search_schema",'
                '"args":{"query":"orders"}}'
            ),
            tokens_in=1,
            tokens_out=1,
            latency_ms=0.0,
            model="fake",
            attempts=1,
            retried=False,
        )


@pytest.mark.asyncio
async def test_agent_stops_at_exact_step_budget() -> None:
    llm = InfiniteToolLLM()

    tool_call_count = 0

    def fake_search(
        request: SearchSchemaIn,
    ) -> SearchSchemaOut:
        nonlocal tool_call_count
        tool_call_count += 1

        assert request.query == "orders"

        return SearchSchemaOut(
            cards=[],
        )

    tools = {
        "search_schema": ToolSpec(
            input_model=SearchSchemaIn,
            handler=fake_search,
            description="Search schema.",
        )
    }

    trace = await run_agent(
        "Count orders.",
        llm,
        tools=tools,
        max_steps=6,
        step_timeout_s=1.0,
    )

    assert trace.status == "step_budget_exhausted"
    assert trace.final_answer is None
    assert trace.error is not None

    assert llm.call_count == 6
    assert tool_call_count == 6
    assert len(trace.steps) == 6


@pytest.mark.asyncio
async def test_independent_tool_calls_run_concurrently() -> None:
    llm = ScriptedLLM(
        responses=[
            (
                '{"tool_calls":['
                '{"tool":"search_schema",'
                '"args":{"query":"orders"}},'
                '{"tool":"search_schema",'
                '"args":{"query":"customers"}}'
                ']}'
            ),
            '{"final":"Done."}',
        ]
    )

    started_calls: list[str] = []

    async def slow_search(
        request: SearchSchemaIn,
    ) -> SearchSchemaOut:
        started_calls.append(request.query)

        await asyncio.sleep(0.1)

        return SearchSchemaOut(
            cards=[],
        )

    tools = {
        "search_schema": ToolSpec(
            input_model=SearchSchemaIn,
            handler=slow_search,
            description="Search schema.",
        )
    }

    started = time.perf_counter()

    trace = await run_agent(
        "Compare orders with customers.",
        llm,
        tools=tools,
        max_steps=6,
        step_timeout_s=1.0,
    )

    elapsed = time.perf_counter() - started

    assert trace.status == "completed"

    assert set(started_calls) == {
        "orders",
        "customers",
    }

    assert len(trace.steps[0].tool_calls) == 2

    # Sequential execution would take roughly 0.2 seconds.
    # Concurrent execution should remain much closer to 0.1.
    assert elapsed < 0.19


@pytest.mark.asyncio
async def test_agent_returns_trace_on_timeout() -> None:
    class SlowLLM:
        async def complete(
            self,
            prompt: str,
            **_overrides,
        ) -> LLMResponse:
            del prompt

            await asyncio.sleep(0.2)

            return LLMResponse(
                text='{"final":"too late"}',
                tokens_in=1,
                tokens_out=1,
                latency_ms=200.0,
                model="fake",
                attempts=1,
                retried=False,
            )

    trace = await run_agent(
        "test",
        SlowLLM(),
        tools={},
        max_steps=6,
        step_timeout_s=0.05,
    )

    assert trace.status == "timeout"
    assert trace.final_answer is None
    assert trace.error is not None
    assert len(trace.steps) == 1
    assert trace.steps[0].error is not None


@pytest.mark.asyncio
async def test_agent_recovers_from_malformed_model_output() -> None:
    llm = ScriptedLLM(
        responses=[
            '{"tool":"search_schema","args":{',
            '{"final":"Recovered successfully."}',
        ]
    )

    trace = await run_agent(
        "Count orders.",
        llm,
        tools={},
        max_steps=6,
        step_timeout_s=1.0,
    )

    assert trace.status == "completed"
    assert trace.final_answer == "Recovered successfully."
    assert trace.error is None

    assert llm.call_count == 2
    assert len(trace.steps) == 2

    assert trace.steps[0].error is not None
    assert "Malformed agent output" in trace.steps[0].error
    assert trace.steps[1].error is None

    assert "Parser/validation error" in llm.prompts[1]


@pytest.mark.asyncio
async def test_agent_stops_early_on_repeated_identical_malformed_output() -> None:
    broken = '{"tool":"search_schema","args":{'

    llm = ScriptedLLM(
        responses=[
            broken,
            broken,
            broken,
            broken,
            broken,
            broken,
        ]
    )

    trace = await run_agent(
        "Count orders.",
        llm,
        tools={},
        max_steps=6,
        step_timeout_s=1.0,
    )

    assert trace.status == "no_progress"
    assert trace.final_answer is None
    assert trace.error is not None

    assert llm.call_count == 2
    assert len(trace.steps) == 2

    assert trace.steps[0].error is not None
    assert trace.steps[1].error is not None

    assert "same malformed output" in trace.error

@pytest.mark.asyncio
async def test_unknown_tool_is_returned_as_observation() -> None:
    llm = ScriptedLLM(
        responses=[
            '{"tool":"does_not_exist","args":{}}',
            '{"final":"I cannot use that tool."}',
        ]
    )

    trace = await run_agent(
        "test",
        llm,
        tools={},
        max_steps=6,
        step_timeout_s=1.0,
    )

    assert trace.status == "completed"

    first_result = trace.steps[0].tool_calls[0].result

    assert first_result == {
        "error": "Unknown tool: does_not_exist",
    }