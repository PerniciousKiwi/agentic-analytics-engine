from __future__ import annotations

import pytest
from eval.systems.oracle import OracleSystem


def test_oracle_returns_gold_sql() -> None:
    system = OracleSystem()

    predicted_sql, metadata = system.answer(
        "How many orders are there?",
        {"gold_sql": "SELECT COUNT(*) FROM orders;"},
    )

    assert predicted_sql == "SELECT COUNT(*) FROM orders;"
    assert metadata == {}


def test_oracle_does_not_modify_gold_sql() -> None:
    system = OracleSystem()

    gold_sql = "  SELECT * FROM orders\nWHERE id = 1;  "

    predicted_sql, _ = system.answer(
        "Some question",
        {"gold_sql": gold_sql},
    )

    assert predicted_sql == gold_sql


def test_oracle_requires_gold_sql() -> None:
    system = OracleSystem()

    with pytest.raises(ValueError, match="gold_sql"):
        system.answer(
            "Some question",
            {},
        )


def test_oracle_rejects_empty_gold_sql() -> None:
    system = OracleSystem()

    with pytest.raises(ValueError, match="gold_sql"):
        system.answer(
            "Some question",
            {"gold_sql": "   "},
        )
