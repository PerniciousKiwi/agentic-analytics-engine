from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cardinal.agent.schemas import (
    ExecuteSqlIn,
    SearchSchemaIn,
)
from cardinal.agent.tools import execute_sql, search_schema
from cardinal.config import get_settings
from cardinal.llm.client import LLMResponse


class AgentLLM(Protocol):
    """Minimal LLM interface required by the agent loop."""

    async def complete(
        self,
        prompt: str,
        **overrides: Any,
    ) -> LLMResponse: ...


ToolHandler = Callable[
    [BaseModel],
    object | Awaitable[object],
]


@dataclass(frozen=True)
class ToolSpec:
    """Definition of one tool available to the agent."""

    input_model: type[BaseModel]
    handler: ToolHandler
    description: str


class AgentToolCall(BaseModel):
    """One tool request emitted by the model."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class AgentTurn(BaseModel):
    """Parsed manual-ReAct response from the model."""

    model_config = ConfigDict(extra="forbid")

    final: str | None = None
    tool: str | None = None
    args: dict[str, Any] | None = None
    tool_calls: list[AgentToolCall] | None = None


class ToolCallTrace(BaseModel):
    """Trace entry for one executed tool call."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    args: dict[str, Any]
    result: Any
    latency_ms: int


class AgentStepTrace(BaseModel):
    """Trace information for one agent reasoning step."""

    model_config = ConfigDict(extra="forbid")

    step_number: int
    model_output: str | None = None
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    latency_ms: int
    error: str | None = None


TraceStatus = Literal[
    "completed",
    "step_budget_exhausted",
    "timeout",
    "no_progress",
    "error",
]


class Trace(BaseModel):
    """Deterministic trace returned for every agent execution."""

    model_config = ConfigDict(extra="forbid")

    question: str
    status: TraceStatus
    steps: list[AgentStepTrace] = Field(default_factory=list)
    final_answer: str | None = None
    error: str | None = None
    total_latency_ms: int

class AgentOutputError(ValueError):
    """Recoverable error caused by malformed model output."""

    def __init__(
        self,
        *,
        raw_text: str,
        detail: str,
    ) -> None:
        super().__init__(detail)
        self.raw_text = raw_text
        self.detail = detail

DEFAULT_TOOLS: dict[str, ToolSpec] = {
    "search_schema": ToolSpec(
        input_model=SearchSchemaIn,
        handler=search_schema,
        description=(
            "Search the warehouse schema for relevant tables, columns, "
            "metrics, descriptions, and data types."
        ),
    ),
    "execute_sql": ToolSpec(
        input_model=ExecuteSqlIn,
        handler=execute_sql,
        description=(
            "Execute read-only SQL after deterministic guardrail validation. "
            "Returns rows on success or structured failure information."
        ),
    ),
}


