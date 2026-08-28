from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CardType = Literal["table", "column", "metric"]


class ColumnSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    data_type: str | None = None
    description: str = ""
    is_pii: bool = False


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_table: str
    from_column: str
    to_table: str
    to_column: str


class SampleRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] = Field(default_factory=dict)


class SchemaCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str
    card_type: CardType
    domain: str
    card_name: str
    card_description: str
    card_values_text: str = ""

    def to_text(self) -> str:
        return f"{self.card_name}\nDOMAIN: {self.domain}\n{self.card_description}"


class TableCard(SchemaCard):
    card_type: Literal["table"] = "table"

    schema_name: str
    table_name: str
    grain: str | None = None
    row_count: int = Field(ge=0)
    columns: list[ColumnSummary] = Field(default_factory=list)
    sample_rows: list[SampleRow] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)

    def to_text(self) -> str:
        lines = [
            f"TABLE: {self.schema_name}.{self.table_name}",
            f"DOMAIN: {self.domain}",
            self.card_description,
        ]

        if self.grain is not None:
            lines.append(f"GRAIN: {self.grain}")

        lines.append(f"ROW COUNT: {self.row_count}")

        if self.columns:
            lines.append("COLUMNS:")
            lines.extend(
                f"{column.name}: {column.data_type or 'unknown'} — {column.description}"
                for column in self.columns
            )

        if self.relationships:
            lines.append("RELATIONSHIPS:")
            lines.extend(
                f"{relationship.from_table}.{relationship.from_column}"
                f" → {relationship.to_table}.{relationship.to_column}"
                for relationship in self.relationships
            )

        if self.metrics:
            lines.append("METRICS:")
            lines.append(", ".join(self.metrics))

        if self.sample_rows:
            lines.append("SAMPLE VALUES:")
            for sample_row in self.sample_rows:
                for name, value in sample_row.values.items():
                    lines.append(f"{name}: {value}")

        if self.card_values_text:
            lines.append(self.card_values_text)

        return "\n".join(lines)


class ColumnCard(SchemaCard):
    card_type: Literal["column"] = "column"

    schema_name: str
    table_name: str
    column_name: str
    data_type: str | None = None
    description: str = ""
    is_pii: bool = False
    null_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    distinct_count: int | None = Field(default=None, ge=0)
    top_values: list[Any] = Field(default_factory=list)
    min_value: Any | None = None
    max_value: Any | None = None

    def to_text(self) -> str:
        lines = [
            f"COLUMN: {self.schema_name}.{self.table_name}.{self.column_name}",
            f"DOMAIN: {self.domain}",
            self.card_description,
        ]

        if self.data_type is not None:
            lines.append(f"DATA TYPE: {self.data_type}")

        if self.null_rate is not None:
            lines.append(f"NULL RATE: {self.null_rate}")

        if self.distinct_count is not None:
            lines.append(f"DISTINCT COUNT: {self.distinct_count}")

        if self.top_values:
            lines.append("TOP VALUES:")
            lines.append(", ".join(str(value) for value in self.top_values))

        if self.min_value is not None:
            lines.append(f"MIN VALUE: {self.min_value}")

        if self.max_value is not None:
            lines.append(f"MAX VALUE: {self.max_value}")

        if self.is_pii:
            lines.append("PII: true")

        if self.card_values_text:
            lines.append(self.card_values_text)

        return "\n".join(lines)


class MetricCard(SchemaCard):
    card_type: Literal["metric"] = "metric"

    name: str
    label: str
    definition: str
    sql: str
    filters: list[str] = Field(default_factory=list)
    grain: str
    caveats: str
    tables: list[str] = Field(default_factory=list)

    def to_text(self) -> str:
        lines = [
            f"METRIC: {self.label}",
            f"DOMAIN: {self.domain}",
            self.card_description,
            f"DEFINITION: {self.definition}",
            f"CALCULATION: {self.sql}",
            f"GRAIN: {self.grain}",
        ]

        if self.filters:
            lines.append("FILTERS:")
            lines.extend(self.filters)

        if self.tables:
            lines.append("TABLES:")
            lines.append(", ".join(self.tables))

        if self.caveats:
            lines.append(f"CAVEATS: {self.caveats}")

        if self.card_values_text:
            lines.append(self.card_values_text)

        return "\n".join(lines)
