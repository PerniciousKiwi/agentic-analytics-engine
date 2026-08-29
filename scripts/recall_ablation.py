import json
from cardinal.retrieval.postgres import PostgresCardStore
from cardinal.retrieval.qdrant import QdrantCardStore
from cardinal.retrieval.fusion import ReciprocalRankFusion
from cardinal.retrieval.rerank import SchemaCardReranker
from cardinal.retrieval.models import RetrievalResult

def tables_from_card_id(card_id: str) -> set[str]:
    if card_id.startswith("table:"):
        return {card_id.removeprefix("table:")}
    if card_id.startswith("column:"):
        return {card_id.removeprefix("column:").rsplit(".", 1)[0]}
    return set()

def tables_from_results(results: list, k: int) -> set[str]:
    tables = set()
    for r in results[:k]:
        tables |= tables_from_card_id(r["card_id"] if isinstance(r, dict) else r.card_id)
    return tables

def recall(required: set[str], retrieved: set[str]) -> float:
    if not required:
        return 1.0
    return len(required & retrieved) / len(required)

lexical_store = PostgresCardStore()
dense_store = QdrantCardStore()
fusion = ReciprocalRankFusion(k=60)
reranker = SchemaCardReranker()

MAX_K = 20
CANDIDATE_LIMIT = max(MAX_K, reranker.input_top_k)

rows = []
with open("eval/suites/olist_gold_150.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

answerable = [r for r in rows if r.get("answerable") and r.get("required_tables")]
print(f"Evaluating {len(answerable)} answerable questions with required_tables")

configs = ["bm25", "dense", "rrf", "rrf_rerank"]
ks = [5, 10, 20]
totals = {cfg: {k: 0.0 for k in ks} for cfg in configs}

for i, row in enumerate(answerable):
    question = row["question"]
    required = set(row["required_tables"])

    lexical_raw = lexical_store.search(question, limit=CANDIDATE_LIMIT)
    dense_results = dense_store.search(question, limit=CANDIDATE_LIMIT)

    lexical_results = [RetrievalResult(
        card_id=r["card_id"], card_type=r["card_type"], domain=r["domain"],
        card_name=r["card_name"], card_text=r["card_text"], score=float(r["score"]),
        metadata=dict(r.get("metadata", {})),
    ) for r in lexical_raw]

    fused = fusion.fuse([lexical_results, dense_results], limit=reranker.input_top_k)
    reranked = reranker.rerank(question, fused, limit=MAX_K)

    for k in ks:
        totals["bm25"][k] += recall(required, tables_from_results(lexical_results, k))
        totals["dense"][k] += recall(required, tables_from_results(dense_results, k))
        totals["rrf"][k] += recall(required, tables_from_results(fused, k))
        totals["rrf_rerank"][k] += recall(required, tables_from_results(reranked, k))

    if (i + 1) % 20 == 0:
        print(f"...{i + 1}/{len(answerable)}")

n = len(answerable)
print("\n| Config | Recall@5 | Recall@10 | Recall@20 |")
print("|---|---|---|---|")
for cfg in configs:
    print(f"| {cfg} | {totals[cfg][5]/n:.3f} | {totals[cfg][10]/n:.3f} | {totals[cfg][20]/n:.3f} |")
