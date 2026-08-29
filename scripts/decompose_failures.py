import json
from eval.systems.retrieval_guarded_repaired import RetrievalGuardedRepairedSystem

# Load the fresh harness results to know which questions are actually wrong.
import glob
result_files = sorted(glob.glob("results/olist_gold_150_retrieval_guarded_repaired_*.json"))
latest_result_file = result_files[-1]
print(f"Using results file: {latest_result_file}")

with open(latest_result_file, encoding="utf-8") as f:
    harness_data = json.load(f)
harness_results = {r["question"]: r for r in harness_data["results"]}

# Load the suite with required_tables annotations.
rows = []
with open("eval/suites/olist_gold_150.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

answerable = [r for r in rows if r.get("answerable") and r.get("required_tables")]

wrong_answerable = []
for row in answerable:
    hr = harness_results.get(row["question"])
    if hr is None:
        print(f"WARNING: no harness result found for: {row['question'][:60]}")
        continue
    if not hr["correct"]:
        wrong_answerable.append(row)

print(f"Answerable: {len(answerable)}, Wrong: {len(wrong_answerable)}")

system = RetrievalGuardedRepairedSystem()

decomposition = []
for i, row in enumerate(wrong_answerable):
    question = row["question"]
    required = set(row["required_tables"])

    try:
        system._generate_sql(question, {"source": "postgres"})
        context = system._last_context
        retrieved = system.context_assembler.tables_from_card_ids(context.card_ids) if context else set()
        retrieval_complete = required.issubset(retrieved)
        classification = "generation_error" if retrieval_complete else "retrieval_miss"
        missing = sorted(required - retrieved)
    except Exception as e:
        retrieved = set()
        retrieval_complete = False
        classification = "exception_during_retrieval"
        missing = sorted(required)

    decomposition.append({
        "question_id": row["question_id"],
        "question": question,
        "required_tables": sorted(required),
        "retrieved_tables": sorted(retrieved),
        "missing_tables": missing,
        "classification": classification,
    })

    if (i + 1) % 10 == 0:
        print(f"...{i+1}/{len(wrong_answerable)}")

with open("retrieval_decomposition_raw.json", "w", encoding="utf-8") as f:
    json.dump(decomposition, f, ensure_ascii=False, indent=2)

retrieval_misses = sum(1 for d in decomposition if d["classification"] == "retrieval_miss")
generation_errors = sum(1 for d in decomposition if d["classification"] == "generation_error")
exceptions = sum(1 for d in decomposition if d["classification"] == "exception_during_retrieval")

print(f"\nTotal wrong (answerable): {len(decomposition)}")
print(f"Retrieval misses: {retrieval_misses} ({100*retrieval_misses/len(decomposition):.1f}%)")
print(f"Generation errors: {generation_errors} ({100*generation_errors/len(decomposition):.1f}%)")
print(f"Exceptions: {exceptions} ({100*exceptions/len(decomposition):.1f}%)")
