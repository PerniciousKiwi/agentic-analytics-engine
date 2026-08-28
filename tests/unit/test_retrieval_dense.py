from unittest.mock import MagicMock

from cardinal.retrieval.dense import DenseRetriever


def test_blank_query_returns_empty() -> None:
    client = MagicMock()
    model = MagicMock()

    retriever = DenseRetriever(
        client=client,
        model=model,
    )

    assert retriever.search("   ") == []

    model.encode.assert_not_called()
    client.query_points.assert_not_called()


def test_top_k_is_loaded_from_config(tmp_path) -> None:
    config = tmp_path / "retrieval.yaml"
    config.write_text(
        """
dense:
  top_k: 25
""",
        encoding="utf-8",
    )

    retriever = DenseRetriever(
        client=MagicMock(),
        model=MagicMock(),
        config_path=config,
    )

    assert retriever.top_k == 25


def test_limit_cannot_exceed_configured_top_k(tmp_path) -> None:
    config = tmp_path / "retrieval.yaml"
    config.write_text(
        """
dense:
  top_k: 25
""",
        encoding="utf-8",
    )

    client = MagicMock()
    model = MagicMock()

    client.query_points.return_value.points = []

    retriever = DenseRetriever(
        client=client,
        model=model,
        config_path=config,
    )

    retriever.search("customer", limit=100)

    kwargs = client.query_points.call_args.kwargs

    assert kwargs["limit"] == 25


def test_search_returns_ranked_card_scores(tmp_path) -> None:
    config = tmp_path / "retrieval.yaml"
    config.write_text(
        """
dense:
  top_k: 50
""",
        encoding="utf-8",
    )

    client = MagicMock()
    model = MagicMock()

    model.encode.return_value.tolist.return_value = [
        0.1,
        0.2,
        0.3,
    ]

    first = MagicMock()
    first.payload = {"card_id": "metric:revenue"}
    first.score = 0.91

    second = MagicMock()
    second.payload = {"card_id": "table:marts.fct_orders"}
    second.score = 0.82

    client.query_points.return_value.points = [
        first,
        second,
    ]

    retriever = DenseRetriever(
        client=client,
        model=model,
        config_path=config,
    )

    result = retriever.search("revenue")

    assert result == [
        ("metric:revenue", 0.91),
        ("table:marts.fct_orders", 0.82),
    ]

    model.encode.assert_called_once_with(
        "revenue",
        normalize_embeddings=True,
    )
