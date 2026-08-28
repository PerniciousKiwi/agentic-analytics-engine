from unittest.mock import MagicMock

from cardinal.retrieval.sparse import SparseRetriever


def test_blank_query_returns_empty() -> None:
    engine = MagicMock()

    retriever = SparseRetriever(engine=engine)

    assert retriever.search("   ") == []
    engine.connect.assert_not_called()


def test_top_k_is_loaded_from_config(tmp_path) -> None:
    config = tmp_path / "retrieval.yaml"
    config.write_text(
        """
sparse:
  top_k: 25
""",
        encoding="utf-8",
    )

    retriever = SparseRetriever(
        engine=MagicMock(),
        config_path=config,
    )

    assert retriever.top_k == 25


def test_limit_cannot_exceed_configured_top_k(tmp_path) -> None:
    config = tmp_path / "retrieval.yaml"
    config.write_text(
        """
sparse:
  top_k: 25
""",
        encoding="utf-8",
    )

    retriever = SparseRetriever(
        engine=MagicMock(),
        config_path=config,
    )

    connection = MagicMock()
    retriever.engine.connect.return_value.__enter__.return_value = connection
    connection.execute.return_value.mappings.return_value.all.return_value = []

    retriever.search("customer", limit=100)

    params = connection.execute.call_args.args[1]

    assert params["limit"] == 25


def test_search_returns_ranked_card_scores(tmp_path) -> None:
    config = tmp_path / "retrieval.yaml"
    config.write_text(
        """
sparse:
  top_k: 50
""",
        encoding="utf-8",
    )

    engine = MagicMock()
    retriever = SparseRetriever(
        engine=engine,
        config_path=config,
    )

    connection = MagicMock()
    retriever.engine.connect.return_value.__enter__.return_value = connection
    connection.execute.return_value.mappings.return_value.all.return_value = [
        {"card_id": "metric:revenue", "score": 0.5},
        {"card_id": "table:marts.fct_orders", "score": 0.2},
    ]

    result = retriever.search("revenue")

    assert result == [
        ("metric:revenue", 0.5),
        ("table:marts.fct_orders", 0.2),
    ]
