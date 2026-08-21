from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"
REPORTS_DIR = PROJECT_ROOT / "docs" / "results"


def load_results(path: Path) -> dict[str, Any]:
    """Load a harness results JSON file."""
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError("Results file must contain a JSON object.")

    if "suite" not in payload:
        raise ValueError("Results file is missing 'suite'.")

    results = payload.get("results")

    if not isinstance(results, list):
        raise ValueError("Results file must contain a 'results' list.")

    return payload


def calculate_metrics(payload: dict[str, Any]) -> dict[str, float]:
    """Calculate the Phase 2 summary metrics."""
    results = payload["results"]

    if not results:
        raise ValueError("Cannot report an empty results set.")

    accuracy = mean(bool(result["correct"]) for result in results)

    latencies = [
        float(result["latency_ms"]) for result in results if result.get("latency_ms") is not None
    ]

    tokens_in = [
        float(result["tokens_in"]) for result in results if result.get("tokens_in") is not None
    ]

    tokens_out = [
        float(result["tokens_out"]) for result in results if result.get("tokens_out") is not None
    ]

    return {
        "question_count": float(len(results)),
        "accuracy": accuracy,
        "mean_latency_ms": mean(latencies) if latencies else 0.0,
        "mean_tokens_in": mean(tokens_in) if tokens_in else 0.0,
        "mean_tokens_out": mean(tokens_out) if tokens_out else 0.0,
    }


def build_report(payload: dict[str, Any]) -> str:
    """Build the Markdown evaluation report."""
    metrics = calculate_metrics(payload)

    suite = payload["suite"]
    generated_at = payload.get("generated_at", "unknown")

    return f"""# Evaluation Results — {suite}

Generated: {generated_at}

| Metric | Value |
|---|---:|
| Question count | {int(metrics["question_count"])} |
| Accuracy | {metrics["accuracy"]:.2%} |
| Mean latency (ms) | {metrics["mean_latency_ms"]:.2f} |
| Mean tokens in | {metrics["mean_tokens_in"]:.2f} |
| Mean tokens out | {metrics["mean_tokens_out"]:.2f} |

## Latency Distribution

The accompanying PNG contains a histogram of per-question latency.
"""


def write_report(
    payload: dict[str, Any],
    output_path: Path,
) -> Path:
    """Write the Markdown evaluation report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_report(payload),
        encoding="utf-8",
        newline="\n",
    )
    return output_path


def write_latency_plot(
    payload: dict[str, Any],
    output_path: Path,
) -> Path:
    """Write a histogram of per-question latency."""
    results = payload["results"]

    latencies = [
        float(result["latency_ms"]) for result in results if result.get("latency_ms") is not None
    ]

    if not latencies:
        raise ValueError("No latency measurements available for plotting.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots()
    axis.hist(latencies, bins=20)
    axis.set_title(f"Latency Distribution — {payload['suite']}")
    axis.set_xlabel("Latency (ms)")
    axis.set_ylabel("Questions")
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)

    return output_path


def resolve_results_path(results_argument: str) -> Path:
    """Resolve either an explicit path or a results filename."""
    path = Path(results_argument)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        raise FileNotFoundError(f"Results file does not exist: {path}")

    return path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a Markdown report from Cardinal evaluation results."
    )
    parser.add_argument(
        "results",
        help="Path to a harness results JSON file.",
    )
    return parser.parse_args()


def main() -> None:
    """Generate Markdown and PNG evaluation artifacts."""
    args = parse_args()

    results_path = resolve_results_path(args.results)
    payload = load_results(results_path)

    suite = str(payload["suite"])

    markdown_path = REPORTS_DIR / f"{suite}.md"
    plot_path = REPORTS_DIR / f"{suite}.png"

    write_report(payload, markdown_path)
    write_latency_plot(payload, plot_path)

    print(f"Results:  {results_path}")
    print(f"Markdown: {markdown_path}")
    print(f"Plot:    {plot_path}")


if __name__ == "__main__":
    main()
