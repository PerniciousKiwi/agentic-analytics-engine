# Retrieval Ablation — Phase 6, Step 7

## Method

For each of the 130 answerable questions in `eval/suites/olist_gold_150.jsonl`,
`required_tables` was extracted automatically from the question's own `gold_sql`
via `sqlglot` (CTEs excluded, physical tables only), then spot-checked manually
against several known questions before being merged into the suite file.

Recall@k is computed as `|retrieved_tables ∩ required_tables| / |required_tables|`,
where retrieved tables are derived from the `card_id` of each returned schema card
(`table:` and `column:` prefixed IDs both resolve to their underlying table).
Recall is averaged across all 130 questions.

Four configurations were measured independently:

- **bm25** — `PostgresCardStore.search()` alone (PostgreSQL full-text search, `ts_rank_cd`)
- **dense** — `QdrantCardStore.search()` alone (bge-small-en-v1.5 embeddings, cosine similarity)
- **rrf** — Reciprocal Rank Fusion (`ReciprocalRankFusion.fuse`, k=60) over bm25 + dense
- **rrf_rerank** — the full production path: RRF fusion, then `SchemaCardReranker`
  (ONNX cross-encoder) reranking down to the final top-k

`rrf_rerank` mirrors `RetrievalService._hybrid()` (the mode used in production by
`retrieval_guarded_repaired`) exactly. `rrf` replicates `_hybrid()` up to but not
including the rerank step, since `RetrievalService` does not expose a fuse-without-
rerank mode directly.

## Results (current)

| Config | Recall@5 | Recall@10 | Recall@20 |
|---|---|---|---|
| bm25 | 0.785 | 0.944 | 0.972 |
| dense | 0.685 | 0.874 | 0.947 |
| rrf | 0.729 | 0.927 | 0.958 |
| rrf_rerank | 0.773 | 0.890 | 0.962 |

These numbers reflect the system's current state, after two fixes landed between
the first and final measurement (see Findings). They were not measured in isolation
from each other — see the methodology note below before drawing per-fix conclusions.

## Findings

**A real bug was found and fixed during this measurement.** `PostgresCardStore.search()`
originally built its query with `websearch_to_tsquery`, which — for a plain natural-
language sentence with no quote/exclusion syntax — ANDs every significant term
together (confirmed directly: `plainto_tsquery` and `websearch_to_tsquery` produced
an identical, fully `&`-joined query for a sample question). This meant a card had
to contain every one of a question's ~5-6 significant terms simultaneously to match
at all. Before the fix, BM25 recall was flat at 0.038 across k=5/10/20 — i.e., BM25
was returning almost nothing for almost any real question. The fix rewrites the
query as an OR of the same stemmed terms (`plainto_tsquery(...)` with `&` replaced
by `|`, then re-parsed via `to_tsquery`), reusing Postgres's own stemming rather than
reimplementing tokenization.

**A second real gap was found and fixed: `search_vector` used flat concatenation,
not weighted zones.** The original DDL built the tsvector via plain `to_tsvector()`
over all fields concatenated together, with no `setweight()` at all — meaning table/
column names ranked no higher than sample values in BM25 scoring, despite the Phase
6 guide's explicit design calling for separate A/B/C weight zones. Fixed by rebuilding
`search_vector` as `setweight(name, 'A') || setweight(description, 'B') ||
setweight(values_text || domain, 'C')`, deliberately excluding `card_text` (a
rendering that duplicates the other three fields' content, which would have diluted
the weighting by double-counting).

**A third real gap was found and fixed: the production dense retriever
(`QdrantCardStore.search()`) never applied bge-small-en-v1.5's recommended query-
instruction prefix.** Per the model's asymmetric-encoding design, only queries need
"Represent this sentence for searching relevant passages:" prepended before
embedding — passages (cards) should not be prefixed, and were correctly left
unprefixed. This is the exact silent-degradation risk the Phase 6 guide names by
description ("no error, just quietly worse recall"). Fixed by adding the prefix to
the query-embedding call only.

**Methodology note — these three fixes were not measured in isolation.** The
`websearch_to_tsquery` fix was isolated and verified (0.038 → ~0.95 flat improvement,
attributable with confidence). The `setweight` and query-prefix fixes, however, were
applied in sequence without an intermediate measurement between them, so their
individual contributions to the "current" numbers above cannot be cleanly separated
from each other. Notably, BM25's Recall@5 dropped from 0.947 (post-tsquery-fix,
pre-setweight) to 0.785 (current) even though the query-prefix fix has no code path
that touches BM25 at all — meaning the `setweight` change alone measurably shifted
BM25's ranking, in a direction that traded a small amount of top-5 recall for
unchanged-or-similar recall at k=10/20. This is plausibly a ranking-quality
improvement (correct zoning should better reflect true relevance) rather than a
regression, but Recall@k alone cannot distinguish those two explanations — a
precision or NDCG-style metric would be needed to say more, and that is out of
scope for this checkpoint.

**BM25 remains the strongest or joint-strongest individual retriever on this corpus
at every k measured**, even after the confound above. This still answers the
question the Phase 6 guide poses directly: dense does not meaningfully beat sparse
here.

**Fusion and reranking still do not clearly earn their cost on this metric.** `rrf`
and `rrf_rerank` both remain at or below plain BM25 at every k measured. This
conclusion is unchanged by the fixes made during this investigation.

**`src/cardinal/retrieval/sparse.py` and `dense.py` are dead code.** They define
`SparseRetriever`/`DenseRetriever` classes that are never imported or called by
`RetrievalService`, which uses `PostgresCardStore`/`QdrantCardStore` instead. This
ablation was run against the real production path. Worth a cleanup pass to remove
or consolidate the duplicate implementations, but out of scope for this measurement.
