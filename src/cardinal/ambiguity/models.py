from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AmbiguityType(StrEnum):
    METRIC = "metric"
    TIME_GRAIN = "time_grain"
    ENTITY = "entity"
    FILTER = "filter"
    TIEBREAK = "tiebreak"


class AbstainReason(StrEnum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    AMBIGUOUS = "AMBIGUOUS"
    NO_SCHEMA = "NO_SCHEMA"


class AmbiguityDecision(BaseModel):
    """Structured result returned by the ambiguity detector."""

    model_config = ConfigDict(extra="forbid")

    ambiguous: bool
    ambiguity_type: AmbiguityType | None = None
    clarifying_question: str | None = Field(
        default=None,
        min_length=1,
    )
    parse_fallback: bool = False

    def model_post_init(
        self,
        __context: object,
    ) -> None:
        if self.ambiguous:
            # A real parsed ambiguity requires a known type.
            # A fail-closed parser fallback is allowed to have
            # no type because inventing one would contaminate
            # type-accuracy evaluation.
            if (
                self.ambiguity_type is None
                and not self.parse_fallback
            ):
                raise ValueError(
                    "ambiguous=true requires ambiguity_type"
                )

            if not self.clarifying_question:
                raise ValueError(
                    "ambiguous=true requires "
                    "clarifying_question"
                )

        else:
            self.ambiguity_type = None
            self.clarifying_question = None
            self.parse_fallback = False


class AmbiguityVerification(BaseModel):
    """Structured result returned by stage-two verification."""

    model_config = ConfigDict(extra="forbid")

    confirmed: bool
    parse_fallback: bool = False