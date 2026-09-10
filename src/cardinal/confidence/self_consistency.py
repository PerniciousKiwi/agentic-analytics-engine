from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from eval.execution_accuracy import rows_equal

GenerateCandidateFn = Callable[[], Awaitable[str]]
ExecuteCandidateFn = Callable[
    [str],
    Awaitable[list[list[Any]] | list[tuple[Any, ...]]],
]


@dataclass(frozen=True)
class ConsistencyRun:
    sql: str | None
    rows: list[list[Any]] | list[tuple[Any, ...]] | None
    execution_failed: bool


@dataclass(frozen=True)
class ConsistencyResult:
    runs: list[ConsistencyRun]
    agreement_rate: float


async def run_self_consistency(
    generate_candidate: GenerateCandidateFn,
    execute_candidate: ExecuteCandidateFn,
    *,
    sample_count: int = 5,
) -> ConsistencyResult:
    """Generate and execute multiple candidates concurrently."""

    generation_results = await asyncio.gather(
        *[
            _safe_generate(generate_candidate)
            for _ in range(sample_count)
        ]
    )

    execution_results = await asyncio.gather(
        *[
            _safe_execute(
                sql,
                execute_candidate,
            )
            for sql in generation_results
        ]
    )

    successful_rows = [
        run.rows
        for run in execution_results
        if not run.execution_failed
        and run.rows is not None
    ]

    score = _agreement_rate_with_failures(
        successful_rows,
        total_runs=sample_count,
    )

    return ConsistencyResult(
        runs=list(execution_results),
        agreement_rate=score,
    )


async def _safe_generate(
    generate_candidate: GenerateCandidateFn,
) -> str | None:
    try:
        return await generate_candidate()
    except Exception:
        return None


async def _safe_execute(
    sql: str | None,
    execute_candidate: ExecuteCandidateFn,
) -> ConsistencyRun:
    if not sql:
        return ConsistencyRun(
            sql=None,
            rows=None,
            execution_failed=True,
        )

    try:
        rows = await execute_candidate(sql)

        return ConsistencyRun(
            sql=sql,
            rows=rows,
            execution_failed=False,
        )

    except Exception:
        return ConsistencyRun(
            sql=sql,
            rows=None,
            execution_failed=True,
        )


def _agreement_rate_with_failures(
    successful_rows: list[
        list[list[Any]] | list[tuple[Any, ...]]
    ],
    *,
    total_runs: int,
) -> float:
    if total_runs <= 0 or not successful_rows:
        return 0.0

    clusters: list[
        list[list[list[Any]] | list[tuple[Any, ...]]]
    ] = []

    for rows in successful_rows:
        matched = False

        for cluster in clusters:
            representative = cluster[0]

            if rows_equal(
                representative,
                rows,
            ):
                cluster.append(rows)
                matched = True
                break

        if not matched:
            clusters.append([rows])

    largest_cluster = max(
        len(cluster)
        for cluster in clusters
    )

    return largest_cluster / total_runs