from __future__ import annotations

import json
import logging
import random
from collections import Counter
from pathlib import Path
from typing import Any, cast

import yaml
from datasets import load_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "eval.yaml"

REQUIRED_COLUMNS = {
    "question_id",
    "db_id",
    "question",
    "SQL",
    "difficulty",
}

EXPECTED_SPLIT = "dev_20251106"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def load_config() -> dict[str, Any]:
    """Load the Phase 2 evaluation configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise RuntimeError("eval.yaml must contain a YAML mapping.")

    return cast(dict[str, Any], config)


def validate_dataset(
    dataset: Any,
    bird_config: dict[str, Any],
) -> None:
    """Validate the downloaded BIRD dataset against eval.yaml."""
    actual_columns = set(dataset.column_names)

    missing_columns = REQUIRED_COLUMNS - actual_columns
    if missing_columns:
        raise RuntimeError(f"BIRD dataset is missing required columns: {sorted(missing_columns)}")

    expected_row_count = bird_config["source_row_count"]
    actual_row_count = len(dataset)

    if actual_row_count != expected_row_count:
        raise RuntimeError(
            f"Unexpected BIRD row count: expected {expected_row_count}, got {actual_row_count}"
        )

    expected_difficulty_counts = Counter(bird_config["source_difficulty_counts"])
    actual_difficulty_counts = Counter(dataset["difficulty"])

    if actual_difficulty_counts != expected_difficulty_counts:
        raise RuntimeError(
            "BIRD difficulty distribution does not match eval.yaml. "
            f"Expected {dict(expected_difficulty_counts)}, "
            f"got {dict(actual_difficulty_counts)}"
        )


def sample_stratified(
    dataset: Any,
    bird_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Sample the configured number of questions from each difficulty."""
    seed = bird_config["bird_seed"]
    targets = bird_config["bird_strata_targets"]

    selected_rows: list[dict[str, Any]] = []

    for stratum_index, (difficulty, target_count) in enumerate(targets.items()):
        group_indices = [
            index for index, row in enumerate(dataset) if row["difficulty"] == difficulty
        ]

        available_count = len(group_indices)

        if target_count > available_count:
            raise RuntimeError(
                f"Cannot sample {target_count} rows from difficulty "
                f"'{difficulty}'; only {available_count} are available."
            )

        # Deterministic, non-cryptographic sampling is intentional here.
        rng = random.Random(seed + stratum_index)  # noqa: S311

        sampled_indices = rng.sample(
            group_indices,
            target_count,
        )

        selected_rows.extend(
            {
                "question_id": dataset[index]["question_id"],
                "db_id": dataset[index]["db_id"],
                "question": dataset[index]["question"],
                "evidence": dataset[index]["evidence"],
                "gold_sql": dataset[index]["SQL"],
                "difficulty": dataset[index]["difficulty"],
            }
            for index in sampled_indices
        )

    expected_total = bird_config["bird_subset_size"]

    if len(selected_rows) != expected_total:
        raise RuntimeError(
            f"Expected {expected_total} selected questions, got {len(selected_rows)}."
        )

    question_ids = [row["question_id"] for row in selected_rows]

    if len(question_ids) != len(set(question_ids)):
        raise RuntimeError("Selected BIRD questions contain duplicate IDs.")

    return selected_rows


def write_jsonl(
    rows: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Write evaluation questions as JSON Lines."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    """Download, validate, sample, and write the BIRD evaluation suite."""
    config = load_config()
    bird_config = config["bird"]

    source = bird_config["source"]
    revision = bird_config["bird_commit_hash"]

    if not source.startswith("huggingface://"):
        raise RuntimeError("BIRD source must use the huggingface:// scheme.")

    dataset_name = source.removeprefix("huggingface://")

    logger.info("BIRD evaluation suite generation")
    logger.info("Source: %s", source)
    logger.info("Revision: %s", revision)
    logger.info(
        "Expected source rows: %s",
        bird_config["source_row_count"],
    )
    logger.info(
        "Target sample size: %s",
        bird_config["bird_subset_size"],
    )
    logger.info(
        "Random seed: %s",
        bird_config["bird_seed"],
    )

    dataset_dict = load_dataset(
        dataset_name,
        revision=revision,
    )

    if EXPECTED_SPLIT not in dataset_dict:
        raise RuntimeError(
            f"Expected split '{EXPECTED_SPLIT}' was not found. "
            f"Available splits: {list(dataset_dict.keys())}"
        )

    dataset = dataset_dict[EXPECTED_SPLIT]

    validate_dataset(dataset, bird_config)

    logger.info("Source validation: PASS")

    selected_rows = sample_stratified(
        dataset,
        bird_config,
    )

    selected_difficulties = Counter(row["difficulty"] for row in selected_rows)

    logger.info("Selected difficulty counts:")
    for difficulty in sorted(selected_difficulties):
        logger.info(
            "  %s: %s",
            difficulty,
            selected_difficulties[difficulty],
        )

    output_path = PROJECT_ROOT / bird_config["questions_path"]

    write_jsonl(
        selected_rows,
        output_path,
    )

    logger.info(
        "Selected questions: %s",
        len(selected_rows),
    )
    logger.info(
        "Output: %s",
        output_path,
    )
    logger.info("BIRD suite generation: COMPLETE")


if __name__ == "__main__":
    main()
