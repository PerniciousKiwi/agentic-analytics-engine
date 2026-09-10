from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from eval.metrics import aurc, risk_coverage
from sklearn.calibration import calibration_curve

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OOF_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_oof_predictions.jsonl"
)

CONFIDENCE_METRICS_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_metrics.json"
)

POLICY_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_policy.json"
)

SELECTED_POLICY_METRICS_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "selected_policy_metrics.json"
)

RISK_COVERAGE_METRICS_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "risk_coverage_metrics.json"
)

RESULTS_DIR = (
    PROJECT_ROOT
    / "docs"
    / "results"
)

RELIABILITY_PATH = (
    RESULTS_DIR
    / "reliability_diagram.png"
)

RISK_COVERAGE_PATH = (
    RESULTS_DIR
    / "risk_coverage.png"
)

REPORT_PATH = (
    RESULTS_DIR
    / "selective_prediction.md"
)


def load_json(
    path: Path,
) -> dict[str, Any]:
    return json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )


def load_jsonl(
    path: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            if line.strip():
                rows.append(
                    json.loads(line)
                )

    return rows


def build_reliability_diagram(
    confidences: np.ndarray,
    correct: np.ndarray,
) -> None:
    fraction_positive, mean_predicted = (
        calibration_curve(
            correct,
            confidences,
            n_bins=10,
            strategy="uniform",
        )
    )

    plt.figure()

    plt.plot(
        mean_predicted,
        fraction_positive,
        marker="o",
        label="Observed",
    )

    plt.plot(
        [0.0, 1.0],
        [0.0, 1.0],
        linestyle="--",
        label="Perfect calibration",
    )

    plt.xlabel("Mean predicted confidence")
    plt.ylabel("Observed correctness")
    plt.title("Confidence Reliability Diagram")
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.savefig(
        RELIABILITY_PATH,
        dpi=200,
    )

    plt.close()


def build_risk_coverage_plot(
    confidences: np.ndarray,
    correct: np.ndarray,
    threshold: float,
) -> float:
    coverage, risk = risk_coverage(
        confidences,
        correct,
    )

    score = aurc(
        coverage,
        risk,
    )

    order = np.argsort(
        -confidences
    )

    sorted_confidence = confidences[
        order
    ]

    answered_count = int(
        np.sum(
            sorted_confidence
            >= threshold
        )
    )

    if answered_count > 0:
        operating_index = (
            answered_count - 1
        )

        operating_coverage = coverage[
            operating_index
        ]

        operating_risk = risk[
            operating_index
        ]

    else:
        operating_coverage = 0.0
        operating_risk = 1.0

    baseline_risk = (
        1.0 - float(np.mean(correct))
    )

    plt.figure()

    plt.plot(
        coverage,
        risk,
        label="Selective predictor",
    )

    plt.axhline(
        baseline_risk,
        linestyle="--",
        label="Always-answer baseline",
    )

    plt.scatter(
        [operating_coverage],
        [operating_risk],
        label="Selected operating point",
        zorder=5,
    )

    plt.xlabel("Coverage")
    plt.ylabel("Risk")
    plt.title("Risk-Coverage Curve")
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.savefig(
        RISK_COVERAGE_PATH,
        dpi=200,
    )

    plt.close()

    return score


def write_report(
    *,
    confidence_metrics: dict[str, Any],
    policy: dict[str, Any],
    selected_metrics: dict[str, Any],
    risk_metrics: dict[str, Any],
    combined_aurc: float,
) -> None:
    combined = selected_metrics[
        "groups"
    ]["combined"]

    bird = selected_metrics[
        "groups"
    ]["bird_dev_200"]

    olist = selected_metrics[
        "groups"
    ]["olist_gold_150"]

    bird_aurc = risk_metrics[
        "bird_dev_200"
    ]["aurc"]

    olist_aurc = risk_metrics[
        "olist_gold_150"
    ]["aurc"]

    report = f"""# Selective Prediction

## Confidence Model

The confidence model uses a StandardScaler followed by logistic regression.

Training examples: {confidence_metrics["training_rows"]}

Out-of-fold metrics:

- Accuracy: {confidence_metrics["oof_accuracy"]:.4f}
- ROC-AUC: {confidence_metrics["oof_roc_auc"]:.4f}
- Log loss: {confidence_metrics["oof_log_loss"]:.4f}
- Brier score: {confidence_metrics["oof_brier_score"]:.4f}

All reported confidence-model evaluation metrics use out-of-fold predictions.

## Selected Policy

Target selective accuracy: {policy["target_accuracy"]:.2%}

Selected confidence threshold:

`tau = {policy["threshold"]:.6f}`

Combined operating point:

- Coverage: {combined["coverage"]:.2%}
- Selective accuracy: {combined["selective_accuracy"]:.2%}
- Abstention rate: {combined["abstention_rate"]:.2%}
- Always-answer accuracy: {combined["always_answer_accuracy"]:.2%}

## Suite Results

### BIRD-200

- Coverage: {bird["coverage"]:.2%}
- Selective accuracy: {bird["selective_accuracy"]:.2%}
- Always-answer accuracy: {bird["always_answer_accuracy"]:.2%}
- AURC: {bird_aurc:.4f}

### Olist

- Coverage: {olist["coverage"]:.2%}
- Selective accuracy: {olist["selective_accuracy"]:.2%}
- Always-answer accuracy: {olist["always_answer_accuracy"]:.2%}
- AURC: {olist_aurc:.4f}

### Combined

- Coverage: {combined["coverage"]:.2%}
- Selective accuracy: {combined["selective_accuracy"]:.2%}
- Always-answer accuracy: {combined["always_answer_accuracy"]:.2%}
- AURC: {combined_aurc:.4f}

## Headline

Cardinal answers {bird["coverage"]:.2%} of BIRD-200 at
{bird["selective_accuracy"]:.2%} selective accuracy
(AURC {bird_aurc:.4f}). The always-answer baseline achieves
{bird["always_answer_accuracy"]:.2%} accuracy at 100% coverage.

## Reliability

![Reliability diagram](reliability_diagram.png)

The reliability diagram compares predicted confidence with observed
correctness using out-of-fold predictions.

## Risk-Coverage

![Risk coverage](risk_coverage.png)

Lower AURC indicates that incorrect predictions are concentrated toward lower-confidence regions.

## Limitations

The confidence threshold was selected using the same out-of-fold
predictions used to report the risk-coverage curve. This introduces
mild threshold-selection bias because there is no independent
threshold-selection holdout.

BIRD does not use several warehouse-specific confidence signals that
are available for Olist, including warehouse bounds and
retrieval-derived signals from the Olist schema-card retrieval system.
These unavailable signals are represented explicitly rather than
fabricated.

The grounding score is a heuristic based on numbers and named entities
appearing in result rows. It should be treated as a proxy for answer
grounding rather than a full factual-verification system.

The selected global threshold performs very differently across suites.
In particular, BIRD coverage is extremely low, which indicates that
the current confidence model transfers poorly to BIRD compared with
Olist."""

    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )


