from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from eval.execution_accuracy import rows_equal
from eval.systems.baseline import BaselineSystem
from eval.systems.oracle import OracleSystem
from eval.systems.protocol import EvaluationSystem

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "eval.yaml"
RESULTS_DIR = PROJECT_ROOT / "results"

RESULT_FIELDS = (
    "question",
    "gold_sql",
    "predicted_sql",
    "executed_ok",
    "correct",
    "latency_ms",
    "tokens_in",
    "tokens_out",
    "prompt_hash",
    "confidence",
    "abstained",
    "failure_class",
)

SYSTEMS: dict[str, type[EvaluationSystem]] = {
    "baseline": BaselineSystem,
    "oracle": OracleSystem,
}


def load_suite(path: Path) -> list[dict[str, Any]]:
    """Load and validate a JSONL evaluation suite."""
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc

            if not isinstance(record, dict):
                raise ValueError(f"Suite line {line_number} must contain a JSON object.")

            if "question" not in record:
                raise ValueError(f"Suite line {line_number} is missing 'question'.")

            answerable = record.get("answerable", True)

            if not isinstance(answerable, bool):
                raise ValueError(f"Suite line {line_number} field 'answerable' must be boolean.")

            if answerable and "gold_sql" not in record:
                raise ValueError(f"Suite line {line_number} is answerable but missing 'gold_sql'.")

            rows.append(record)

    if not rows:
        raise ValueError(f"Evaluation suite is empty: {path}")

    return rows


def load_config() -> dict[str, Any]:
    """Load eval.yaml."""
    import yaml

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError("configs/eval.yaml must contain a mapping.")

    return config


def resolve_suite_path(
    config: dict[str, Any],
    suite: str,
) -> Path:
    """Resolve a suite name to its JSONL file."""
    if suite == "bird_dev_200":
        path = PROJECT_ROOT / config["bird"]["questions_path"]
    elif suite == "olist_gold_150":
        path = PROJECT_ROOT / config["olist_gold_path"]
    elif suite == "ambiguity_100":
        path = PROJECT_ROOT / config["ambiguity_path"]
    else:
        raise ValueError(f"Unknown evaluation suite: {suite}")

    if not path.exists():
        raise FileNotFoundError(f"Evaluation suite does not exist: {path}")

    return path


def resolve_system(name: str) -> EvaluationSystem:
    """Instantiate a registered evaluation system."""
    try:
        system_class = SYSTEMS[name]
    except KeyError as exc:
        available = ", ".join(sorted(SYSTEMS))
        raise ValueError(f"Unknown system '{name}'. Available systems: {available}") from exc

    return system_class()


def resolve_database_path(
    record: dict[str, Any],
    config: dict[str, Any],
) -> Path:
    """Resolve the SQLite database used by a BIRD question."""
    db_id = record.get("db_id")

    if not isinstance(db_id, str) or not db_id:
        raise ValueError("BIRD evaluation records require a non-empty 'db_id'.")

    database_root = PROJECT_ROOT / config["bird"]["databases_path"]
    database_path = database_root / db_id / f"{db_id}.sqlite"

    if not database_path.exists():
        raise FileNotFoundError(f"BIRD database does not exist: {database_path}")

    return database_path


def execute_sql(
    sql: str,
    database_path: Path,
) -> list[tuple[Any, ...]]:
    """Execute SQL against a SQLite database and return rows."""
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(sql)
        return cursor.fetchall()


