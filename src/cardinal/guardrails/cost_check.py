from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from cardinal.guardrails.ast_checks import GuardResult


class CostBudget(BaseModel):
    max_cost: float
    max_rows: int = 1_000_000


def check_cost(
    sql: str,
    explain: Callable[[str], dict],
    budget: CostBudget,
) -> GuardResult:
    plan = explain(sql)

    cost = float(plan["Plan"]["Total Cost"])

    if cost > budget.max_cost:
        return GuardResult(
            allowed=False,
            reasons=[f"COST_LIMIT_EXCEEDED: {cost} > {budget.max_cost}"],
        )

    return GuardResult(allowed=True)
