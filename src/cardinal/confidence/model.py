from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_NAMES = [
    "agreement_rate",
    "empty_result",
    "negative_value",
    "high_null_rate",
    "excessive_row_count",
    "date_out_of_bounds",
    "warehouse_checks_applicable",
    "grounding_score",
    "top_rrf_score",
    "reranker_margin",
    "retrieval_signals_available",
    "repair_attempts",
    "guardrail_failures",
    "estimated_query_cost",
    "agent_steps",
    "execution_failed",
]


@dataclass(frozen=True)
class ConfidenceModel:
    pipeline: Pipeline

    def predict_proba(
        self,
        features: dict[str, Any],
    ) -> float:
        row = pd.DataFrame(
            [
                {
                    name: float(features[name])
                    for name in FEATURE_NAMES
                }
            ],
            columns=FEATURE_NAMES,
        )

        probabilities = self.pipeline.predict_proba(row)

        return float(probabilities[0, 1])


def build_confidence_pipeline() -> Pipeline:
    """Create the confidence classifier pipeline."""

    return Pipeline(
        steps=[
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=2000,
                    random_state=42,
                ),
            ),
        ]
    )