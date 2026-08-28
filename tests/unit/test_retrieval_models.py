from cardinal.retrieval.models import RetrievalResponse, RetrievalResult


def test_retrieval_result_defaults_metadata() -> None:
    result = RetrievalResult(
        card_id="table:marts.fct_orders",
        card_type="table",
        domain="orders",
        card_name="fct_orders",
        card_text="TABLE: marts.fct_orders",
        score=0.95,
    )

    assert result.metadata == {}


def test_retrieval_response_contains_results() -> None:
    result = RetrievalResult(
        card_id="column:marts.fct_orders.order_id",
        card_type="column",
        domain="orders",
        card_name="order_id",
        card_text="COLUMN: marts.fct_orders.order_id",
        score=0.9,
    )

    response = RetrievalResponse(
        query="orders",
        mode="lexical",
        results=[result],
    )

    assert response.query == "orders"
    assert response.mode == "lexical"
    assert len(response.results) == 1
    assert response.results[0].card_id == "column:marts.fct_orders.order_id"


def test_retrieval_response_defaults_to_empty_results() -> None:
    response = RetrievalResponse(
        query="customer",
        mode="dense",
    )

    assert response.results == []
