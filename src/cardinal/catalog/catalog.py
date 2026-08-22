from pathlib import Path

from cardinal.catalog.manifest import (
    Column,
    Manifest,
    load_glossary,
    load_metrics,
)
from cardinal.catalog.models import Glossary, Metric


class Catalog:
    def __init__(
        self,
        manifest: Manifest,
        metrics: list[Metric],
        glossary: Glossary,
    ) -> None:
        self.manifest = manifest
        self.metrics = metrics
        self.glossary = glossary

    def get_relation(self, name: str):
        return self.manifest.get_relation(name)

    def resolve_table(self, name: str):
        return self.manifest.get_relation(name)

    def resolve_column(self, table: str, column: str) -> Column | None:
        if "." in column:
            table, column = column.rsplit(".", 1)

        relation = self.get_relation(table)

        if relation is None:
            return None

        return relation.columns.get(column)

    @classmethod
    def load(
        cls,
        manifest_path: Path | str,
        metrics_path: Path | str,
        glossary_path: Path | str,
        catalog_path: Path | str | None = None,
    ) -> "Catalog":
        manifest_path = Path(manifest_path)
        metrics_path = Path(metrics_path)
        glossary_path = Path(glossary_path)

        manifest = Manifest.load(
            manifest_path,
            catalog_path=Path(catalog_path) if catalog_path else None,
        )
        metrics = load_metrics(metrics_path)
        glossary = load_glossary(glossary_path)

        pii_columns = {entry.lower() for entry in glossary.pii_columns}

        for relation in manifest.relations.values():
            for column in relation.columns.values():
                identifier = f"{relation.schema_name}.{relation.name}.{column.name}"
                column.is_pii = identifier.lower() in pii_columns

        return cls(
            manifest=manifest,
            metrics=metrics,
            glossary=glossary,
        )
