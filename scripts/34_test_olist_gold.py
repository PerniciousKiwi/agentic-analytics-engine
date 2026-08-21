from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = PROJECT_ROOT / "eval" / "suites" / "olist_gold_150.jsonl"


def main() -> None:
    """Execute answerable Olist gold SQL queries."""
    rows = [
        json.loads(line)
        for line in SUITE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    connection = psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )

    failures = []

    with connection, connection.cursor() as cursor:
        for row in rows:
            if not row["answerable"]:
                continue

            try:
                cursor.execute(row["gold_sql"])
                cursor.fetchall()
            except Exception as exc:
                failures.append(
                    {
                        "question_id": row["question_id"],
                        "error": str(exc),
                    }
                )

    print(f"Total questions: {len(rows)}")
    print(f"Executed successfully: {len(rows) - len(failures)}")
    print(f"Failed: {len(failures)}")

    if failures:
        print()
        for failure in failures:
            print(f"{failure['question_id']}: {failure['error']}")
        raise SystemExit(1)

    print()
    print("Olist gold SQL execution: PASS")


if __name__ == "__main__":
    main()
