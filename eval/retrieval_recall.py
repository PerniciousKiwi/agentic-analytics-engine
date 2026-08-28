from __future__ import annotations

import json
from pathlib import Path

from cardinal.retrieval.service import RetrievalService

SUITE_PATH = Path("eval/suites/olist_gold_150.jsonl")
RECALL_KS = (5, 10, 20)


def load_answerable_questions() -> list[dict]:
    """Load answerable questions from the retrieval evaluation suite."""
    rows = [
        json.loads(line)
        for line in SUITE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    return [row for row in rows if row.get("answerable", False)]


def retrieved_tables(results) -> set[str]:
    """Return physical tables represented by retrieved schema cards."""
    tables: set[str] = set()

    for result in results:
        if result.card_id.startswith("table:"):
            tables.add(result.card_id.removeprefix("table:"))

        elif result.card_id.startswith("column:"):
            tables.add(
                result.card_id.removeprefix("column:").rsplit(".", 1)[0],
            )

    return tables


def table_recall(
    required_tables: set[str],
    retrieved_tables_set: set[str],
) -> float:
    """Calculate standard table recall for one question."""
    if not required_tables:
        return 0.0

    return len(required_tables & retrieved_tables_set) / len(required_tables)


def mean_recall(
    rows: list[dict],
    rankings: dict[str, list],
    k: int,
) -> float:
    """Calculate mean table recall at one cutoff."""
    recalls: list[float] = []

    for row in rows:
        required = set(row["required_tables"])
        retrieved = retrieved_tables(
            rankings[row["question_id"]][:k],
        )

        recalls.append(
            table_recall(
                required,
                retrieved,
            )
        )

    return sum(recalls) / len(recalls) if recalls else 0.0


def build_rrf_rankings(
    service: RetrievalService,
    rows: list[dict],
) -> dict[str, list]:
    """Build RRF rankings once for every question."""
    rankings: dict[str, list] = {}

    candidate_limit = service.reranker.input_top_k

    for row in rows:
        lexical_results = service._lexical(
            row["question"],
            candidate_limit,
        )

        dense_results = service._dense(
            row["question"],
            candidate_limit,
        )

        rankings[row["question_id"]] = service.fusion.fuse(
            [lexical_results, dense_results],
            limit=candidate_limit,
        )

    return rankings


def build_reranked_rankings(
    service: RetrievalService,
    rows: list[dict],
    rrf_rankings: dict[str, list],
) -> dict[str, list]:
    """Rerank each RRF candidate pool exactly once."""
    rankings: dict[str, list] = {}

    for row in rows:
        rankings[row["question_id"]] = service.reranker.rerank(
            row["question"],
            rrf_rankings[row["question_id"]],
            limit=service.reranker.input_top_k,
        )

    return rankings


def main() -> None:
    rows = load_answerable_questions()

    if not rows:
        raise ValueError("No answerable questions found.")

    if any("required_tables" not in row for row in rows):
        raise ValueError("Every answerable question must contain required_tables.")

    service = RetrievalService()

    print(f"Evaluating {len(rows)} answerable questions.")
    print()

    print("Building BM25 rankings...")
    lexical_rankings = {
        row["question_id"]: service._lexical(
            row["question"],
            max(RECALL_KS),
        )
        for row in rows
    }

    print("Building dense rankings...")
    dense_rankings = {
        row["question_id"]: service._dense(
            row["question"],
            max(RECALL_KS),
        )
        for row in rows
    }

    print("Building RRF candidate rankings...")
    rrf_rankings = build_rrf_rankings(
        service,
        rows,
    )

    print("Reranking RRF candidates once...")
    reranked_rankings = build_reranked_rankings(
        service,
        rows,
        rrf_rankings,
    )

    results: dict[str, dict[int, float]] = {
        "BM25": {},
        "Dense": {},
        "RRF": {},
        "RRF + rerank": {},
    }

    for k in RECALL_KS:
        results["BM25"][k] = mean_recall(
            rows,
            lexical_rankings,
            k,
        )

        results["Dense"][k] = mean_recall(
            rows,
            dense_rankings,
            k,
        )

        results["RRF"][k] = mean_recall(
            rows,
            rrf_rankings,
            k,
        )

        results["RRF + rerank"][k] = mean_recall(
            rows,
            reranked_rankings,
            k,
        )

    print()
    print("| Configuration | Recall@5 | Recall@10 | Recall@20 |")
    print("|---|---:|---:|---:|")

    for configuration, scores in results.items():
        print(f"| {configuration} | {scores[5]:.4f} | {scores[10]:.4f} | {scores[20]:.4f} |")

    output_path = Path("results/retrieval_ablation_olist_150.json")
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = {
        "suite": str(SUITE_PATH),
        "answerable_questions": len(rows),
        "metric": ("Mean table recall: |retrieved_tables ∩ required_tables| / |required_tables|"),
        "cutoffs": list(RECALL_KS),
        "results": {
            configuration: {f"recall_at_{k}": score for k, score in scores.items()}
            for configuration, scores in results.items()
        },
    }

    output_path.write_text(
        json.dumps(
            output,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(f"Results written to: {output_path}")


if __name__ == "__main__":
    main()
