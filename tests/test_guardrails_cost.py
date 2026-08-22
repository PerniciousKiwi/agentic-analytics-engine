from cardinal.guardrails.cost_check import CostBudget, check_cost


def cheap_explain(_sql: str) -> dict:
    return {
        "Plan": {
            "Node Type": "Seq Scan",
            "Total Cost": 12.5,
            "Plan Rows": 100,
            "Plans": [],
        }
    }


def expensive_explain(_sql: str) -> dict:
    return {
        "Plan": {
            "Node Type": "Seq Scan",
            "Total Cost": 5_000_000.0,
            "Plan Rows": 80_000_000,
            "Plans": [],
        }
    }


def test_cheap_query_passes() -> None:
    budget = CostBudget(
        max_cost=100_000,
        max_rows=1_000_000,
    )

    result = check_cost(
        "SELECT 1",
        cheap_explain,
        budget,
    )

    assert result.allowed is True
    assert result.reasons == []


def test_expensive_query_rejected() -> None:
    budget = CostBudget(
        max_cost=100_000,
        max_rows=1_000_000,
    )

    result = check_cost(
        "SELECT 1",
        expensive_explain,
        budget,
    )

    assert result.allowed is False
    assert "COST_LIMIT_EXCEEDED" in result.reasons[0]


def test_query_at_exact_cost_limit_passes() -> None:
    budget = CostBudget(max_cost=100_000)

    def explain(_sql: str) -> dict:
        return {
            "Plan": {
                "Total Cost": 100_000,
            }
        }

    result = check_cost("SELECT 1", explain, budget)

    assert result.allowed is True


def test_query_just_above_cost_limit_is_rejected() -> None:
    budget = CostBudget(max_cost=100_000)

    def explain(_sql: str) -> dict:
        return {
            "Plan": {
                "Total Cost": 100_000.01,
            }
        }

    result = check_cost("SELECT 1", explain, budget)

    assert result.allowed is False


def test_custom_max_rows_is_preserved() -> None:
    budget = CostBudget(
        max_cost=100_000,
        max_rows=50_000,
    )

    assert budget.max_rows == 50_000


def test_default_max_rows() -> None:
    budget = CostBudget(max_cost=100_000)

    assert budget.max_rows == 1_000_000
