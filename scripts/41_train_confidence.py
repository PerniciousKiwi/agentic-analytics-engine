from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
)

from cardinal.confidence.model import (
    FEATURE_NAMES,
    build_confidence_pipeline,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASET_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_dataset.jsonl"
)

MODEL_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_model.joblib"
)

METRICS_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_metrics.json"
)

OOF_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_oof_predictions.jsonl"
)


def load_training_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with DATASET_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            if not line.strip():
                continue

            row = json.loads(line)

            if row.get("training_eligible") != 1:
                continue

            if row.get("correct") not in (0, 1):
                continue

            rows.append(row)

    return rows


def build_matrix(
    rows: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    X = pd.DataFrame(
        [
            {
                name: float(row[name])
                for name in FEATURE_NAMES
            }
            for row in rows
        ],
        columns=FEATURE_NAMES,
    )

    y = np.asarray(
        [
            int(row["correct"])
            for row in rows
        ],
        dtype=int,
    )

    return X, y


def write_oof_predictions(
    rows: list[dict[str, Any]],
    probabilities: np.ndarray,
) -> None:
    OOF_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OOF_PATH.open(
        "w",
        encoding="utf-8",
    ) as handle:
        for row, probability in zip(
            rows,
            probabilities,
            strict=True,
        ):
            output = {
                "question_id": row["question_id"],
                "suite": row["suite"],
                "correct": int(row["correct"]),
                "confidence": float(probability),
            }

            handle.write(
                json.dumps(output) + "\n"
            )


def main() -> None:
    rows = load_training_rows()

    if not rows:
        raise RuntimeError(
            "No eligible confidence-training rows found."
        )

    x, y = build_matrix(rows)

    if len(np.unique(y)) < 2:
        raise RuntimeError(
            "Confidence dataset must contain both classes."
        )

    cross_validation = StratifiedKFold(
        n_splits=5,
        shuffle=True,
        random_state=42,
    )

    pipeline = build_confidence_pipeline()

    oof_probabilities = cross_val_predict(
        pipeline,
        x,
        y,
        cv=cross_validation,
        method="predict_proba",
    )[:, 1]

    oof_predictions = (
        oof_probabilities >= 0.5
    ).astype(int)

    metrics = {
        "training_rows": len(rows),
        "positive_rows": int(y.sum()),
        "negative_rows": int(
            len(y) - y.sum()
        ),
        "oof_accuracy": float(
            accuracy_score(
                y,
                oof_predictions,
            )
        ),
        "oof_roc_auc": float(
            roc_auc_score(
                y,
                oof_probabilities,
            )
        ),
        "oof_log_loss": float(
            log_loss(
                y,
                oof_probabilities,
            )
        ),
        "oof_brier_score": float(
            brier_score_loss(
                y,
                oof_probabilities,
            )
        ),
    }

    write_oof_predictions(
        rows,
        oof_probabilities,
    )

    final_pipeline = build_confidence_pipeline()

    final_pipeline.fit(
        x,
        y,
    )

    MODEL_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        final_pipeline,
        MODEL_PATH,
    )

    METRICS_PATH.write_text(
        json.dumps(
            metrics,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Training rows: {len(rows)}")
    print(
        "Positive / correct:",
        int(y.sum()),
    )
    print(
        "Negative / incorrect:",
        int(len(y) - y.sum()),
    )
    print()

    for name, value in metrics.items():
        if name.endswith("_rows"):
            continue

        print(
            f"{name}: {value:.4f}"
        )

    print()
    print(f"Model:   {MODEL_PATH}")
    print(f"Metrics: {METRICS_PATH}")
    print(f"OOF:     {OOF_PATH}")


if __name__ == "__main__":
    main()