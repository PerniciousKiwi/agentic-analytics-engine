from __future__ import annotations

import json
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = PROJECT_ROOT / "eval" / "suites" / "bird_dev_200.jsonl"
DATABASE_ROOT = PROJECT_ROOT / "data" / "bird" / "dev_databases"


def load_suite() -> list[dict[str, object]]:
    with SUITE_PATH.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def execute_gold_sql(row: dict[str, object]) -> tuple[bool, str]:
    db_id = str(row["db_id"])
    gold_sql = str(row["gold_sql"])

    database_path = DATABASE_ROOT / db_id / f"{db_id}.sqlite"

    try:
        with sqlite3.connect(database_path) as connection:
            connection.execute(gold_sql).fetchall()

        return True, ""

    except sqlite3.Error as exc:
        return False, str(exc)


def main() -> None:
    rows = load_suite()

    successful = 0
    failed = 0

    failures: list[tuple[int, str, str]] = []

    for row in rows:
        question_id = int(row["question_id"])
        db_id = str(row["db_id"])

        success, error = execute_gold_sql(row)

        if success:
            successful += 1
        else:
            failed += 1
            failures.append((question_id, db_id, error))

    print(f"Total questions: {len(rows)}")
    print(f"Executed successfully: {successful}")
    print(f"Failed: {failed}")

    if failures:
        print()
        print("FAILURES:")
        for question_id, db_id, error in failures:
            print(f"question_id={question_id} db_id={db_id} error={error}")

        raise SystemExit(1)

    print()
    print("BIRD gold SQL execution: PASS")


if __name__ == "__main__":
    main()
