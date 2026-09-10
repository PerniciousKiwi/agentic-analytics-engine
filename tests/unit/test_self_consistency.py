import asyncio

import pytest

from cardinal.confidence.self_consistency import (
    run_self_consistency,
)


@pytest.mark.asyncio
async def test_self_consistency_three_of_five_match() -> None:
    sql_outputs = iter(
        [
            "sql_1",
            "sql_2",
            "sql_3",
            "sql_4",
            "sql_5",
        ]
    )

    async def generate_candidate() -> str:
        await asyncio.sleep(0)
        return next(sql_outputs)

    async def execute_candidate(sql: str):
        if sql in {
            "sql_1",
            "sql_2",
            "sql_3",
        }:
            return [[1], [2]]

        if sql == "sql_4":
            return [[3]]

        return [[4]]

    result = await run_self_consistency(
        generate_candidate,
        execute_candidate,
    )

    assert len(result.runs) == 5
    assert result.agreement_rate == 0.6


@pytest.mark.asyncio
async def test_self_consistency_counts_failed_execution_in_denominator() -> None:
    sql_outputs = iter(
        [
            "sql_1",
            "sql_2",
            "sql_3",
            "sql_4",
            "sql_5",
        ]
    )

    async def generate_candidate() -> str:
        return next(sql_outputs)

    async def execute_candidate(sql: str):
        if sql == "sql_5":
            raise RuntimeError("execution failed")

        return [[1]]

    result = await run_self_consistency(
        generate_candidate,
        execute_candidate,
    )

    assert result.agreement_rate == 0.8
    assert result.runs[-1].execution_failed is True


@pytest.mark.asyncio
async def test_self_consistency_all_fail() -> None:
    async def generate_candidate() -> str:
        return "SELECT 1"

    async def execute_candidate(sql: str):
        raise RuntimeError("execution failed")

    result = await run_self_consistency(
        generate_candidate,
        execute_candidate,
    )

    assert result.agreement_rate == 0.0
    assert all(
        run.execution_failed
        for run in result.runs
    )