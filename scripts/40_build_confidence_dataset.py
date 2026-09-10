from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import psycopg
from eval.execution_accuracy import rows_equal
from eval.harness import (
    load_config,
    load_suite,
    resolve_database_path,
    resolve_suite_path,
)
from eval.systems.retrieval_guarded_repaired import (
    RetrievalGuardedRepairedSystem,
)

from cardinal.confidence.grounding import grounding_score
from cardinal.confidence.signals import (
    build_failure_feature_vector,
    build_feature_vector,
    load_row_count_reference,
    load_warehouse_bounds,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_dataset.jsonl"
)


def load_completed_ids() -> set[str]:
    if not OUTPUT_PATH.exists():
        return set()

    completed: set[str] = set()

    with OUTPUT_PATH.open(
        encoding="utf-8",
    ) as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            question_id = row.get(
                "question_id"
            )

            if isinstance(question_id, str):
                completed.add(question_id)

    return completed


def append_row(
    row: dict[str, Any],
) -> None:
    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
            json.dumps(
                row,
                ensure_ascii=False,
                default=str,
            )
        )
        file.write("\n")


def metric_non_negative_fields(
    metadata: dict[str, Any],
) -> set[str]:
    fields: set[str] = set()

    for metric in metadata.get(
        "selected_metrics",
        [],
    ):
        if not getattr(
            metric,
            "non_negative",
            False,
        ):
            continue

        fields.add(
            str(metric.name)
        )

    return fields


def execute_prediction(
    sql: str,
    *,
    suite_name: str,
    record: dict[str, Any],
    config: dict[str, Any],
) -> tuple[list[str], list[tuple[Any, ...]]]:
    if suite_name == "bird_dev_200":
        database_path = resolve_database_path(
            record,
            config,
        )

        with sqlite3.connect(database_path) as connection:
            cursor = connection.execute(sql)

            columns = [
                description[0]
                for description in cursor.description or []
            ]

            rows = cursor.fetchall()

        return columns, rows

    if suite_name == "olist_gold_150":
        import os

        import psycopg

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

            columns = [
                description.name
                for description in cursor.description or []
            ]

            rows = cursor.fetchall()

        return columns, rows

    raise ValueError(
        f"Unsupported suite: {suite_name}"
    )


