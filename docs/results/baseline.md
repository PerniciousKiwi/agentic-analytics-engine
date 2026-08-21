# Phase 3 Baseline

## Purpose

Phase 3 establishes the intentionally naive SQL-generation baseline for Cardinal.

The baseline provides the reference point for all later improvements. It uses:

- the full database schema as a raw DDL-like schema dump
- no retrieval
- no schema cards
- no embeddings
- no guardrails
- no SQL validation or repair
- no examples
- no metrics context
- deterministic temperature (`0.0`)
- Qwen 2.5 Coder 7B via Ollama

Prompt version:

`da6014499c58`

The prompt hash identifies the source version of
`src/cardinal/llm/prompts/generate_sql.j2`.

## Baseline Results

| Suite | Questions | Executed OK | Correct | Accuracy | Prompt hash |
|---|---:|---:|---:|---:|---|
| Olist Gold 150 | 150 | 130 (86.67%) | 38 | 29.23% | `da6014499c58` |
| BIRD Dev 200 | 200 | 170 (85.00%) | 58 | 29.00% | `da6014499c58` |

### Olist Gold 150

- Accuracy: **29.2%**
- Executed successfully: **130 / 150 (86.67%)**
- Correct: **38 / 130 graded questions**
- Mean latency: **5516.96 ms**
- Mean input tokens: **856.42**
- Mean output tokens: **52.27**
- Prompt hash: `da6014499c58`

The final 20 Olist records are deliberately unanswerable examples.
They were correctly marked as abstentions by the harness:

- 20 abstained
- 20 correct
- 0 executed

These records have no prompt hash because no LLM request was made.

### BIRD Dev 200

- Accuracy: **29.0%**
- Executed successfully: **170 / 200 (85.00%)**
- Correct: **58 / 200**
- Mean latency: **6948.26 ms**
- Mean input tokens: **864.62**
- Mean output tokens: **62.12**
- Prompt hash: `da6014499c58`

BIRD uses a separate SQLite database for each question's `db_id`.
The baseline resolves and caches the appropriate SQLite schema for each
evaluation database before generating SQL.

The BIRD baseline therefore measures the actual SQL-generation capability
of the naive full-schema approach rather than the earlier schema-contamination
bug.

## Generated Reports

The detailed per-suite reports are:

- `docs/results/olist_gold_150.md`
- `docs/results/olist_gold_150.png`
- `docs/results/bird_dev_200.md`
- `docs/results/bird_dev_200.png`

The raw evaluation results are:

- `results/olist_gold_150_20260821T150150Z.json`
- `results/bird_dev_200_20260821T170932Z.json`

## Baseline Interpretation

The baseline demonstrates the limitations of providing an LLM with the
complete database schema and asking it to generate SQL without retrieval,
validation, repair, or other deterministic guardrails.

The current measured reference results are:

- **Olist Gold 150: 29.2% accuracy**
- **BIRD Dev 200: 29.0% accuracy**

The earlier BIRD result of 0.00% was caused by schema contamination: the
Olist warehouse schema was being supplied to BIRD questions. That issue has
now been fixed by resolving the schema from the evaluation database supplied
through `db_context`.

Later phases must be evaluated against these current measured baseline
results rather than against assumed target values.
