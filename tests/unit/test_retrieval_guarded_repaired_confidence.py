from unittest.mock import AsyncMock

import pytest
from eval.systems.retrieval_guarded_repaired import (
    RetrievalGuardedRepairedSystem,
)


@pytest.mark.asyncio
async def test_generate_consistency_candidate_uses_temperature_point_seven(
    monkeypatch,
) -> None:
    system = object.__new__(
        RetrievalGuardedRepairedSystem
    )

    system.client = AsyncMock()
    system.max_output_tokens = 500

    system.client.complete.return_value.text = (
        "SELECT 1;"
    )

    class FakeResponse:
        def __init__(self) -> None:
            self.results = []

    class FakeRetrieval:
        def retrieve(
            self,
            question,
            mode,
            limit,
        ):
            return FakeResponse()

    class FakeContext:
        def __init__(self) -> None:
            self.schema = ""
            self.card_ids = []
            self.token_count = 0

    class FakeAssembler:
        def select_metrics(
            self,
            question,
            metrics,
        ):
            return []

        def assemble(
            self,
            results,
            required_tables=None,
        ):
            return FakeContext()

        def _format_metrics(
            self,
            metrics,
        ):
            return ""

        def tables_from_card_ids(
            self,
            card_ids,
        ):
            return set()

        def _format_glossary(
            self,
            question,
            tables,
        ):
            return ""

        def _format_table_notes(
            self,
            tables,
        ):
            return ""

    system.retrieval = FakeRetrieval()
    system.context_assembler = FakeAssembler()

    class FakeCatalog:
        def __init__(self) -> None:
            self.metrics = []

    system.catalog = FakeCatalog()

    system.prompt_template = type(
        "FakeTemplate",
        (),
        {
            "render": lambda self, **kwargs: (
                "prompt"
            )
        },
    )()

    sql = await system._generate_consistency_candidate(
        "How many orders?",
        {
            "source": "postgres",
        },
    )

    assert sql == "SELECT 1;"

    call = system.client.complete.await_args

    assert call.kwargs["temperature"] == 0.7

def test_retrieval_metadata_contains_confidence_scores() -> None:
    response_results = [
        type(
            "Result",
            (),
            {
                "score": 4.5,
                "metadata": {
                    "rrf_score": 0.032,
                },
            },
        )(),
        type(
            "Result",
            (),
            {
                "score": 3.75,
                "metadata": {
                    "rrf_score": 0.031,
                },
            },
        )(),
    ]

    top_rrf_score = None
    reranker_margin = None

    if response_results:
        rrf_score = response_results[0].metadata.get(
            "rrf_score"
        )

        if isinstance(rrf_score, (int, float)):
            top_rrf_score = float(rrf_score)

    if len(response_results) >= 2:
        reranker_margin = float(
            response_results[0].score
            - response_results[1].score
        )

    assert top_rrf_score == 0.032
    assert reranker_margin == 0.75