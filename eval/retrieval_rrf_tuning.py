from __future__ import annotations

import json
from pathlib import Path

from cardinal.retrieval.fusion import ReciprocalRankFusion
from cardinal.retrieval.service import RetrievalService

SUITE_PATH = Path("eval/suites/olist_gold_150.jsonl")
RECALL_KS = (5, 10, 20)
RRF_KS = (20, 40, 60, 80, 100)


def load_answerable_questions() -> list[dict]:
    """Load answerable questions from the evaluation suite."""
    rows = [
        json.loads(line)
        for line in SUITE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    return [row for row in rows if row.get("answerable", False)]


def retrieved_tables(results) -> set[str]:
    """Return physical table names represented by retrieved cards."""
    return {
        result.card_id.removeprefix("table:")
        for result in results
        if result.card_id.startswith("table:")
    }


def table_recall(
    required_tables: set[str],
    retrieved: set[str],
) -> float:
    """Calculate standard table recall for one question."""
    if not required_tables:
        return 0.0

    return len(required_tables & retrieved) / len(required_tables)


def main() -> None:
    rows = load_answerable_questions()

    if not rows:
        raise ValueError("No answerable questions found.")

    if any("required_tables" not in row for row in rows):
        raise ValueError(
            "Every answerable question must contain required_tables.",
        )

    service = RetrievalService()
    candidate_limit = service.reranker.input_top_k

    print(f"Evaluating {len(rows)} answerable questions.")
    print()

    print("Building retrieval candidates...")

    candidates: dict[str, tuple[list, list]] = {}

    for row in rows:
        question = row["question"]

        lexical = service._lexical(
            question,
            candidate_limit,
        )

        dense = service._dense(
            question,
            candidate_limit,
        )

        candidates[row["question_id"]] = (
            lexical,
            dense,
        )

    results: dict[int, dict[int, float]] = {}

    for rrf_k in RRF_KS:
        print(f"Evaluating RRF k={rrf_k}...")

        fusion = ReciprocalRankFusion(k=rrf_k)

        rankings = {
            question_id: fusion.fuse(
                [lexical, dense],
                limit=candidate_limit,
            )
            for question_id, (lexical, dense) in candidates.items()
        }

        results[rrf_k] = {}

        for recall_k in RECALL_KS:
            recalls: list[float] = []

            for row in rows:
                retrieved = retrieved_tables(
                    rankings[row["question_id"]][:recall_k],
                )

                required = set(row["required_tables"])

                recalls.append(
                    table_recall(
                        required,
                        retrieved,
                    )
                )

            results[rrf_k][recall_k] = sum(recalls) / len(recalls) if recalls else 0.0

        print(f"  Recall@5:  {results[rrf_k][5]:.4f}")
        print(f"  Recall@10: {results[rrf_k][10]:.4f}")
        print(f"  Recall@20: {results[rrf_k][20]:.4f}")
        print()

    print("| RRF k | Recall@5 | Recall@10 | Recall@20 |")
    print("|---:|---:|---:|---:|")

    for rrf_k in RRF_KS:
        print(
            f"| {rrf_k} | "
            f"{results[rrf_k][5]:.4f} | "
            f"{results[rrf_k][10]:.4f} | "
            f"{results[rrf_k][20]:.4f} |"
        )

    output_path = Path("results/retrieval_rrf_tuning_olist_150.json")
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = {
        "suite": str(SUITE_PATH),
        "answerable_questions": len(rows),
        "rrf_k_values": list(RRF_KS),
        "recall_cutoffs": list(RECALL_KS),
        "metric": ("Mean table recall: |retrieved_tables ∩ required_tables| / |required_tables|"),
        "results": {
            str(rrf_k): {f"recall_at_{recall_k}": score for recall_k, score in scores.items()}
            for rrf_k, scores in results.items()
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
