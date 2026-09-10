from __future__ import annotations

from cardinal.catalog.catalog import Catalog


def build_semantic_context(catalog: Catalog) -> tuple[str, str]:
    """Build the always-included semantic context for ambiguity detection."""

    metric_blocks: list[str] = []

    for metric in catalog.metrics:
        metric_blocks.append(
            "\n".join(
                [
                    f"Metric: {metric.name}",
                    f"Label: {metric.label}",
                    f"Definition: {metric.definition}",
                    f"Grain: {metric.grain}",
                    f"Filters: {metric.filters}",
                    f"Caveats: {metric.caveats}",
                    f"Tables: {metric.tables}",
                ]
            )
        )

    glossary_blocks: list[str] = []

    for term, entry in catalog.glossary.glossary.items():
        glossary_blocks.append(
            "\n".join(
                [
                    f"Term: {term}",
                    f"Definition: {entry.definition}",
                    f"Warehouse columns: {entry.warehouse_columns}",
                ]
            )
        )

    metrics_context = "\n\n".join(metric_blocks)
    glossary_context = "\n\n".join(glossary_blocks)

    return metrics_context, glossary_context