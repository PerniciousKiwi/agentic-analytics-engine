from unittest.mock import Mock

from cardinal.catalog.cards import TableCard
from cardinal.retrieval.qdrant import QdrantCardStore


def test_point_id_is_deterministic() -> None:
    first = QdrantCardStore._point_id("table:marts.fct_orders")
    second = QdrantCardStore._point_id("table:marts.fct_orders")

    assert first == second
    assert first >= 0


def test_point_id_differs_for_different_cards() -> None:
    first = QdrantCardStore._point_id("table:marts.fct_orders")
    second = QdrantCardStore._point_id("table:marts.fct_products")

    assert first != second


def test_metadata_for_table_card() -> None:
    card = TableCard(
        card_id="table:marts.fct_orders",
        domain="orders",
        card_name="fct_orders",
        card_description="Orders.",
        schema_name="marts",
        table_name="fct_orders",
        row_count=100,
    )

    metadata = QdrantCardStore._metadata(card)

    assert metadata["schema_name"] == "marts"
    assert metadata["table_name"] == "fct_orders"
    assert metadata["row_count"] == 100


def test_search_returns_empty_for_blank_query() -> None:
    client = Mock()
    model = Mock()

    store = QdrantCardStore(
        client=client,
        model=model,
    )

    result = store.search("   ")

    assert result == []
    model.encode.assert_not_called()
    client.query_points.assert_not_called()
