from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RetrievalMode = Literal["lexical", "dense", "hybrid"]


class RetrievalResult(BaseModel):
    """A single retrieved schema card."""

    model_config = ConfigDict(extra="forbid")

    card_id: str
    card_type: Literal["table", "column", "metric"]
    domain: str
    card_name: str
    card_text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    """Results returned by a retrieval operation."""

    model_config = ConfigDict(extra="forbid")

    query: str
    mode: RetrievalMode
    results: list[RetrievalResult] = Field(default_factory=list)
