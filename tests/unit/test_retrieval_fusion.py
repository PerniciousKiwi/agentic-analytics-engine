from cardinal.retrieval.fusion import ReciprocalRankFusion
from cardinal.retrieval.models import RetrievalResult


def _result(card_id: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        card_id=card_id,
        card_type="table",
        domain="orders",
        card_name=card_id,
        card_text=f"TABLE: {card_id}",
        score=score,
    )


def test_fuses_ranked_lists() -> None:
    fusion = ReciprocalRankFusion(k=60)

    result = fusion.fuse(
        [
            [
                _result("table:a", 0.9),
                _result("table:b", 0.8),
            ],
            [
                _result("table:b", 0.95),
                _result("table:a", 0.7),
            ],
        ],
        limit=2,
    )

    assert len(result) == 2
    assert result[0].card_id == "table:a"
    assert result[1].card_id == "table:b"

    expected = (1 / 61) + (1 / 62)
    assert result[0].score == expected
    assert result[1].score == expected


def test_deduplicates_cards() -> None:
    fusion = ReciprocalRankFusion(k=60)

    result = fusion.fuse(
        [
            [_result("table:a", 0.9)],
            [_result("table:a", 0.8)],
        ],
        limit=10,
    )

    assert len(result) == 1
    assert result[0].card_id == "table:a"


def test_respects_limit() -> None:
    fusion = ReciprocalRankFusion(k=60)

    result = fusion.fuse(
        [
            [
                _result("table:a", 0.9),
                _result("table:b", 0.8),
                _result("table:c", 0.7),
            ],
        ],
        limit=2,
    )

    assert len(result) == 2


def test_tie_breaking_is_deterministic() -> None:
    fusion = ReciprocalRankFusion(k=60)

    result = fusion.fuse(
        [
            [_result("table:z", 0.9)],
            [_result("table:a", 0.8)],
        ],
        limit=2,
    )

    assert [item.card_id for item in result] == [
        "table:a",
        "table:z",
    ]


def test_invalid_k_is_rejected() -> None:
    try:
        ReciprocalRankFusion(k=0)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")


def test_non_positive_limit_returns_empty() -> None:
    fusion = ReciprocalRankFusion()

    assert fusion.fuse([[_result("table:a", 0.9)]], limit=0) == []
