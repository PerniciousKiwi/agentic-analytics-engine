from pathlib import Path

from cardinal.catalog.builder import SchemaCardBuilder
from cardinal.catalog.catalog import Catalog
from cardinal.catalog.profiler import CardProfiler
from cardinal.db.reader import WarehouseReader
from cardinal.retrieval.postgres import PostgresCardStore
from cardinal.retrieval.qdrant import QdrantCardStore

ROOT = Path(__file__).resolve().parents[1]

MANIFEST_PATH = ROOT / "warehouse" / "target" / "manifest.json"
CATALOG_PATH = ROOT / "warehouse" / "target" / "catalog.json"
METRICS_PATH = ROOT / "warehouse" / "semantic" / "metrics.yml"
GLOSSARY_PATH = ROOT / "warehouse" / "semantic" / "glossary.yml"
SCHEMA_PATH = ROOT / "warehouse" / "models" / "schema.yml"


def main() -> None:
    catalog = Catalog.load(
        manifest_path=MANIFEST_PATH,
        metrics_path=METRICS_PATH,
        glossary_path=GLOSSARY_PATH,
        catalog_path=CATALOG_PATH,
    )

    # The read-only warehouse role has access to the analytics-facing
    # marts layer. Intermediate dbt models are implementation details
    # and are not part of the retrieval catalog.
    catalog.manifest.relations = {
        unique_id: relation
        for unique_id, relation in catalog.manifest.relations.items()
        if relation.schema_name == "marts"
    }

    builder = SchemaCardBuilder(
        catalog=catalog,
        schema_path=SCHEMA_PATH,
    )

    cards = builder.build_all()

    with WarehouseReader() as reader:
        profiler = CardProfiler(reader)

        profiled_cards = []

        for card in cards:
            if card.card_type == "table":
                card = profiler.profile_table(card)
            elif card.card_type == "column":
                card = profiler.profile_column(card)

            profiled_cards.append(card)

    store = PostgresCardStore()
    store.initialize()
    store.replace_all(profiled_cards)

    dense_store = QdrantCardStore()
    dense_store.replace_all(profiled_cards)

    print(f"Indexed {len(profiled_cards)} schema cards.")
    print(f"PostgreSQL catalog count: {store.count()}")


if __name__ == "__main__":
    main()
