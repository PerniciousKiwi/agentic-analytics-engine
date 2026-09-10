from pathlib import Path

from jinja2 import Template

from cardinal.ambiguity.detector import (
    parse_ambiguity_response,
    parse_verification_response,
)
from cardinal.ambiguity.models import (
    AmbiguityDecision,
    AmbiguityType,
)
from eval.systems.ambiguity_aware import (
    AmbiguityAwareSystem,
)
from eval.systems.retrieval_guarded_repaired import (
    RetrievalGuardedRepairedSystem,
)


def test_prompt_renders_fixed_context() -> None:
    path = Path(
        "src/cardinal/llm/prompts/detect_ambiguity.j2"
    )

    template = Template(
        path.read_text(encoding="utf-8")
    )

    rendered = template.render(
        question="Show revenue for last month.",
        metrics_context=(
            "Metric: revenue\n"
            "Definition: item value plus freight"
        ),
        glossary_context=(
            "Term: customer\n"
            "Definition: business customer"
        ),
        schema_context="",
    )

    assert "Show revenue for last month." in rendered
    assert "Metric: revenue" in rendered
    assert '"ambiguous": true' in rendered


def test_parser_well_formed_response() -> None:
    result = parse_ambiguity_response(
        (
            '{"ambiguous": true, '
            '"ambiguity_type": "time_grain", '
            '"clarifying_question": '
            '"Calendar month or rolling 30 days?"}'
        )
    )

    assert result.ambiguous is True
    assert (
        result.ambiguity_type
        == AmbiguityType.TIME_GRAIN
    )
    assert (
        result.clarifying_question
        == "Calendar month or rolling 30 days?"
    )
    assert result.parse_fallback is False


def test_parser_clear_response() -> None:
    result = parse_ambiguity_response(
        (
            '{"ambiguous": false, '
            '"ambiguity_type": null, '
            '"clarifying_question": null}'
        )
    )

    assert result.ambiguous is False
    assert result.ambiguity_type is None
    assert result.clarifying_question is None
    assert result.parse_fallback is False


def test_parser_accepts_code_fence() -> None:
    result = parse_ambiguity_response(
        (
            "```json\n"
            '{"ambiguous": false, '
            '"ambiguity_type": null, '
            '"clarifying_question": null}'
            "\n```"
        )
    )

    assert result.ambiguous is False
    assert result.ambiguity_type is None


def test_parser_invalid_json_fails_closed() -> None:
    result = parse_ambiguity_response(
        "this is not json"
    )

    assert result.ambiguous is True
    assert result.parse_fallback is True
    assert result.clarifying_question is not None


def test_parser_missing_field_fails_closed() -> None:
    result = parse_ambiguity_response(
        (
            '{"ambiguous": true, '
            '"ambiguity_type": "metric"}'
        )
    )

    assert result.ambiguous is True
    assert result.parse_fallback is True


def test_parser_unexpected_type_fails_closed() -> None:
    result = parse_ambiguity_response(
        (
            '{"ambiguous": true, '
            '"ambiguity_type": "banana", '
            '"clarifying_question": '
            '"Which one?"}'
        )
    )

    assert result.ambiguous is True
    assert result.parse_fallback is True

def test_verifier_confirms_real_ambiguity() -> None:
    result = parse_verification_response(
        '{"confirmed": true}'
    )

    assert result.confirmed is True
    assert result.parse_fallback is False


def test_verifier_rejects_invented_ambiguity() -> None:
    result = parse_verification_response(
        '{"confirmed": false}'
    )

    assert result.confirmed is False
    assert result.parse_fallback is False


def test_verifier_malformed_response_fails_closed() -> None:
    result = parse_verification_response(
        "not valid json"
    )

    assert result.confirmed is True
    assert result.parse_fallback is True

def test_ambiguous_question_skips_phase8(
    monkeypatch,
) -> None:
    class FakeDetector:
        def detect(self, question: str):
            return (
                AmbiguityDecision(
                    ambiguous=True,
                    ambiguity_type=AmbiguityType.METRIC,
                    clarifying_question=(
                        "Do you mean revenue or GMV?"
                    ),
                ),
                {
                    "ambiguity_type": "metric",
                    "clarifying_question": (
                        "Do you mean revenue or GMV?"
                    ),
                },
            )

    system = AmbiguityAwareSystem.__new__(
        AmbiguityAwareSystem
    )

    system.ambiguity_detector = FakeDetector()

    def phase8_must_not_run(
        self,
        question,
        db_context,
    ):
        raise AssertionError(
            "Phase 8 pipeline should not run "
            "for ambiguous questions."
        )

    monkeypatch.setattr(
        RetrievalGuardedRepairedSystem,
        "answer",
        phase8_must_not_run,
    )

    sql, metadata = system.answer(
        "Show sales.",
        {
            "source": "postgres",
        },
    )

    assert sql == ""
    assert metadata["abstained"] is True
    assert metadata["abstain_reason"] == "AMBIGUOUS"
    assert metadata["generation_skipped"] is True
    assert metadata["repair_attempts"] == 0