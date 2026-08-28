# Retrieval Ablation Results

## Evaluation setup

The retrieval evaluation uses the Olist gold suite:

- Suite: `eval/suites/olist_gold_150.jsonl`
- Total questions: 150
- Answerable questions: 130
- Unanswerable questions: 20
- Metric: table-level question recall
- Cutoffs: Recall@5, Recall@10, Recall@20

For an answerable question, a hit requires every table in
`required_tables` to appear among the retrieved table cards at the
specified cutoff.

The evaluation compares:

1. BM25 / PostgreSQL lexical retrieval
2. Dense retrieval using BGE embeddings
3. Reciprocal Rank Fusion (RRF) of lexical and dense retrieval
4. RRF followed by ONNX cross-encoder reranking

## Results

| Configuration | Recall@5 | Recall@10 | Recall@20 |
|---|---:|---:|---:|
| BM25 | 0.0378 | 0.0378 | 0.0378 |
| Dense | 0.4090 | 0.5019 | 0.6917 |
| RRF | 0.4468 | 0.5359 | 0.7064 |
| RRF + rerank | **0.5494** | **0.6968** | **0.7949** |

## Findings

### BM25

BM25 performs poorly on the schema retrieval workload, reaching only
3.78% question recall at all tested cutoffs.

This indicates that lexical matching alone is insufficient for the
natural-language schema questions in the evaluation suite.

### Dense retrieval

Dense retrieval substantially outperforms BM25:

- Recall@5: 40.90%
- Recall@10: 50.19%
- Recall@20: 69.17%

This demonstrates that semantic retrieval is important for matching
natural-language questions to schema cards.

### Reciprocal Rank Fusion

RRF improves over dense retrieval at every evaluated cutoff:

- Recall@5: +3.78 percentage points
- Recall@10: +3.40 percentage points
- Recall@20: +1.47 percentage points

The current configuration uses `fusion.k = 60`.

### Cross-encoder reranking

RRF followed by cross-encoder reranking provides the strongest results:

- Recall@5: 54.94%
- Recall@10: 69.68%
- Recall@20: 79.49%

Compared with RRF, reranking improves Recall@10 by 16.09 percentage
points and Recall@20 by 8.85 percentage points.

The reranker therefore provides a substantial improvement in ordering
the highest-value candidates.

## RRF k tuning

The following RRF constants were evaluated:

| RRF k | Recall@5 | Recall@10 | Recall@20 |
|---:|---:|---:|---:|
| 20 | 0.4468 | 0.5359 | 0.7064 |
| 40 | 0.4468 | 0.5359 | 0.7064 |
| 60 | 0.4468 | 0.5359 | 0.7064 |
| 80 | 0.4468 | 0.5359 | 0.7064 |
| 100 | 0.4468 | 0.5359 | 0.7064 |

No measurable recall difference was observed across the tested values.
The existing value of `60` is therefore retained.

## Decision

The retrieval pipeline uses:

```text
Dense retrieval
      +
BM25 retrieval
      ↓
Reciprocal Rank Fusion
      ↓
ONNX cross-encoder reranking
      ↓
Top-k schema cards
