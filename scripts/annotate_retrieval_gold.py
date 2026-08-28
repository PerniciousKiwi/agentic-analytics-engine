from __future__ import annotations

import json
from pathlib import Path

import sqlglot
from sqlglot import exp

INPUT_PATH = Path("eval/suites/olist_gold_150.jsonl")


def extract_required_tables(sql: str) -> list[str]:
    """Extract physical warehouse tables referenced by a SQL statement."""
    expression = sqlglot.parse_one(sql, dialect="postgres")

    cte_names = {cte.alias_or_name for cte in expression.find_all(exp.CTE)}

    tables = set()

    for table in expression.find_all(exp.Table):
        table_name = table.name

        if table_name in cte_names:
            continue

        if table.db:
            tables.add(f"{table.db}.{table_name}")
        else:
            tables.add(table_name)

    return sorted(tables)


def main() -> None:
    rows = [
        json.loads(line)
        for line in INPUT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    annotated = 0

    for row in rows:
        if not row.get("answerable", False):
            continue

        gold_sql = row.get("gold_sql")
        if not gold_sql:
            raise ValueError(f"{row['question_id']} is answerable but has no gold_sql.")

        row["required_tables"] = extract_required_tables(gold_sql)
        annotated += 1

    INPUT_PATH.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows)
        + "\n",
        encoding="utf-8",
    )

    print(f"Annotated {annotated} answerable questions.")
    print(f"Skipped {len(rows) - annotated} unanswerable questions.")


if __name__ == "__main__":
    main()
