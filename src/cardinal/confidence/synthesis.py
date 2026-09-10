from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Template

from cardinal.llm.client import OllamaClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]

PROMPT_PATH = (
    PROJECT_ROOT
    / "src"
    / "cardinal"
    / "llm"
    / "prompts"
    / "synthesize_answer.j2"
)


class AnswerSynthesizer:
    """Generate a short natural-language answer from executed SQL rows."""

    def __init__(
        self,
        client: OllamaClient,
    ) -> None:
        self.client = client

        self.template = Template(
            PROMPT_PATH.read_text(
                encoding="utf-8",
            )
        )

    async def synthesize(
        self,
        question: str,
        rows: list[list[Any]] | list[tuple[Any, ...]],
    ) -> str:
        prompt = self.template.render(
            question=question,
            rows=rows,
        )

        response = await self.client.complete(
            prompt,
            temperature=0.0,
            max_tokens=150,
        )

        return response.text.strip()