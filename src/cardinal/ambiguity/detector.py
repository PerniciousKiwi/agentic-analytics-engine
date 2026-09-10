from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Template
from pydantic import ValidationError

from cardinal.ambiguity.context import build_semantic_context
from cardinal.ambiguity.models import (
    AmbiguityDecision,
    AmbiguityVerification,
)
from cardinal.catalog.catalog import Catalog
from cardinal.llm.client import OllamaClient


PROJECT_ROOT = Path(__file__).resolve().parents[3]

PROMPT_PATH = (
    PROJECT_ROOT
    / "src"
    / "cardinal"
    / "llm"
    / "prompts"
    / "detect_ambiguity.j2"
)

VERIFY_PROMPT_PATH = (
    PROJECT_ROOT
    / "src"
    / "cardinal"
    / "llm"
    / "prompts"
    / "verify_ambiguity.j2"
)


class AmbiguityDetector:
    """Two-stage ambiguity detector."""

    def __init__(
        self,
        *,
        catalog: Catalog,
        client: OllamaClient,
        loop: Any,
        retrieval: Any | None = None,
        context_assembler: Any | None = None,
        include_retrieved_schema: bool = False,
        max_tokens: int = 220,
        verification_max_tokens: int = 80,
        enable_verification: bool = False,
    ) -> None:
        self.catalog = catalog
        self.client = client
        self.loop = loop
        self.retrieval = retrieval
        self.context_assembler = context_assembler
        self.include_retrieved_schema = include_retrieved_schema
        self.max_tokens = max_tokens
        self.verification_max_tokens = verification_max_tokens
        self.enable_verification = enable_verification

        self.template = Template(
            PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        self.verification_template = Template(
            VERIFY_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

    def detect(
        self,
        question: str,
    ) -> tuple[
        AmbiguityDecision,
        dict[str, Any],
    ]:
        """Classify and, when needed, verify ambiguity."""

        metrics_context, glossary_context = (
            build_semantic_context(
                self.catalog
            )
        )

        schema_context = ""

        if self.include_retrieved_schema:
            if (
                self.retrieval is None
                or self.context_assembler is None
            ):
                raise ValueError(
                    "retrieval and context_assembler are "
                    "required when "
                    "include_retrieved_schema=True"
                )

            response = self.retrieval.retrieve(
                question,
                mode="hybrid",
                limit=12,
            )

            context = self.context_assembler.assemble(
                response.results
            )

            schema_context = context.schema

        prompt = self.template.render(
            question=question,
            metrics_context=metrics_context,
            glossary_context=glossary_context,
            schema_context=schema_context,
        )

        llm_response = self.loop.run_until_complete(
            self.client.complete(
                prompt,
                temperature=0.0,
                max_tokens=self.max_tokens,
            )
        )

        stage1_decision = (
            parse_ambiguity_response(
                llm_response.text
            )
        )

        metadata: dict[str, Any] = {
            "ambiguity_tokens_in": (
                llm_response.tokens_in
            ),
            "ambiguity_tokens_out": (
                llm_response.tokens_out
            ),
            "ambiguity_latency_ms": (
                llm_response.latency_ms
            ),
            "ambiguity_llm_attempts": (
                llm_response.attempts
            ),
            "ambiguity_llm_retried": (
                llm_response.retried
            ),
            "ambiguity_context_mode": (
                "semantic_plus_schema"
                if self.include_retrieved_schema
                else "semantic_only"
            ),
            "ambiguity_parse_fallback": (
                stage1_decision.parse_fallback
            ),
            "ambiguity_stage1_ambiguous": (
                stage1_decision.ambiguous
            ),
            "ambiguity_stage1_type": (
                stage1_decision.ambiguity_type.value
                if stage1_decision.ambiguity_type
                else None
            ),
            "ambiguity_stage1_clarifying_question": (
                stage1_decision.clarifying_question
            ),
            "ambiguity_verification_used": False,
            "ambiguity_verified": None,
            "ambiguity_verification_parse_fallback": False,
        }

        # Clear at stage 1: no second LLM call needed.
        if not stage1_decision.ambiguous:
            metadata["ambiguity_type"] = None
            metadata["clarifying_question"] = None

            return stage1_decision, metadata

        # A stage-1 parser failure already triggered our
        # fail-closed policy. There is no reliable proposed
        # ambiguity for stage 2 to verify.
        if stage1_decision.parse_fallback:
            metadata["ambiguity_type"] = None
            metadata["clarifying_question"] = (
                stage1_decision.clarifying_question
            )

            return stage1_decision, metadata

        # Verification was evaluated as an ablation.
        # Keep it optional because the extra LLM call must
        # justify its latency and complexity empirically.
        if not self.enable_verification:
            metadata["ambiguity_type"] = (
                stage1_decision.ambiguity_type.value
                if stage1_decision.ambiguity_type
                else None
            )

            metadata["clarifying_question"] = (
                stage1_decision.clarifying_question
            )

            return stage1_decision, metadata

        verification, verification_metadata = (
            self._verify(
                question=question,
                decision=stage1_decision,
                metrics_context=metrics_context,
                glossary_context=glossary_context,
            )
        )

        metadata.update(
            verification_metadata
        )

        if not verification.confirmed:
            final_decision = AmbiguityDecision(
                ambiguous=False,
            )
        else:
            final_decision = stage1_decision

        metadata["ambiguity_type"] = (
            final_decision.ambiguity_type.value
            if final_decision.ambiguity_type
            else None
        )

        metadata["clarifying_question"] = (
            final_decision.clarifying_question
        )

        return final_decision, metadata

    def _verify(
        self,
        *,
        question: str,
        decision: AmbiguityDecision,
        metrics_context: str,
        glossary_context: str,
    ) -> tuple[
        AmbiguityVerification,
        dict[str, Any],
    ]:
        """Verify a stage-one ambiguity claim."""

        prompt = self.verification_template.render(
            question=question,
            metrics_context=metrics_context,
            glossary_context=glossary_context,
            ambiguity_type=(
                decision.ambiguity_type.value
                if decision.ambiguity_type
                else ""
            ),
            clarifying_question=(
                decision.clarifying_question
                or ""
            ),
        )

        llm_response = self.loop.run_until_complete(
            self.client.complete(
                prompt,
                temperature=0.0,
                max_tokens=self.verification_max_tokens,
            )
        )

        verification = (
            parse_verification_response(
                llm_response.text
            )
        )

        metadata = {
            "ambiguity_verification_used": True,
            "ambiguity_verified": (
                verification.confirmed
            ),
            "ambiguity_verification_parse_fallback": (
                verification.parse_fallback
            ),
            "ambiguity_verification_tokens_in": (
                llm_response.tokens_in
            ),
            "ambiguity_verification_tokens_out": (
                llm_response.tokens_out
            ),
            "ambiguity_verification_latency_ms": (
                llm_response.latency_ms
            ),
            "ambiguity_verification_llm_attempts": (
                llm_response.attempts
            ),
            "ambiguity_verification_llm_retried": (
                llm_response.retried
            ),
        }

        return verification, metadata


def _json_candidates(
    text: str,
) -> list[str]:
    """Return likely JSON payloads from an LLM response."""

    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines:
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip() == "```"
        ):
            lines = lines[:-1]

        cleaned = "\n".join(
            lines
        ).strip()

    candidates = [cleaned]

    object_match = re.search(
        r"\{.*\}",
        cleaned,
        flags=re.DOTALL,
    )

    if (
        object_match is not None
        and object_match.group(0) != cleaned
    ):
        candidates.append(
            object_match.group(0)
        )

    return candidates


def parse_ambiguity_response(
    text: str,
) -> AmbiguityDecision:
    """Parse the stage-one classifier response."""

    for candidate in _json_candidates(
        text
    ):
        try:
            payload = json.loads(
                candidate
            )

            if not isinstance(
                payload,
                dict,
            ):
                continue

            if (
                "type" in payload
                and "ambiguity_type"
                not in payload
            ):
                payload[
                    "ambiguity_type"
                ] = payload.pop(
                    "type"
                )

            if (
                payload.get(
                    "ambiguity_type"
                )
                == ""
            ):
                payload[
                    "ambiguity_type"
                ] = None

            if (
                payload.get(
                    "clarifying_question"
                )
                == ""
            ):
                payload[
                    "clarifying_question"
                ] = None

            return (
                AmbiguityDecision.model_validate(
                    payload
                )
            )

        except (
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ):
            continue

    # Fail closed:
    # malformed classifier output must not silently
    # proceed into SQL generation.
    return AmbiguityDecision(
        ambiguous=True,
        ambiguity_type=None,
        clarifying_question=(
            "I could not reliably determine the intended "
            "interpretation. Could you clarify the metric, "
            "entity, time period, or scope you want?"
        ),
        parse_fallback=True,
    )


def parse_verification_response(
    text: str,
) -> AmbiguityVerification:
    """Parse the stage-two verifier response."""

    for candidate in _json_candidates(
        text
    ):
        try:
            payload = json.loads(
                candidate
            )

            if not isinstance(
                payload,
                dict,
            ):
                continue

            return (
                AmbiguityVerification.model_validate(
                    payload
                )
            )

        except (
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ):
            continue

    # Fail closed here as well.
    #
    # Stage 1 already found ambiguity. If the verifier
    # cannot return a reliable judgment, do not silently
    # overturn that decision.
    return AmbiguityVerification(
        confirmed=True,
        parse_fallback=True,
    )