def main() -> None:
    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = load_jsonl(
        OOF_PATH
    )

    confidences = np.asarray(
        [
            float(row["confidence"])
            for row in rows
        ],
        dtype=float,
    )

    correct = np.asarray(
        [
            int(row["correct"])
            for row in rows
        ],
        dtype=int,
    )

    confidence_metrics = load_json(
        CONFIDENCE_METRICS_PATH
    )

    policy = load_json(
        POLICY_PATH
    )

    selected_metrics = load_json(
        SELECTED_POLICY_METRICS_PATH
    )

    risk_metrics = load_json(
        RISK_COVERAGE_METRICS_PATH
    )

    build_reliability_diagram(
        confidences,
        correct,
    )

    combined_aurc = (
        build_risk_coverage_plot(
            confidences,
            correct,
            float(policy["threshold"]),
        )
    )

    write_report(
        confidence_metrics=confidence_metrics,
        policy=policy,
        selected_metrics=selected_metrics,
        risk_metrics=risk_metrics,
        combined_aurc=combined_aurc,
    )

    print(
        f"Reliability: {RELIABILITY_PATH}"
    )

    print(
        f"Risk coverage: {RISK_COVERAGE_PATH}"
    )

    print(
        f"Report: {REPORT_PATH}"
    )


if __name__ == "__main__":
    main()