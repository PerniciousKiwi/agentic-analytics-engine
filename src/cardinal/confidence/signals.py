from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from numbers import Real
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]

WAREHOUSE_BOUNDS_PATH = (
    PROJECT_ROOT
    / "configs"
    / "warehouse_bounds.yaml"
)

ROW_COUNT_REFERENCE_PATH = (
    PROJECT_ROOT
    / "configs"
    / "row_count_reference.yaml"
)


@dataclass(frozen=True)
class FeatureVector:
    """Confidence features for one analytical question."""

    agreement_rate: float

    empty_result: int
    negative_value: int
    high_null_rate: int
    excessive_row_count: int
    date_out_of_bounds: int
    warehouse_checks_applicable: int

    grounding_score: float

    top_rrf_score: float
    reranker_margin: float
    retrieval_signals_available: int

    repair_attempts: int
    guardrail_failures: int
    estimated_query_cost: float
    agent_steps: int

    execution_failed: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def load_warehouse_bounds() -> dict[str, Any]:
    if not WAREHOUSE_BOUNDS_PATH.exists():
        return {}

    data = yaml.safe_load(
        WAREHOUSE_BOUNDS_PATH.read_text(
            encoding="utf-8",
        )
    )

    return data if isinstance(data, dict) else {}


def load_row_count_reference() -> dict[str, float]:
    if not ROW_COUNT_REFERENCE_PATH.exists():
        return {}

    data = yaml.safe_load(
        ROW_COUNT_REFERENCE_PATH.read_text(
            encoding="utf-8",
        )
    )

    if not isinstance(data, dict):
        return {}

    return {
        str(key): float(value)
        for key, value in data.items()
        if isinstance(value, Real)
    }


def empty_result_signal(
    rows: list[list[Any]] | list[tuple[Any, ...]],
) -> int:
    return int(len(rows) == 0)


def high_null_rate_signal(
    rows: list[list[Any]] | list[tuple[Any, ...]],
    *,
    threshold: float = 0.5,
) -> int:
    if not rows:
        return 0

    total_values = sum(len(row) for row in rows)

    if total_values == 0:
        return 0

    null_values = sum(
        value is None
        for row in rows
        for value in row
    )

    null_rate = null_values / total_values

    return int(null_rate > threshold)


def negative_value_signal(
    columns: list[str],
    rows: list[list[Any]] | list[tuple[Any, ...]],
    non_negative_fields: set[str],
) -> int:
    if not columns or not rows or not non_negative_fields:
        return 0

    normalized_fields = {
        field.lower()
        for field in non_negative_fields
    }

    for column_index, column_name in enumerate(columns):
        if column_name.lower() not in normalized_fields:
            continue

        for row in rows:
            if column_index >= len(row):
                continue

            value = row[column_index]

            if (
                isinstance(value, Real)
                and not isinstance(value, bool)
                and float(value) < 0
            ):
                return 1

    return 0


def excessive_row_count_signal(
    row_count: int,
    category: str | None,
    references: dict[str, float],
    *,
    multiplier: float = 10.0,
) -> int:
    if category is None:
        return 0

    reference = references.get(category)

    if reference is None:
        return 0

    if reference <= 0:
        return 0

    return int(
        row_count > multiplier * reference
    )


def date_out_of_bounds_signal(
    rows: list[list[Any]] | list[tuple[Any, ...]],
    warehouse_bounds: dict[str, Any],
) -> int:
    minimum_raw = warehouse_bounds.get(
        "min_order_purchase_timestamp"
    )
    maximum_raw = warehouse_bounds.get(
        "max_order_purchase_timestamp"
    )

    if not minimum_raw or not maximum_raw:
        return 0

    minimum = _parse_datetime(minimum_raw)
    maximum = _parse_datetime(maximum_raw)

    if minimum is None or maximum is None:
        return 0

    for row in rows:
        for value in row:
            candidate = _coerce_datetime(value)

            if candidate is None:
                continue

            if candidate < minimum or candidate > maximum:
                return 1

    return 0


def build_failure_feature_vector() -> FeatureVector:
    """Return the deterministic sentinel for total execution failure."""

    return FeatureVector(
        agreement_rate=0.0,
        empty_result=0,
        negative_value=0,
        high_null_rate=0,
        excessive_row_count=0,
        date_out_of_bounds=0,
        warehouse_checks_applicable=0,
        grounding_score=0.0,
        top_rrf_score=0.0,
        reranker_margin=0.0,
        retrieval_signals_available=0,
        repair_attempts=0,
        guardrail_failures=0,
        estimated_query_cost=0.0,
        agent_steps=0,
        execution_failed=1,
    )