def build_db_context(
    *,
    suite_name: str,
    record: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    gold_sql = record.get(
        "gold_sql"
    )

    if suite_name == "bird_dev_200":
        database_path = resolve_database_path(
            record,
            config,
        )

        return {
            "source": "sqlite",
            "db_id": record.get("db_id"),
            "database_path": database_path,
            "gold_sql": gold_sql,
        }

    if suite_name == "olist_gold_150":
        return {
            "source": "postgres",
            "db_id": None,
            "database_path": None,
            "gold_sql": gold_sql,
        }

    raise ValueError(
        f"Unsupported suite: {suite_name}"
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Cardinal confidence dataset."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N new questions per suite.",
    )

    return parser.parse_args()

def process_question(
    *,
    system: RetrievalGuardedRepairedSystem,
    suite_name: str,
    record: dict[str, Any],
    config: dict[str, Any],
    warehouse_bounds: dict[str, Any],
    row_count_reference: dict[str, float],
) -> dict[str, Any]:
    question_id = str(
        record["question_id"]
    )
    question = str(
        record["question"]
    )

    answerable = record.get(
        "answerable",
        True,
    )

    base_row: dict[str, Any] = {
        "question_id": question_id,
        "suite": suite_name,
        "question": question,
        "category": record.get(
            "category"
        ),
        "difficulty": record.get(
            "difficulty"
        ),
        "answerable": answerable,
    }

    if answerable is False:
        features = build_failure_feature_vector().to_dict()

        features["execution_failed"] = 0

        return {
            **base_row,
            **features,
            "correct": None,
            "abstained": None,
            "predicted_sql": None,
            "synthesized_answer": None, 
            "training_eligible": 0,
            "exclusion_reason": (
                "Unanswerable example reserved for Phase 9 "
                "ambiguity/answerability evaluation."
            ),
        }

    db_context = build_db_context(
        suite_name=suite_name,
        record=record,
        config=config,
    )

    try:
        predicted_sql, metadata = (
            system.answer(
                question,
                db_context,
            )
        )

        if not predicted_sql:
            raise ValueError(
                "System returned no SQL."
            )

        predicted_columns, predicted_rows = execute_prediction(
            predicted_sql,
            suite_name=suite_name,
            record=record,
            config=config,
        )

        gold_sql = str(
            record["gold_sql"]
        )

        _, gold_rows = execute_prediction(
            gold_sql,
            suite_name=suite_name,
            record=record,
            config=config,
        )

        correct = int(
            rows_equal(
                gold_rows,
                predicted_rows,
                float_tol=float(
                    config[
                        "float_tolerance"
                    ]
                ),
            )
        )

        answer_text = (
            system.loop.run_until_complete(
                system.answer_synthesizer.synthesize(
                    question,
                    predicted_rows,
                )
            )
            if hasattr(
                system,
                "answer_synthesizer",
            )
            else ""
        )

        grounded = (
            grounding_score(
                answer_text,
                predicted_rows,
            )
            if answer_text
            else 0.0
        )

        features = build_feature_vector(
            agreement=float(
                metadata.get(
                    "agreement_rate",
                    0.0,
                )
            ),
            columns=predicted_columns,
            rows=predicted_rows,
            category=record.get(
                "category"
            ),
            source=str(
                db_context["source"]
            ),
            grounding=grounded,
            top_rrf_score=metadata.get(
                "top_rrf_score"
            ),
            reranker_margin=metadata.get(
                "reranker_margin"
            ),
            repair_attempts=int(
                metadata.get(
                    "repair_attempts",
                    0,
                )
            ),
            guardrail_failures=int(
                metadata.get(
                    "guardrail_failures",
                    0,
                )
            ),
            estimated_query_cost=metadata.get(
                "estimated_query_cost"
            ),
            agent_steps=0,
            non_negative_fields=(
                metric_non_negative_fields(
                    metadata
                )
            ),
            row_count_references=(
                row_count_reference
            ),
            warehouse_bounds=(
                warehouse_bounds
            ),
            execution_failed=False,
        )

        return {
            **base_row,
            **features.to_dict(),
            "correct": correct,
            "abstained": 0,
            "predicted_sql": predicted_sql,
            "synthesized_answer": answer_text,
            "training_eligible": 1,
        }

    except (
        sqlite3.Error,
        psycopg.Error,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
    ) as exc:
        features = (
            build_failure_feature_vector()
        )

        return {
            **base_row,
            **features.to_dict(),
            "correct": 0,
            "abstained": 0,
            "predicted_sql": None,
            "synthesized_answer": None,
            "training_eligible": 1,
            "error": str(exc),
        }


def main() -> None:
    config = load_config()
    args = parse_args()

    warehouse_bounds = (
        load_warehouse_bounds()
    )

    row_count_reference = (
        load_row_count_reference()
    )

    completed_ids = (
        load_completed_ids()
    )

    system = (
        RetrievalGuardedRepairedSystem()
    )

    suites = (
        "bird_dev_200",
        "olist_gold_150",
    )

    processed = 0
    skipped = 0

    try:
        for suite_name in suites:
            suite_path = resolve_suite_path(
                config,
                suite_name,
            )

            suite = load_suite(
                suite_path
            )

            if args.limit is not None:
                if args.limit <= 0:
                    raise ValueError(
                        "--limit must be greater than zero."
                    )

                suite = suite[: args.limit]

            for index, record in enumerate(
                suite,
                start=1,
            ):
                question_id = str(
                    record["question_id"]
                )

                if question_id in completed_ids:
                    skipped += 1
                    continue

                row = process_question(
                    system=system,
                    suite_name=suite_name,
                    record=record,
                    config=config,
                    warehouse_bounds=warehouse_bounds,
                    row_count_reference=(
                        row_count_reference
                    ),
                )

                append_row(row)

                completed_ids.add(
                    question_id
                )

                processed += 1

                print(
                    f"[{suite_name}] "
                    f"{index}/{len(suite)} "
                    f"{question_id} "
                    f"correct={row['correct']} "
                    f"agreement="
                    f"{row['agreement_rate']:.2f}"
                )

    finally:
        system.close()

    print()
    print(
        f"Processed: {processed}"
    )
    print(
        f"Skipped:   {skipped}"
    )
    print(
        f"Output:    {OUTPUT_PATH}"
    )



if __name__ == "__main__":
    main()