from pydantic import BaseModel


class Metric(BaseModel):
    name: str
    label: str
    definition: str
    sql: str
    filters: list[str]
    grain: str
    caveats: str
    tables: list[str]


class GlossaryEntry(BaseModel):
    definition: str
    warehouse_columns: list[str]


class Glossary(BaseModel):
    version: int
    glossary: dict[str, GlossaryEntry]
    pii_columns: list[str]
