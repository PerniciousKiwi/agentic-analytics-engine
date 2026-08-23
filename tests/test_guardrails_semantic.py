from __future__ import annotations

from cardinal.guardrails.semantic_check import (
    check_mode_question_shape,
    check_superlative,
)


def test_fastest_requires_ascending_order() -> None:
    result = check_superlative(
        """
        SELECT driverId
        FROM lapTimes
        WHERE lap = 1
        ORDER BY time ASC
        LIMIT 5
        """,
        "List the driver's ID with the fastest time during the first lap.",
    )

    assert result.allowed is True


def test_fastest_rejects_descending_order() -> None:
    result = check_superlative(
        """
        SELECT driverId
        FROM lapTimes
        WHERE lap = 1
        ORDER BY time DESC
        LIMIT 5
        """,
        "List the driver's ID with the fastest time during the first lap.",
    )

    assert result.allowed is False
    assert "SUPERLATIVE_MISMATCH" in result.reasons[0]


def test_slowest_requires_descending_order() -> None:
    result = check_superlative(
        """
        SELECT driverId
        FROM lapTimes
        ORDER BY time DESC
        LIMIT 1
        """,
        "Which driver had the slowest time?",
    )

    assert result.allowed is True


def test_slowest_rejects_ascending_order() -> None:
    result = check_superlative(
        """
        SELECT driverId
        FROM lapTimes
        ORDER BY time ASC
        LIMIT 1
        """,
        "Which driver had the slowest time?",
    )

    assert result.allowed is False
    assert "SUPERLATIVE_MISMATCH" in result.reasons[0]


def test_highest_requires_descending_order() -> None:
    result = check_superlative(
        """
        SELECT id, score
        FROM players
        ORDER BY score DESC
        LIMIT 1
        """,
        "Which player has the highest score?",
    )

    assert result.allowed is True


def test_lowest_requires_ascending_order() -> None:
    result = check_superlative(
        """
        SELECT id, score
        FROM players
        ORDER BY score ASC
        LIMIT 1
        """,
        "Which player has the lowest score?",
    )

    assert result.allowed is True


def test_most_common_is_not_checked_yet() -> None:
    result = check_superlative(
        """
        SELECT race, COUNT(*) AS count
        FROM superhero
        GROUP BY race
        ORDER BY count DESC
        LIMIT 1
        """,
        "What is the most common race?",
    )

    assert result.allowed is True


def test_question_without_superlative_is_unaffected() -> None:
    result = check_superlative(
        """
        SELECT driverId
        FROM lapTimes
        ORDER BY time DESC
        LIMIT 5
        """,
        "List five drivers.",
    )

    assert result.allowed is True


def test_mode_ambiguous_phrase_accepts_superlative_shape() -> None:
    result = check_mode_question_shape(
        """
        SELECT p.Body
        FROM posts AS p
        JOIN tags AS t
            ON p.Id = t.ExcerptPostId
        WHERE t.Count = (
            SELECT MAX(Count)
            FROM tags
        )
        """,
        (
            "From which post is the most popular tag excerpted from? "
            "Please give the body of the post."
        ),
    )

    assert result.allowed is True


def test_mode_strict_phrase_rejects_ungrouped_superlative() -> None:
    result = check_mode_question_shape(
        """
        SELECT race
        FROM superhero
        ORDER BY id DESC
        LIMIT 1
        """,
        "What is the most common race?",
    )

    assert result.allowed is False
    assert "MODE_MISMATCH" in result.reasons[0]
