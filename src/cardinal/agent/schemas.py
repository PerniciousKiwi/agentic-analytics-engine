from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cardinal.agent.repair import FailureClass


class ToolError(BaseModel):
    """Structured error returned by an agent tool."""

    model_config = ConfigDict(extra="forbid")

    message: str
    failure_class: FailureClass
    candidates: list[str] = Field(default_factory=list)


class ExecuteSqlIn(BaseModel):
    """Input accepted by the SQL execution tool."""

    model_config = ConfigDict(extra="forbid")

    sql: str = Field(max_length=20_000)
    row_limit: int = Field(default=1000, ge=1, le=5000)


class ExecuteSqlOut(BaseModel):
    """Successful SQL execution result."""

    model_config = ConfigDict(extra="forbid")

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
    error: ToolError | None = None


class SearchSchemaIn(BaseModel):
    """Input accepted by the schema-search tool."""

    model_config = ConfigDict(extra="forbid")

    query: str
    domain: str | None = None


class SchemaCardSummary(BaseModel):
    """Structured schema-card information exposed to the agent."""

    model_config = ConfigDict(extra="forbid")

    card_type: str
    domain: str
    name: str
    description: str
    data_type: str | None = None


class SearchSchemaOut(BaseModel):
    """Structured schema-search result."""

    model_config = ConfigDict(extra="forbid")

    cards: list[SchemaCardSummary] = Field(default_factory=list)
    error: ToolError | None = None
