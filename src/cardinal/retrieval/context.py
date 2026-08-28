from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import yaml

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
        config_path: str = "configs/retrieval.yaml",
    ) -> None:
        config_path = Path(config_path)

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
        metrics: list[Metric],
        token_budget: int = 6000,
    ) -> RetrievalContext:
        """Assemble bounded schema and metric context.

        Table cards are structural anchors: when a column card is selected,
        its parent table card is preferred so that relationships and the
        complete table schema remain available to SQL generation.
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
        columns_by_table: dict[str, int] = {}

        def add_result(result: RetrievalResult) -> bool:
            if result.card_id in selected_ids:
                return True

            table_name = self._table_name(result)

            if table_name not in tables:
                if len(tables) >= self.max_tables:
                    return False

                tables.add(table_name)

            if result.card_type == "column":
                column_count = columns_by_table.get(table_name, 0)

                if column_count >= self.max_columns_per_table:
                    return False

                columns_by_table[table_name] = column_count + 1

            selected.append(result)
            selected_ids.add(result.card_id)
            return True

        for result in deduplicated:
            if result.card_type == "metric":
                continue

            if result.card_type == "column":
                table_name = self._table_name(result)
                table_card = table_cards.get(table_name)

                if table_card is not None:
                    add_result(table_card)

            add_result(result)

        schema = "\n\n".join(result.card_text for result in selected)

        metric_text = self._format_metrics(metrics)

        token_count = self._estimate_tokens(
            schema,
            metric_text,
        )

        while selected and token_count > token_budget:
            removed = selected.pop()
            selected_ids.discard(removed.card_id)

            schema = "\n\n".join(result.card_text for result in selected)

            token_count = self._estimate_tokens(
                schema,
                metric_text,
            )

        return RetrievalContext(
            schema=schema,
            metrics=metric_text,
            card_ids=tuple(result.card_id for result in selected),
            token_count=token_count,
        )

    @staticmethod
    def select_metrics(
        question: str,
        metrics: list[Metric],
    ) -> list[Metric]:
        """Select the most relevant metrics using deterministic semantic matching."""
        if not metrics:
            return []

        normalized_question = (
            question.lower()
            .replace("-", " ")
            .replace("_", " ")
            .replace("?", " ")
            .replace(",", " ")
            .replace(".", " ")
        )

        stop_words = {
            "what",
            "which",
            "that",
            "this",
            "were",
            "have",
            "been",
            "from",
            "with",
            "across",
            "total",
            "percentage",
            "percent",
            "orders",
            "order",
            "value",
            "number",
            "many",
            "does",
            "most",
            "least",
            "eligible",
            "the",
            "are",
            "is",
            "was",
            "for",
            "all",
            "how",
        }

        question_words = {
            word
            for word in normalized_question.split()
            if len(word) >= 3 and word not in stop_words
        }

        scored: list[tuple[float, Metric]] = []

        for metric in metrics:
            metric_name = metric.name.lower().replace("_", " ").replace("-", " ")

            metric_label = metric.label.lower().replace("_", " ").replace("-", " ")

            metric_definition = (
                metric.definition.lower()
                .replace("_", " ")
                .replace("-", " ")
                .replace(",", " ")
                .replace(".", " ")
            )

            score = 0.0

            # Exact multi-word metric names and labels are authoritative.
            # A single generic word such as "revenue" is only a weak signal.
            metric_name_words = metric_name.split()
            metric_label_words = metric_label.split()

            if len(metric_name_words) > 1 and metric_name in normalized_question:
                score += 10000

            if len(metric_label_words) > 1 and metric_label in normalized_question:
                score += 10000

            if len(metric_name_words) == 1 and metric_name in normalized_question:
                score += 100

            name_words = set(metric_name.split())
            label_words = set(metric_label.split())
            definition_words = {
                word
                for word in metric_definition.split()
                if len(word) >= 4 and word not in stop_words
            }

            score += len(question_words & name_words) * 100
            score += len(question_words & label_words) * 100

            # Definition similarity is the main signal when the question
            # describes the metric without using its formal name.
            definition_matches = question_words & definition_words

            if definition_matches:
                score += len(definition_matches) * 500

                question_coverage = len(definition_matches) / len(question_words)
                definition_coverage = len(definition_matches) / len(definition_words)

                score += question_coverage * 1500
                score += definition_coverage * 500

            # Compare the full natural-language question with the definition.
            # This distinguishes specific concepts from generic words such
            # as "revenue", "review", or "delivered".
            question_text = " ".join(
                word for word in normalized_question.split() if word not in stop_words
            )

            definition_text = " ".join(
                word for word in metric_definition.split() if word not in stop_words
            )

            if question_text and definition_text:
                similarity = SequenceMatcher(
                    None,
                    question_text,
                    definition_text,
                ).ratio()

                score += similarity * 3000

            # Reward exact multi-word concepts occurring in the definition.
            question_tokens = question_text.split()
            definition_token_text = " ".join(definition_text.split())

            for size in range(
                min(7, len(question_tokens)),
                1,
                -1,
            ):
                matched_phrase = False

                for start in range(len(question_tokens) - size + 1):
                    phrase = " ".join(
                        question_tokens[start : start + size],
                    )

                    if len(phrase) >= 4 and phrase in definition_token_text:
                        score += size * 2500
                        matched_phrase = True
                        break

                if matched_phrase:
                    break

            scored.append((score, metric))

        scored.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        best_score = scored[0][0]

        if best_score <= 0:
            return metrics

        return [metric for score, metric in scored if score == best_score]

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

        return result.card_id

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

    @staticmethod
    def _estimate_tokens(
        schema: str,
        metrics: str,
    ) -> int:
        """Conservatively estimate prompt tokens."""
        text = f"{schema}\n{metrics}".strip()

        if not text:
            return 0

        # Ollama uses the model's native tokenizer, which isn't directly
        # exposed here. chars/4 is a deliberately conservative approximation
        # for context-budget enforcement.
        return (len(text) + 3) // 4
