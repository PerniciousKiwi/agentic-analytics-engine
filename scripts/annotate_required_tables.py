import json
from pathlib import Path

import sqlglot
from sqlglot import exp


def extract_required_tables(sql: str) -> list[str]:
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return []

    cte_names = {cte.alias.lower() for cte in parsed.find_all(exp.CTE)}

    tables = set()
    for table in parsed.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names:
            continue
        schema = table.db.lower() if table.db else None
        qualified = f"{schema}.{name}" if schema else name
        tables.add(qualified)

    return sorted(tables)

rows = []
with Path("eval/suites/olist_gold_150.jsonl").open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

for row in rows:
    if "gold_sql" in row:
        row["required_tables"] = extract_required_tables(row["gold_sql"])
    else:
        row["required_tables"] = []

with Path(
    "eval/suites/olist_gold_150_annotated_review.jsonl"
).open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

answerable = [r for r in rows if r.get("answerable")]
no_tables = [r["question_id"] for r in answerable if not r["required_tables"]]
single_table = [r["question_id"] for r in answerable if len(r["required_tables"]) == 1]
multi_table = [r["question_id"] for r in answerable if len(r["required_tables"]) > 1]

print(f"Total rows: {len(rows)}")
print(f"Answerable rows: {len(answerable)}")
print(f"Answerable rows with ZERO required_tables (needs manual review): {len(no_tables)}")
print(no_tables)
print(f"Answerable rows with exactly 1 required table: {len(single_table)}")
print(f"Answerable rows with 2+ required tables: {len(multi_table)}")