def _parse_datetime(
    value: Any,
) -> datetime | None:
    if isinstance(value, datetime):
        return value

    if not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None


def _coerce_datetime(
    value: Any,
) -> datetime | None:
    if isinstance(value, datetime):
        return value

    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        try:
            return datetime(
                value.year,
                value.month,
                value.day,
            )
        except (TypeError, ValueError):
            return None

    if isinstance(value, str):
        return _parse_datetime(value)

    return None

def agreement_rate(
    result_sets: Sequence[
        Sequence[Sequence[Any]]
    ],
    *,
    comparator=None,
) -> float:
    if comparator is None:
        def comparator(left, right):
            return left == right
    """Return the size of the largest equivalent-result cluster / N."""

    if not result_sets:
        return 0.0

    clusters: list[
        list[Sequence[Sequence[Any]]]
    ] = []

    for candidate in result_sets:
        matched = False

        for cluster in clusters:
            representative = cluster[0]

            if comparator(
                representative,
                candidate,
            ):
                cluster.append(candidate)
                matched = True
                break

        if not matched:
            clusters.append([candidate])

    largest_cluster = max(
        len(cluster)
        for cluster in clusters
    )

    return largest_cluster / len(result_sets)


def sanity_checks(
    rows,
    columns,
    non_negative_columns=None,
):
    """Run lightweight result-set sanity checks."""

    non_negative_columns = set(
        non_negative_columns or []
    )

    failures: list[str] = []

    if not rows:
        failures.append("empty_result")

    column_indexes = {
        column: index
        for index, column in enumerate(columns)
    }

    for column in non_negative_columns:
        index = column_indexes.get(column)

        if index is None:
            continue

        for row in rows:
            if index >= len(row):
                continue

            value = row[index]

            if (
                isinstance(value, (int, float))
                and value < 0
            ):
                failures.append("negative_value")
                break

    total_values = sum(
        len(row)
        for row in rows
    )

    null_values = sum(
        value is None
        for row in rows
        for value in row
    )

    if (
        total_values > 0
        and null_values / total_values > 0.5
    ):
        failures.append("high_null_rate")

    return {
        "flagged": bool(failures),
        "failures": failures,
        "count": len(failures),
    }


def build_feature_vector(
    *,
    agreement: float,
    columns: list[str],
    rows: list[list[Any]] | list[tuple[Any, ...]],
    category: str | None,
    source: str,
    grounding: float,
    top_rrf_score: float | None,
    reranker_margin: float | None,
    repair_attempts: int,
    guardrail_failures: int,
    estimated_query_cost: float | None,
    agent_steps: int,
    non_negative_fields: set[str] | None = None,
    row_count_references: dict[str, float] | None = None,
    warehouse_bounds: dict[str, Any] | None = None,
    execution_failed: bool = False,
) -> FeatureVector:
    """Assemble all confidence signals into one flat feature vector."""

    if execution_failed:
        return build_failure_feature_vector()

    is_olist = source == "postgres"

    non_negative_fields = non_negative_fields or set()
    row_count_references = row_count_references or {}
    warehouse_bounds = warehouse_bounds or {}

    empty_result = empty_result_signal(rows)
    high_null_rate = high_null_rate_signal(rows)

    if is_olist:
        negative_value = negative_value_signal(
            columns,
            rows,
            non_negative_fields,
        )

        excessive_row_count = excessive_row_count_signal(
            len(rows),
            category,
            row_count_references,
        )

        date_out_of_bounds = date_out_of_bounds_signal(
            rows,
            warehouse_bounds,
        )

        warehouse_checks_applicable = 1

    else:
        negative_value = 0
        excessive_row_count = 0
        date_out_of_bounds = 0
        warehouse_checks_applicable = 0

    retrieval_available = int(
        top_rrf_score is not None
        and reranker_margin is not None
    )

    return FeatureVector(
        agreement_rate=float(agreement),
        empty_result=empty_result,
        negative_value=negative_value,
        high_null_rate=high_null_rate,
        excessive_row_count=excessive_row_count,
        date_out_of_bounds=date_out_of_bounds,
        warehouse_checks_applicable=warehouse_checks_applicable,
        grounding_score=float(grounding),
        top_rrf_score=(
            float(top_rrf_score)
            if top_rrf_score is not None
            else 0.0
        ),
        reranker_margin=(
            float(reranker_margin)
            if reranker_margin is not None
            else 0.0
        ),
        retrieval_signals_available=retrieval_available,
        repair_attempts=int(repair_attempts),
        guardrail_failures=int(guardrail_failures),
        estimated_query_cost=(
            float(estimated_query_cost)
            if estimated_query_cost is not None
            else 0.0
        ),
        agent_steps=int(agent_steps),
        execution_failed=0,
    )