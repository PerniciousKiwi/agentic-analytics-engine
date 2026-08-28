from unittest.mock import Mock

from cardinal.retrieval.models import RetrievalResult
from cardinal.retrieval.service import RetrievalService


def _result(
    card_id: str,
    score: float,
) -> RetrievalResult:
    return RetrievalResult(
        card_id=card_id,
        card_type="table",
        domain="orders",
        card_name=card_id,
        card_text=f"TABLE: {card_id}",
        score=score,
    )


def test_lexical_mode_uses_postgres_store() -> None:
    lexical_store = Mock()
    dense_store = Mock()

    lexical_store.search.return_value = [
        {
            "card_id": "table:marts.fct_orders",
            "card_type": "table",
            "domain": "orders",
            "card_name": "fct_orders",
            "card_text": "TABLE: marts.fct_orders",
            "metadata": {},
            "score": 0.8,
        }
    ]

    service = RetrievalService(
        lexical_store=lexical_store,
        dense_store=dense_store,
    )

    response = service.retrieve(
        "orders",
        mode="lexical",
        limit=5,
    )

    assert response.mode == "lexical"
    assert len(response.results) == 1
    assert response.results[0].card_id == "table:marts.fct_orders"

    lexical_store.search.assert_called_once_with(
        "orders",
        limit=5,
    )
    dense_store.search.assert_not_called()


def test_dense_mode_uses_qdrant_store() -> None:
    lexical_store = Mock()
    dense_store = Mock()

    dense_store.search.return_value = [
        _result("table:marts.fct_orders", 0.91),
    ]

    service = RetrievalService(
        lexical_store=lexical_store,
        dense_store=dense_store,
    )

    response = service.retrieve(
        "orders",
        mode="dense",
        limit=5,
    )

    assert response.mode == "dense"
    assert len(response.results) == 1
    assert response.results[0].card_id == "table:marts.fct_orders"

    dense_store.search.assert_called_once_with(
        "orders",
        limit=5,
    )
    lexical_store.search.assert_not_called()


def test_blank_query_returns_empty_results() -> None:
    lexical_store = Mock()
    dense_store = Mock()

    service = RetrievalService(
        lexical_store=lexical_store,
        dense_store=dense_store,
    )

    response = service.retrieve(
        "   ",
        mode="dense",
    )

    assert response.results == []
    dense_store.search.assert_not_called()
    lexical_store.search.assert_not_called()


def test_non_positive_limit_returns_empty_results() -> None:
    lexical_store = Mock()
    dense_store = Mock()

    service = RetrievalService(
        lexical_store=lexical_store,
        dense_store=dense_store,
    )

    response = service.retrieve(
        "orders",
        mode="dense",
        limit=0,
    )

    assert response.results == []
    dense_store.search.assert_not_called()
    lexical_store.search.assert_not_called()


def test_hybrid_mode_deduplicates_cards() -> None:
    lexical_store = Mock()
    dense_store = Mock()
    reranker = Mock()

    lexical_store.search.return_value = [
        {
            "card_id": "table:marts.fct_orders",
            "card_type": "table",
            "domain": "orders",
            "card_name": "fct_orders",
            "card_text": "TABLE: marts.fct_orders",
            "metadata": {},
            "score": 0.7,
        },
        {
            "card_id": "table:marts.fct_customers",
            "card_type": "table",
            "domain": "customers",
            "card_name": "fct_customers",
            "card_text": "TABLE: marts.fct_customers",
            "metadata": {},
            "score": 0.6,
        },
    ]

    dense_store.search.return_value = [
        _result("table:marts.fct_orders", 0.9),
        _result("table:marts.fct_products", 0.8),
    ]

    reranker.input_top_k = 50
    reranker.rerank.side_effect = lambda query, results, limit: results[:limit]

    service = RetrievalService(
        lexical_store=lexical_store,
        dense_store=dense_store,
        reranker=reranker,
    )

    response = service.retrieve(
        "orders",
        mode="hybrid",
        limit=10,
    )

    assert len(response.results) == 3

    card_ids = [result.card_id for result in response.results]

    assert card_ids.count("table:marts.fct_orders") == 1
    assert "table:marts.fct_customers" in card_ids
    assert "table:marts.fct_products" in card_ids


def test_hybrid_mode_respects_limit() -> None:
    lexical_store = Mock()
    dense_store = Mock()
    reranker = Mock()

    lexical_store.search.return_value = [
        {
            "card_id": "table:marts.fct_orders",
            "card_type": "table",
            "domain": "orders",
            "card_name": "fct_orders",
            "card_text": "TABLE: marts.fct_orders",
            "metadata": {},
            "score": 0.7,
        },
    ]

    dense_store.search.return_value = [
        _result("table:marts.fct_customers", 0.9),
        _result("table:marts.fct_products", 0.8),
    ]

    reranker.input_top_k = 50
    reranker.rerank.side_effect = lambda query, results, limit: results[:limit]

    service = RetrievalService(
        lexical_store=lexical_store,
        dense_store=dense_store,
        reranker=reranker,
    )

    response = service.retrieve(
        "orders",
        mode="hybrid",
        limit=2,
    )

    assert len(response.results) == 2


def test_hybrid_mode_uses_reciprocal_rank_fusion() -> None:
    lexical_store = Mock()
    dense_store = Mock()
    reranker = Mock()

    lexical_store.search.return_value = [
        {
            "card_id": "table:marts.fct_orders",
            "card_type": "table",
            "domain": "orders",
            "card_name": "fct_orders",
            "card_text": "TABLE: marts.fct_orders",
            "metadata": {},
            "score": 0.1,
        },
        {
            "card_id": "table:marts.fct_customers",
            "card_type": "table",
            "domain": "customers",
            "card_name": "fct_customers",
            "card_text": "TABLE: marts.fct_customers",
            "metadata": {},
            "score": 0.99,
        },
    ]

    dense_store.search.return_value = [
        _result("table:marts.fct_customers", 0.1),
        _result("table:marts.fct_orders", 0.99),
    ]

    reranker.input_top_k = 50
    reranker.rerank.side_effect = lambda query, results, limit: results[:limit]

    service = RetrievalService(
        lexical_store=lexical_store,
        dense_store=dense_store,
        reranker=reranker,
    )

    response = service.retrieve(
        "orders",
        mode="hybrid",
        limit=2,
    )

    assert len(response.results) == 2

    # Both cards occur at rank 1 and rank 2 across the two systems,
    # so their RRF scores should be identical.
    assert response.results[0].score == response.results[1].score

    # Tie-breaking is deterministic by card_id.
    assert response.results[0].card_id == "table:marts.fct_customers"
    assert response.results[1].card_id == "table:marts.fct_orders"

    reranker.rerank.assert_called_once()
