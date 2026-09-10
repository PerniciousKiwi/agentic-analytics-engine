from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import psycopg
import yaml

from cardinal.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]

OLIST_SUITE_PATH = (
    PROJECT_ROOT
    / "eval"
    / "suites"
    / "olist_gold_150.jsonl"
)

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


def load_olist_suite() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with OLIST_SUITE_PATH.open(
        encoding="utf-8",
    ) as file:
        for line in file:
            line = line.strip()

            if line:
                rows.append(json.loads(line))

    return rows


def compute_warehouse_bounds() -> dict[str, str | None]:
    settings = get_settings()

    with (
        psycopg.connect(
            host=settings.warehouse_ro_host,
            port=settings.warehouse_ro_port,
            dbname=settings.warehouse_ro_db,
            user=settings.warehouse_ro_user,
            password=settings.warehouse_ro_password,
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT
                MIN(order_purchase_timestamp),
                MAX(order_purchase_timestamp)
            FROM marts.fct_orders
            """
        )

        row = cursor.fetchone()

    minimum, maximum = row if row is not None else (None, None)

    return {
        "min_order_purchase_timestamp": (
            minimum.isoformat()
            if minimum is not None
            else None
        ),
        "max_order_purchase_timestamp": (
            maximum.isoformat()
            if maximum is not None
            else None
        ),
    }


def write_warehouse_bounds() -> Path:
    bounds = compute_warehouse_bounds()

    WAREHOUSE_BOUNDS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    WAREHOUSE_BOUNDS_PATH.write_text(
        yaml.safe_dump(
            bounds,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    return WAREHOUSE_BOUNDS_PATH


def compute_gold_row_count_medians(
    execute_sql,
) -> dict[str, float]:
    counts: dict[str, list[int]] = defaultdict(list)

    for record in load_olist_suite():
        if record.get("answerable") is False:
            continue

        category = str(record["category"])
        gold_sql = str(record["gold_sql"])

        rows = execute_sql(gold_sql)

        counts[category].append(len(rows))

    return {
        category: float(statistics.median(values))
        for category, values in sorted(counts.items())
    }


def write_row_count_reference(
    execute_sql,
) -> Path:
    medians = compute_gold_row_count_medians(
        execute_sql,
    )

    ROW_COUNT_REFERENCE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ROW_COUNT_REFERENCE_PATH.write_text(
        yaml.safe_dump(
            medians,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    return ROW_COUNT_REFERENCE_PATH