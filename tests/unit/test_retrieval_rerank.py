from unittest.mock import MagicMock

import numpy as np
import pytest

from cardinal.retrieval.models import RetrievalResult
from cardinal.retrieval.rerank import SchemaCardReranker


def _result(card_id: str, score: float = 0.0) -> RetrievalResult:
    return RetrievalResult(
        card_id=card_id,
        card_type="table",
        domain="orders",
        card_name=card_id,
        card_text=f"TABLE: {card_id}",
        score=score,
    )


def _reranker(
    *,
    batch_size: int = 16,
    input_top_k: int = 50,
    output_top_k: int = 10,
) -> tuple[SchemaCardReranker, MagicMock, MagicMock]:
    session = MagicMock()
    tokenizer = MagicMock()

    reranker = object.__new__(SchemaCardReranker)
    reranker.batch_size = batch_size
    reranker.input_top_k = input_top_k
    reranker.output_top_k = output_top_k
    reranker.session = session
    reranker.tokenizer = tokenizer

    return reranker, session, tokenizer


def test_blank_query_returns_empty() -> None:
    reranker, session, tokenizer = _reranker()

    assert reranker.rerank("   ", [_result("a")]) == []

    session.run.assert_not_called()
    tokenizer.assert_not_called()


def test_empty_candidates_returns_empty() -> None:
    reranker, session, tokenizer = _reranker()

    assert reranker.rerank("orders", []) == []

    session.run.assert_not_called()
    tokenizer.assert_not_called()


def test_candidates_are_limited_to_input_top_k() -> None:
    reranker, session, tokenizer = _reranker(input_top_k=2)

    tokenizer.return_value = {
        "input_ids": np.ones((2, 4), dtype=np.int64),
        "attention_mask": np.ones((2, 4), dtype=np.int64),
    }
    session.run.return_value = [np.array([[0.1], [0.2]], dtype=np.float32)]

    candidates = [_result("a"), _result("b"), _result("c")]

    results = reranker.rerank("orders", candidates)

    assert len(results) == 2
    assert {result.card_id for result in results} == {"a", "b"}


def test_reranks_by_model_score() -> None:
    reranker, session, tokenizer = _reranker()

    tokenizer.return_value = {
        "input_ids": np.ones((3, 4), dtype=np.int64),
        "attention_mask": np.ones((3, 4), dtype=np.int64),
    }
    session.run.return_value = [
        np.array([[0.2], [1.5], [0.7]], dtype=np.float32),
    ]

    results = reranker.rerank(
        "orders",
        [_result("a"), _result("b"), _result("c")],
    )

    assert [result.card_id for result in results] == ["b", "c", "a"]
    assert [result.score for result in results] == pytest.approx([1.5, 0.7, 0.2])


def test_output_top_k_is_respected() -> None:
    reranker, session, tokenizer = _reranker(output_top_k=2)

    tokenizer.return_value = {
        "input_ids": np.ones((4, 4), dtype=np.int64),
        "attention_mask": np.ones((4, 4), dtype=np.int64),
    }
    session.run.return_value = [
        np.array([[0.1], [0.4], [0.9], [0.2]], dtype=np.float32),
    ]

    results = reranker.rerank(
        "orders",
        [_result("a"), _result("b"), _result("c"), _result("d")],
    )

    assert [result.card_id for result in results] == ["c", "b"]


def test_explicit_limit_can_exceed_output_top_k() -> None:
    reranker, session, tokenizer = _reranker(output_top_k=10)

    tokenizer.return_value = {
        "input_ids": np.ones((12, 4), dtype=np.int64),
        "attention_mask": np.ones((12, 4), dtype=np.int64),
    }
    session.run.return_value = [
        np.arange(12, dtype=np.float32).reshape(-1, 1),
    ]

    results = reranker.rerank(
        "orders",
        [_result(str(index)) for index in range(12)],
        limit=12,
    )

    assert len(results) == 12
    assert [result.card_id for result in results] == [str(index) for index in range(11, -1, -1)]


def test_batch_size_controls_inference_batches() -> None:
    reranker, session, tokenizer = _reranker(batch_size=2)

    tokenizer.side_effect = [
        {
            "input_ids": np.ones((2, 4), dtype=np.int64),
            "attention_mask": np.ones((2, 4), dtype=np.int64),
        },
        {
            "input_ids": np.ones((1, 4), dtype=np.int64),
            "attention_mask": np.ones((1, 4), dtype=np.int64),
        },
    ]

    session.run.side_effect = [
        [np.array([[0.1], [0.2]], dtype=np.float32)],
        [np.array([[0.3]], dtype=np.float32)],
    ]

    results = reranker.rerank(
        "orders",
        [_result("a"), _result("b"), _result("c")],
    )

    assert [result.card_id for result in results] == ["c", "b", "a"]
    assert session.run.call_count == 2
    assert tokenizer.call_count == 2
