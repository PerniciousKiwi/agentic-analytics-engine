from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from cardinal.catalog.catalog import Catalog
from cardinal.catalog.models import Metric
from cardinal.retrieval.models import RetrievalResult


@dataclass(frozen=True)
class RetrievalContext:
    """Assembled schema and metric context for SQL generation."""

    schema: str
    metrics: str
    card_ids: tuple[str, ...]
    token_count: int


class SchemaContextAssembler:
    """Build a bounded SQL-generation context from retrieved schema cards."""

    def __init__(
        self,
        catalog: Catalog | None = None,
        config_path: str = "configs/retrieval.yaml",
    ) -> None:
        config_path = Path(config_path)
        self.catalog = catalog

        with config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

        pruning = config.get("pruning", {})

        self.max_tables = int(pruning.get("max_tables", 8))
        self.max_columns_per_table = int(
            pruning.get("max_columns_per_table", 25),
        )
        self.always_include_metrics = bool(
            pruning.get("always_include_metrics", True),
        )

        if self.max_tables <= 0:
            raise ValueError("pruning.max_tables must be positive.")

        if self.max_columns_per_table <= 0:
            raise ValueError(
                "pruning.max_columns_per_table must be positive.",
            )

    def assemble(
        self,
        results: list[RetrievalResult],
        required_tables: list[str] | None = None,
        token_budget: int = 6000,
    ) -> RetrievalContext:
        """Assemble bounded schema and metric context.

        Retrieved results are deduplicated and reduced to a bounded set of
        authoritative table cards. The assembler does not select metrics;
        callers select canonical metrics separately and render them into the
        prompt.
        """
        if token_budget <= 0:
            raise ValueError("token_budget must be positive.")

        deduplicated = self._deduplicate(results)

        table_cards = {
            self._table_name(result): result
            for result in deduplicated
            if result.card_type == "table"
        }

        selected: list[RetrievalResult] = []
        selected_ids: set[str] = set()
        tables: set[str] = set()
        required_tables = required_tables or []

        def add_table(table_name: str) -> bool:
            """Add an authoritative table card within the table limit."""
            if table_name in tables:
                return True

            if len(tables) >= self.max_tables:
                return False

            table_card = self._authoritative_table(
                table_name,
                table_cards,
            )

            if table_card is None:
                return False

            if table_card.card_id in selected_ids:
                tables.add(table_name)
                return True

            selected.append(table_card)
            selected_ids.add(table_card.card_id)
            tables.add(table_name)
            return True

        # Canonical metric tables are authoritative and must always
        # be present when supplied by the caller.
        for table_name in required_tables or []:
            add_table(table_name)

        # First, include tables required by retrieved table cards.
        for result in deduplicated:
            if result.card_type != "table":
                continue

            add_table(self._table_name(result))

        # Then include tables referenced by retrieved columns.
        for result in deduplicated:
            if result.card_type != "column":
                continue

            add_table(self._table_name(result))

        # Finally include non-table cards that fit within the table set.
        for result in deduplicated:
            if result.card_type == "table":
                continue

            if result.card_type == "column":
                table_name = self._table_name(result)

                if table_name not in tables:
                    continue

            if result.card_id in selected_ids:
                continue

            selected.append(result)
            selected_ids.add(result.card_id)

        # Keep table cards authoritative and cap the number of columns
        # represented for each table.
        table_selected: list[RetrievalResult] = [
            result for result in selected if result.card_type == "table"
        ]

        column_selected: list[RetrievalResult] = [
            result for result in selected if result.card_type == "column"
        ]

        other_selected: list[RetrievalResult] = [
            result for result in selected if result.card_type not in {"table", "column"}
        ]

        columns_by_table: dict[str, list[RetrievalResult]] = {}

        for result in column_selected:
            table_name = self._table_name(result)
            columns_by_table.setdefault(table_name, []).append(result)

        bounded_columns: list[RetrievalResult] = []

        for _table_name, columns in columns_by_table.items():
            bounded_columns.extend(
                columns[: self.max_columns_per_table],
            )

        selected = table_selected + bounded_columns + other_selected

        # Render the authoritative table cards.
        schema_sections = [
            result.card_text for result in selected if result.card_type in {"table", "column"}
        ]

        schema = "\n\n".join(schema_sections)

        # Metrics are intentionally not selected here. The caller can render
        # canonical metrics separately through _format_metrics().
        metrics = ""

        # Enforce the context budget conservatively.
        while selected and self._estimate_tokens(schema, metrics) > token_budget:
            removed = selected.pop()

            if removed.card_type == "table":
                # Never remove an authoritative table if possible.
                selected.insert(0, removed)

                removable = next(
                    (index for index, item in enumerate(selected) if item.card_type != "table"),
                    None,
                )

                if removable is None:
                    break

                selected.pop(removable)

            schema = "\n\n".join(
                result.card_text for result in selected if result.card_type in {"table", "column"}
            )

        card_ids = tuple(result.card_id for result in selected)

        return RetrievalContext(
            schema=schema,
            metrics=metrics,
            card_ids=card_ids,
            token_count=self._estimate_tokens(schema, metrics),
        )

    @staticmethod
    def select_metrics(
        question: str,
        metrics: list[Metric],
    ) -> list[Metric]:
        """Select the most relevant canonical metric deterministically."""
        if not metrics:
            return []

        normalized = (
            question.lower()
            .replace("-", " ")
            .replace("_", " ")
            .replace("?", " ")
            .replace(",", " ")
            .replace(".", " ")
        )

        words = set(normalized.split())

        def contains_phrase(*phrases: str) -> bool:
            return any(phrase in normalized for phrase in phrases)

        def metric_score(metric: Metric) -> float:
            name = metric.name.lower().replace("_", " ")
            label = metric.label.lower().replace("_", " ")
            definition = (
                metric.definition.lower()
                .replace("_", " ")
                .replace("-", " ")
                .replace(",", " ")
                .replace(".", " ")
            )

            score = 0.0

            if name in normalized:
                score += 100.0

            if label in normalized:
                score += 100.0

            name_words = {word for word in name.split() if len(word) >= 3}
            label_words = {word for word in label.split() if len(word) >= 3}

            score += len(words & name_words) * 15.0
            score += len(words & label_words) * 10.0

            definition_words = {word for word in definition.split() if len(word) >= 4}

            score += len(words & definition_words) * 4.0

            question_tokens = normalized.split()

            for size, weight in (
                (4, 20.0),
                (3, 12.0),
                (2, 6.0),
            ):
                for index in range(len(question_tokens) - size + 1):
                    phrase = " ".join(
                        question_tokens[index : index + size],
                    )

                    if phrase in definition:
                        score += weight

            if metric.name == "delivered_order_rate" and contains_phrase(
                "delivered to the customer",
                "delivered to customer",
                "orders delivered",
                "order delivered",
                "have been delivered",
                "were delivered",
            ):
                score += 250.0

            if metric.name == "delivered_order_rate" and contains_phrase(
                "late",
                "delayed",
                "delivery delay",
                "after the estimated",
                "on time",
            ):
                score -= 180.0

            if metric.name == "late_delivery_rate" and contains_phrase(
                "late delivery",
                "late deliveries",
                "delivered late",
                "delivery delay",
                "delayed delivery",
                "after the estimated delivery",
            ):
                score += 250.0

            if metric.name == "late_delivery_rate" and contains_phrase(
                "delivered to the customer",
                "orders delivered",
                "have been delivered",
                "on time",
            ):
                score -= 180.0

            if metric.name == "on_time_delivery_rate" and contains_phrase(
                "on time",
                "on-time",
                "delivered on time",
                "within the estimated",
            ):
                score += 300.0

            if metric.name == "on_time_delivery_rate" and contains_phrase(
                "late",
                "delayed",
                "delivery delay",
            ):
                score -= 180.0

            if metric.name == "orders_with_reviews_rate" and contains_phrase(
                "at least one customer review",
                "at least one review",
                "orders with reviews",
                "orders have reviews",
                "order has a review",
            ):
                score += 250.0

            if metric.name == "avg_review_score" and contains_phrase(
                "average review score",
                "average review rating",
                "mean review score",
            ):
                score += 250.0

            if metric.name == "repeat_customer_rate" and contains_phrase(
                "more than one order",
                "multiple orders",
                "placed more than one order",
                "repeat customer",
                "repeat customers",
            ):
                score += 250.0

            if metric.name == "revenue_per_state" and contains_phrase(
                "average revenue per order",
                "revenue per order",
            ):
                score += 250.0

            if metric.name == "freight_ratio" and contains_phrase(
                "proportion of calculated order value",
                "proportion of order value",
                "freight",
            ):
                score += 250.0

            if metric.name in {
                "revenue",
                "total_revenue",
            }:
                if contains_phrase(
                    "total revenue",
                    "revenue generated",
                    "total sales",
                ):
                    score += 180.0

                if contains_phrase(
                    "average revenue",
                    "revenue per order",
                ):
                    score -= 180.0

            if metric.name in {
                "order_count",
                "total_orders",
            } and contains_phrase(
                "how many orders",
                "number of orders",
                "order count",
                "count of orders",
            ):
                score += 150.0

            if metric.name == "cancelled_order_rate" and contains_phrase(
                "percentage of orders were cancelled",
                "percentage of orders canceled",
                "cancelled orders",
                "canceled orders",
                "cancellation rate",
            ):
                score += 250.0

            if metric.name == "avg_delivery_days" and contains_phrase(
                "average delivery time",
                "average delivery days",
                "average number of days",
                "delivery time in days",
                "days to deliver",
                "average delivery",
            ):
                score += 250.0

            if metric.name == "delivered_order_rate" and contains_phrase(
                "average delivery time",
                "average delivery days",
                "delivery time in days",
                "average number of days",
                "days to deliver",
            ):
                score -= 180.0

            if "item" in words or "items" in words:
                if metric.name in {
                    "total_item_value",
                    "item_value",
                }:
                    score += 100.0

                if metric.name in {
                    "average_item_price",
                    "avg_item_price",
                } and contains_phrase(
                    "average item price",
                    "average price",
                ):
                    score += 180.0

            return score

        scored = [(metric_score(metric), metric) for metric in metrics]

        scored.sort(
            key=lambda item: (-item[0], item[1].name),
        )

        best_score, best_metric = scored[0]

        if best_score < 10.0:
            return []

        if best_score >= 200.0:
            return [best_metric]

        if len(scored) > 1:
            second_score = scored[1][0]

            if second_score > 0 and best_score < second_score * 1.25:
                return []

        return [best_metric]

    def _catalog_table_result(
        self,
        table_name: str,
    ) -> RetrievalResult | None:
        """Build an authoritative table result from the catalog."""
        if self.catalog is None:
            return None

        relation = self.catalog.get_relation(table_name)

        if relation is None:
            return None

        columns = "\n".join(
            f"{column.name}: {column.data_type or 'unknown'}"
            for column in relation.columns.values()
        )

        card_text = "\n".join(
            [
                f"TABLE: {relation.schema_name}.{relation.name}",
                "DOMAIN: unknown",
                "ROW COUNT: 0",
                "COLUMNS:",
                columns,
            ],
        )

        return RetrievalResult(
            card_id=f"table:{relation.schema_name}.{relation.name}",
            card_type="table",
            domain="unknown",
            card_name=relation.name,
            card_text=card_text,
            score=float("inf"),
            metadata={"source": "catalog"},
        )

    def _authoritative_table(
        self,
        table_name: str,
        table_cards: dict[str, RetrievalResult],
    ) -> RetrievalResult | None:
        """Return the retrieved table card or construct one from the catalog."""
        existing = table_cards.get(table_name)

        if existing is not None:
            return existing

        return self._catalog_table_result(table_name)

    @staticmethod
    def _deduplicate(
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """Preserve retrieval order while removing duplicate card IDs."""
        seen: set[str] = set()
        deduplicated: list[RetrievalResult] = []

        for result in results:
            if result.card_id in seen:
                continue

            seen.add(result.card_id)
            deduplicated.append(result)

        return deduplicated

    @staticmethod
    def _table_name(result: RetrievalResult) -> str:
        """Return the physical table represented by a schema card."""
        if result.card_type == "table":
            return result.card_id.removeprefix("table:")

        if result.card_type == "column":
            return result.card_id.removeprefix("column:").rsplit(
                ".",
                1,
            )[0]

        return result.card_id.removeprefix("table:")

    def _format_metrics(self, metrics: list[Metric]) -> str:
        """Format selected metrics as authoritative SQL definitions."""
        if not self.always_include_metrics or not metrics:
            return ""

        sections = []

        for metric in metrics:
            filters = (
                "\n".join(f"- {item}" for item in metric.filters) if metric.filters else "None"
            )

            sections.append(
                "\n".join(
                    [
                        "[CANONICAL METRIC]",
                        f"Name: {metric.name}",
                        f"Label: {metric.label}",
                        f"Definition: {metric.definition}",
                        f"Grain: {metric.grain}",
                        f"Tables: {', '.join(metric.tables)}",
                        "",
                        "CANONICAL CALCULATION:",
                        metric.sql,
                        "",
                        "CANONICAL FILTERS:",
                        filters,
                        "",
                        "MANDATORY:",
                        "Use the canonical calculation exactly.",
                        "Preserve the canonical filters exactly.",
                        "Do not substitute another column or calculation.",
                        "Do not multiply a rate by 100 unless the canonical "
                        "calculation explicitly does so.",
                        "Do not add NULL filters unless they are canonical or "
                        "explicitly requested by the user.",
                        "[/CANONICAL METRIC]",
                    ],
                ),
            )

        return "\n\n".join(sections)
    
    def tables_from_card_ids(self, card_ids: tuple[str, ...]) -> set[str]:
        """Return the physical table names represented in assembled card IDs."""
        tables: set[str] = set()

        for card_id in card_ids:
            if card_id.startswith("table:"):
                tables.add(card_id.removeprefix("table:"))
            elif card_id.startswith("column:"):
                tables.add(card_id.removeprefix("column:").rsplit(".", 1)[0])

        return tables

    def _format_glossary(self, question: str, tables: set[str]) -> str:
        """Format glossary entries relevant to the question and assembled tables."""
        if self.catalog is None or not tables:
            return ""

        normalized_question = question.lower()
        sections = []

        for term, entry in self.catalog.glossary.glossary.items():
            entry_tables = {
                column.rsplit(".", 1)[0] for column in entry.warehouse_columns
            }

            if not entry_tables & tables:
                continue

            term_phrase = term.replace("_", " ")

            if term_phrase not in normalized_question:
                continue

            sections.append(
                "\n".join(
                    [
                        "[GLOSSARY TERM]",
                        f"Term: {term}",
                        f"Definition: {entry.definition}",
                        "Authoritative columns: " + ", ".join(entry.warehouse_columns),
                        "[/GLOSSARY TERM]",
                    ],
                ),
            )

        return "\n\n".join(sections)

    def _format_table_notes(self, tables: set[str]) -> str:
        """Format structural usage notes for tables present in the assembled schema.

        Unlike glossary terms, these are not phrase-matched against the
        question: a table's structural quirks (e.g. slowly-changing
        dimension semantics) apply whenever the table is used, regardless
        of how the question is worded.
        """
        if self.catalog is None or not tables:
            return ""

        sections = []

        for table_name, note in self.catalog.glossary.table_notes.items():
            if table_name not in tables:
                continue

            sections.append(
                "\n".join(
                    [
                        "[TABLE USAGE NOTE]",
                        f"Table: {table_name}",
                        f"Note: {note}",
                        "[/TABLE USAGE NOTE]",
                    ],
                ),
            )

        return "\n\n".join(sections)

    @staticmethod
    def _estimate_tokens(
        schema: str,
        metrics: str,
    ) -> int:
        """Conservatively estimate prompt tokens."""
        text = f"{schema}\n{metrics}".strip()

        if not text:
            return 0

        return (len(text) + 3) // 4
