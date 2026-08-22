from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import BaseModel

from cardinal.catalog.models import Glossary, Metric


class Column(BaseModel):
    name: str
    data_type: str | None = None
    is_pii: bool = False


class Relation(BaseModel):
    unique_id: str
    name: str
    schema_name: str
    database: str | None = None
    resource_type: str
    columns: dict[str, Column]


class Manifest(BaseModel):
    relations: dict[str, Relation]

    @classmethod
    def load(
        cls,
        path: Path,
        catalog_path: Path | None = None,
    ) -> Manifest:
        payload = json.loads(path.read_text(encoding="utf-8"))

        catalog_payload = {}
        if catalog_path is not None:
            catalog_payload = json.loads(
                catalog_path.read_text(encoding="utf-8"),
            )

        relations: dict[str, Relation] = {}

        for unique_id, node in payload.get("nodes", {}).items():
            if node.get("resource_type") != "model":
                continue

            catalog_node = catalog_payload.get("nodes", {}).get(
                unique_id,
                {},
            )
            catalog_columns = catalog_node.get("columns", {})

            columns = {
                name: Column(
                    name=name,
                    data_type=column.get("type"),
                )
                for name, column in catalog_columns.items()
            }

            if not columns:
                columns = {
                    name: Column(
                        name=name,
                        data_type=column.get("type"),
                    )
                    for name, column in node.get("columns", {}).items()
                }

            relation = Relation(
                unique_id=unique_id,
                name=node["name"],
                schema_name=node["schema"],
                database=node.get("database"),
                resource_type=node["resource_type"],
                columns=columns,
            )

            relations[unique_id] = relation

        return cls(relations=relations)

    def get_relation(self, name: str) -> Relation | None:
        name_lower = name.lower()

        for relation in self.relations.values():
            relation_name = relation.name.lower()
            qualified_name = f"{relation.schema_name}.{relation.name}".lower()

            if name_lower in {relation_name, qualified_name}:
                return relation

        return None


def load_metrics(path: Path) -> list[Metric]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    return [Metric.model_validate(metric) for metric in payload["metrics"]]


def load_glossary(path: Path) -> Glossary:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    return Glossary.model_validate(payload)