def execute_postgres_sql(sql: str) -> list[tuple[Any, ...]]:
    """Execute SQL against the Cardinal PostgreSQL warehouse."""
    with (
        psycopg.connect(
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            dbname=os.environ["POSTGRES_DB"],
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(sql)
        return cursor.fetchall()


def build_result_record(
    *,
    question: str,
    gold_sql: str | None,
    predicted_sql: str | None,
    executed_ok: bool,
    correct: bool,
    latency_ms: float,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build the stable Phase 2 per-question result schema."""
    return {
        "question": question,
        "gold_sql": gold_sql,
        "predicted_sql": predicted_sql,
        "executed_ok": executed_ok,
        "correct": correct,
        "latency_ms": latency_ms,
        "tokens_in": metadata.get("tokens_in"),
        "tokens_out": metadata.get("tokens_out"),
        "prompt_hash": metadata.get("prompt_hash"),
        "confidence": metadata.get("confidence"),
        "abstained": metadata.get("abstained", False),
        "failure_class": metadata.get("failure_class"),
    }


def run_suite(
    suite: list[dict[str, Any]],
    system: EvaluationSystem,
    config: dict[str, Any],
    suite_name: str,
) -> list[dict[str, Any]]:
    """Run every question in a suite through the selected system."""
    results: list[dict[str, Any]] = []
    float_tolerance = float(config["float_tolerance"])

    for record in suite:
        question = str(record["question"])
        answerable = record.get("answerable", True)

        gold_sql = record.get("gold_sql")
        if gold_sql is not None:
            gold_sql = str(gold_sql)

        predicted_sql: str | None = None
        metadata: dict[str, Any] = {}
        executed_ok = False
        correct = False

        start = time.perf_counter()

        try:
            # Unanswerable records are negative evaluation examples.
            #
            # The Phase 2 oracle knows that no valid SQL answer exists,
            # so the correct behavior is abstention. There is deliberately
            # no SQL execution for these records.
            if answerable is False:
                metadata["abstained"] = True
                correct = True
                executed_ok = False

            else:
                if suite_name == "bird_dev_200":
                    database_path = resolve_database_path(
                        record,
                        config,
                    )

                    db_context = {
                        "source": "sqlite",
                        "db_id": record.get("db_id"),
                        "database_path": database_path,
                        "gold_sql": gold_sql,
                    }

                    predicted_sql, metadata = system.answer(
                        question,
                        db_context,
                    )

                    if not predicted_sql:
                        raise ValueError("Evaluation system returned no predicted SQL.")

                    predicted_rows = execute_sql(
                        predicted_sql,
                        database_path,
                    )

                    gold_rows = execute_sql(
                        gold_sql,
                        database_path,
                    )

                elif suite_name == "olist_gold_150":
                    db_context = {
                        "source": "postgres",
                        "db_id": None,
                        "database_path": None,
                        "gold_sql": gold_sql,
                    }

                    predicted_sql, metadata = system.answer(
                        question,
                        db_context,
                    )

                    if not predicted_sql:
                        raise ValueError("Evaluation system returned no predicted SQL.")

                    predicted_rows = execute_postgres_sql(predicted_sql)

                    gold_rows = execute_postgres_sql(gold_sql)

                else:
                    raise NotImplementedError(
                        f"Execution is not implemented for suite: {suite_name}"
                    )

                executed_ok = True
                correct = rows_equal(
                    gold_rows,
                    predicted_rows,
                    float_tol=float_tolerance,
                )

        except (
            sqlite3.Error,
            psycopg.Error,
            ValueError,
            TypeError,
            KeyError,
        ):
            executed_ok = False
            correct = False

        latency_ms = (time.perf_counter() - start) * 1000

        results.append(
            build_result_record(
                question=question,
                gold_sql=gold_sql,
                predicted_sql=predicted_sql,
                executed_ok=executed_ok,
                correct=correct,
                latency_ms=latency_ms,
                metadata=metadata,
            )
        )

    return results


def write_results(
    suite_name: str,
    results: list[dict[str, Any]],
) -> Path:
    """Write timestamped evaluation results."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"{suite_name}_{timestamp}.json"

    payload = {
        "suite": suite_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "results": results,
    }

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")

    return output_path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run a Cardinal evaluation suite.")
    parser.add_argument(
        "--suite",
        required=True,
        choices=(
            "bird_dev_200",
            "olist_gold_150",
            "ambiguity_100",
        ),
    )
    parser.add_argument(
        "--system",
        required=True,
        choices=tuple(sorted(SYSTEMS)),
    )
    return parser.parse_args()


def main() -> None:
    """Run the requested evaluation suite."""
    args = parse_args()

    config = load_config()
    suite_path = resolve_suite_path(
        config,
        args.suite,
    )
    suite = load_suite(suite_path)
    system = resolve_system(args.system)

    print(f"Suite:       {args.suite}")
    print(f"System:      {args.system}")
    print(f"Questions:   {len(suite)}")

    try:
        results = run_suite(
            suite_name=args.suite,
            suite=suite,
            system=system,
            config=config,
        )
    finally:
        close = getattr(system, "close", None)
        if callable(close):
            close()

    output_path = write_results(
        suite_name=args.suite,
        results=results,
    )

    execution_accuracy = sum(result["correct"] for result in results) / len(results)

    print(f"Accuracy:    {execution_accuracy:.2%}")
    print(f"Results:     {output_path}")


if __name__ == "__main__":
    main()