async def run_agent(
    question: str,
    llm: AgentLLM,
    *,
    tools: dict[str, ToolSpec] | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> Trace:
    """Run the bounded manual-ReAct agent loop.

    The function always returns a Trace. Errors, timeouts, malformed model
    responses, and step-budget exhaustion never escape its outer boundary.
    """
    started = time.perf_counter()
    settings = get_settings()

    available_tools = (
        DEFAULT_TOOLS
        if tools is None
        else tools
    )
    step_budget = max_steps if max_steps is not None else settings.max_agent_steps
    timeout_s = (
        step_timeout_s
        if step_timeout_s is not None
        else settings.agent_step_timeout_s
    )

    trace = Trace(
        question=question,
        status="error",
        total_latency_ms=0,
    )

    history: list[dict[str, Any]] = []

    previous_malformed_output: str | None = None

    try:
        for step_number in range(1, step_budget + 1):
            step_started = time.perf_counter()

            try:
                outcome = await asyncio.wait_for(
                    _run_step(
                        question=question,
                        history=history,
                        llm=llm,
                        tools=available_tools,
                    ),
                    timeout=timeout_s,
                )

            except TimeoutError:
                trace.steps.append(
                    AgentStepTrace(
                        step_number=step_number,
                        latency_ms=_elapsed_ms(step_started),
                        error=(
                            f"Agent step exceeded timeout of "
                            f"{timeout_s:g} seconds."
                        ),
                    )
                )

                trace.status = "timeout"
                trace.error = trace.steps[-1].error
                trace.total_latency_ms = _elapsed_ms(started)
                return trace

            except AgentOutputError as exc:
                normalized_output = _normalize_model_output(
                    exc.raw_text,
                )

                step_error = (
                    "Malformed agent output: "
                    f"{exc.detail}"
                )

                trace.steps.append(
                    AgentStepTrace(
                        step_number=step_number,
                        model_output=exc.raw_text,
                        latency_ms=_elapsed_ms(step_started),
                        error=step_error,
                    )
                )

                if (
                    previous_malformed_output is not None
                    and normalized_output == previous_malformed_output
                ):
                    trace.status = "no_progress"
                    trace.error = (
                        "Agent produced the same malformed output "
                        "twice consecutively; stopping early because "
                        "no progress was made."
                    )
                    trace.total_latency_ms = _elapsed_ms(started)
                    return trace

                previous_malformed_output = normalized_output

                history.append(
                    {
                        "model": exc.raw_text,
                        "tool_results": [],
                        "observation": (
                            "Your last response was not valid agent JSON. "
                            f"Parser/validation error: {exc.detail}. "
                            "Respond again using exactly one valid JSON object "
                            'matching either {"tool":"...","args":{...}}, '
                            '{"tool_calls":[...]}, or '
                            '{"final":"..."}. Do not include prose outside '
                            "the JSON object."
                        ),
                    }
                )

                continue

            except Exception as exc:
                trace.steps.append(
                    AgentStepTrace(
                        step_number=step_number,
                        latency_ms=_elapsed_ms(step_started),
                        error=str(exc),
                    )
                )

                trace.status = "error"
                trace.error = str(exc)
                trace.total_latency_ms = _elapsed_ms(started)
                return trace

            previous_malformed_output = None
            step_trace = AgentStepTrace(
                step_number=step_number,
                model_output=outcome.model_output,
                tool_calls=outcome.tool_calls,
                latency_ms=_elapsed_ms(step_started),
            )

            trace.steps.append(step_trace)

            if outcome.final_answer is not None:
                trace.status = "completed"
                trace.final_answer = outcome.final_answer
                trace.total_latency_ms = _elapsed_ms(started)
                return trace

            history.append(
                {
                    "model": outcome.model_output,
                    "tool_results": [
                        {
                            "tool": tool_call.tool,
                            "args": tool_call.args,
                            "result": tool_call.result,
                        }
                        for tool_call in outcome.tool_calls
                    ],
                }
            )

        trace.status = "step_budget_exhausted"
        trace.error = (
            f"Agent exhausted its step budget of {step_budget} "
            "without producing a final answer."
        )
        trace.total_latency_ms = _elapsed_ms(started)
        return trace

    except Exception as exc:
        trace.status = "error"
        trace.error = str(exc)
        trace.total_latency_ms = _elapsed_ms(started)
        return trace


@dataclass
class _StepOutcome:
    model_output: str
    tool_calls: list[ToolCallTrace]
    final_answer: str | None


async def _run_step(
    *,
    question: str,
    history: list[dict[str, Any]],
    llm: AgentLLM,
    tools: dict[str, ToolSpec],
) -> _StepOutcome:
    prompt = _build_prompt(
        question=question,
        history=history,
        tools=tools,
    )

    response = await llm.complete(
        prompt,
        temperature=0.0,
    )

    turn = _parse_turn(response.text)

    if turn.final is not None:
        if turn.tool is not None or turn.tool_calls is not None:
            raise ValueError(
                "Agent response cannot contain both a final answer and tool calls."
            )

        return _StepOutcome(
            model_output=response.text,
            tool_calls=[],
            final_answer=turn.final,
        )

    calls = _turn_tool_calls(turn)

    if not calls:
        raise ValueError(
            "Agent response contained neither a final answer nor a tool call."
        )

    traces = await asyncio.gather(
        *[
            _dispatch_tool(
                call,
                tools,
            )
            for call in calls
        ]
    )

    return _StepOutcome(
        model_output=response.text,
        tool_calls=list(traces),
        final_answer=None,
    )


def _turn_tool_calls(
    turn: AgentTurn,
) -> list[AgentToolCall]:
    if turn.tool_calls is not None:
        if turn.tool is not None:
            raise ValueError(
                "Agent response cannot contain both tool and tool_calls."
            )

        return turn.tool_calls

    if turn.tool is not None:
        return [
            AgentToolCall(
                tool=turn.tool,
                args=turn.args or {},
            )
        ]

    return []


async def _dispatch_tool(
    call: AgentToolCall,
    tools: dict[str, ToolSpec],
) -> ToolCallTrace:
    started = time.perf_counter()

    spec = tools.get(call.tool)

    if spec is None:
        return ToolCallTrace(
            tool=call.tool,
            args=call.args,
            result={
                "error": f"Unknown tool: {call.tool}",
            },
            latency_ms=_elapsed_ms(started),
        )

    try:
        request = spec.input_model.model_validate(
            call.args,
        )

    except ValidationError as exc:
        return ToolCallTrace(
            tool=call.tool,
            args=call.args,
            result={
                "error": "Invalid tool arguments.",
                "details": exc.errors(),
            },
            latency_ms=_elapsed_ms(started),
        )

    try:
        is_async_handler = inspect.iscoroutinefunction(
            spec.handler
        ) or inspect.iscoroutinefunction(
            spec.handler.__call__
        )

        if is_async_handler:
            result = await spec.handler(request)
        else:
            result = await asyncio.to_thread(
                spec.handler,
                request,
            )

        return ToolCallTrace(
            tool=call.tool,
            args=call.args,
            result=_jsonable(result),
            latency_ms=_elapsed_ms(started),
        )

    except Exception as exc:
        return ToolCallTrace(
            tool=call.tool,
            args=call.args,
            result={
                "error": str(exc),
            },
            latency_ms=_elapsed_ms(started),
        )


def _parse_turn(text: str) -> AgentTurn:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AgentOutputError(
            raw_text=text,
            detail=(
                f"{exc.msg}: line {exc.lineno} "
                f"column {exc.colno}"
            ),
        ) from exc

    if not isinstance(payload, dict):
        raise AgentOutputError(
            raw_text=text,
            detail="Agent response must be a JSON object.",
        )

    try:
        return AgentTurn.model_validate(payload)
    except ValidationError as exc:
        raise AgentOutputError(
            raw_text=text,
            detail=str(exc),
        ) from exc


def _build_prompt(
    *,
    question: str,
    history: list[dict[str, Any]],
    tools: dict[str, ToolSpec],
) -> str:
    tool_definitions = {
        name: {
            "description": spec.description,
            "input_schema": spec.input_model.model_json_schema(),
        }
        for name, spec in tools.items()
    }

    history_json = json.dumps(
        history,
        ensure_ascii=False,
        default=str,
    )

    tools_json = json.dumps(
        tool_definitions,
        ensure_ascii=False,
    )

    return f"""
You are an analytics agent.

You answer the user's analytical question by deciding which tools to use.
You are not following a fixed generate-then-execute pipeline. Decide what
information you need at each step based on previous tool results.

AVAILABLE TOOLS:
{tools_json}

USER QUESTION:
{question}

PREVIOUS STEPS:
{history_json}

You must return exactly one JSON object and no prose outside the JSON.

To call one tool:

{{"tool":"search_schema","args":{{"query":"..."}}}}

To request multiple independent tools in the same turn:

{{"tool_calls":[
  {{"tool":"search_schema","args":{{"query":"..."}}}},
  {{"tool":"search_schema","args":{{"query":"..."}}}}
]}}

When you have enough information to answer:

{{"final":"your final answer"}}

Rules:
- Never invent tool results.
- Use search_schema when schema knowledge is needed.
- Use execute_sql only for read-only analytical SQL.
- If execute_sql returns a structured error, reason about that error and
  decide whether another tool call is appropriate.
- Do not emit a final answer and tool calls in the same response.
- Return valid JSON only.
""".strip()


def _jsonable(value: object) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(
            mode="json",
        )

    if value is None or isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
            list,
            dict,
        ),
    ):
        return value

    return str(value)

def _normalize_model_output(text: str) -> str:
    return " ".join(text.split())

def _elapsed_ms(started: float) -> int:
    return max(
        0,
        round(
            (time.perf_counter() - started) * 1000,
        ),
    )