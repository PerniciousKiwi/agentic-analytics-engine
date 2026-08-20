from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "olist"


# -----------------------------------------------------------------------------
# CSV configuration
# -----------------------------------------------------------------------------


CSV_CONFIG = {
    "customers": {
        "file": "olist_customers_dataset.csv",
        "dtype": {
            "customer_id": "string",
            "customer_unique_id": "string",
            "customer_zip_code_prefix": "string",
            "customer_city": "string",
            "customer_state": "string",
        },
    },
    "orders": {
        "file": "olist_orders_dataset.csv",
        "dtype": {
            "order_id": "string",
            "customer_id": "string",
            "order_status": "string",
        },
        "parse_dates": [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    },
    "order_items": {
        "file": "olist_order_items_dataset.csv",
        "dtype": {
            "order_id": "string",
            "order_item_id": "Int64",
            "product_id": "string",
            "seller_id": "string",
            "price": "Float64",
            "freight_value": "Float64",
        },
        "parse_dates": ["shipping_limit_date"],
    },
    "order_payments": {
        "file": "olist_order_payments_dataset.csv",
        "dtype": {
            "order_id": "string",
            "payment_sequential": "Int64",
            "payment_type": "string",
            "payment_installments": "Int64",
            "payment_value": "Float64",
        },
    },
    "order_reviews": {
        "file": "olist_order_reviews_dataset.csv",
        "dtype": {
            "review_id": "string",
            "order_id": "string",
            "review_score": "Int64",
            "review_comment_title": "string",
            "review_comment_message": "string",
        },
        "parse_dates": [
            "review_creation_date",
            "review_answer_timestamp",
        ],
    },
    "products": {
        "file": "olist_products_dataset.csv",
        "dtype": {
            "product_id": "string",
            "product_category_name": "string",
            "product_name_lenght": "Int64",
            "product_description_lenght": "Int64",
            "product_photos_qty": "Int64",
            "product_weight_g": "Int64",
            "product_length_cm": "Int64",
            "product_height_cm": "Int64",
            "product_width_cm": "Int64",
        },
    },
    "sellers": {
        "file": "olist_sellers_dataset.csv",
        "dtype": {
            "seller_id": "string",
            "seller_zip_code_prefix": "string",
            "seller_city": "string",
            "seller_state": "string",
        },
    },
    "geolocation": {
        "file": "olist_geolocation_dataset.csv",
        "dtype": {
            "geolocation_zip_code_prefix": "string",
            "geolocation_lat": "Float64",
            "geolocation_lng": "Float64",
            "geolocation_city": "string",
            "geolocation_state": "string",
        },
    },
    "product_category_translation": {
        "file": "product_category_name_translation.csv",
        "dtype": {
            "product_category_name": "string",
            "product_category_name_english": "string",
        },
    },
}

# -----------------------------------------------------------------------------
# Environment
# -----------------------------------------------------------------------------

load_dotenv(PROJECT_ROOT / ".env")


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Database configuration
# -----------------------------------------------------------------------------

POSTGRES_HOST = os.environ["POSTGRES_HOST"]
POSTGRES_PORT = os.environ["POSTGRES_PORT"]
POSTGRES_DB = os.environ["POSTGRES_DB"]
POSTGRES_USER = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]


DATABASE_URL = (
    f"postgresql+psycopg://"
    f"{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)


def get_engine():
    """Create and return the PostgreSQL SQLAlchemy engine."""
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def create_raw_schema(engine) -> None:
    """Create the raw schema if it does not already exist."""
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))

    logger.info("Raw schema is ready")


def create_raw_tables(engine) -> None:
    """Create the nine raw Olist tables."""
    tables = {
        "customers": """
            CREATE TABLE IF NOT EXISTS raw.customers (
                customer_id TEXT,
                customer_unique_id TEXT,
                customer_zip_code_prefix TEXT,
                customer_city TEXT,
                customer_state TEXT
            )
        """,
        "orders": """
            CREATE TABLE IF NOT EXISTS raw.orders (
                order_id TEXT,
                customer_id TEXT,
                order_status TEXT,
                order_purchase_timestamp TIMESTAMP,
                order_approved_at TIMESTAMP,
                order_delivered_carrier_date TIMESTAMP,
                order_delivered_customer_date TIMESTAMP,
                order_estimated_delivery_date TIMESTAMP
            )
        """,
        "order_items": """
            CREATE TABLE IF NOT EXISTS raw.order_items (
                order_id TEXT,
                order_item_id INTEGER,
                product_id TEXT,
                seller_id TEXT,
                shipping_limit_date TIMESTAMP,
                price NUMERIC,
                freight_value NUMERIC
            )
        """,
        "order_payments": """
            CREATE TABLE IF NOT EXISTS raw.order_payments (
                order_id TEXT,
                payment_sequential INTEGER,
                payment_type TEXT,
                payment_installments INTEGER,
                payment_value NUMERIC
            )
        """,
        "order_reviews": """
            CREATE TABLE IF NOT EXISTS raw.order_reviews (
                review_id TEXT,
                order_id TEXT,
                review_score INTEGER,
                review_comment_title TEXT,
                review_comment_message TEXT,
                review_creation_date TIMESTAMP,
                review_answer_timestamp TIMESTAMP
            )
        """,
        "products": """
            CREATE TABLE IF NOT EXISTS raw.products (
                product_id TEXT,
                product_category_name TEXT,
                product_name_lenght INTEGER,
                product_description_lenght INTEGER,
                product_photos_qty INTEGER,
                product_weight_g INTEGER,
                product_length_cm INTEGER,
                product_height_cm INTEGER,
                product_width_cm INTEGER
            )
        """,
        "sellers": """
            CREATE TABLE IF NOT EXISTS raw.sellers (
                seller_id TEXT,
                seller_zip_code_prefix TEXT,
                seller_city TEXT,
                seller_state TEXT
            )
        """,
        "geolocation": """
            CREATE TABLE IF NOT EXISTS raw.geolocation (
                geolocation_zip_code_prefix TEXT,
                geolocation_lat NUMERIC,
                geolocation_lng NUMERIC,
                geolocation_city TEXT,
                geolocation_state TEXT
            )
        """,
        "product_category_translation": """
            CREATE TABLE IF NOT EXISTS raw.product_category_translation (
                product_category_name TEXT,
                product_category_name_english TEXT
            )
        """,
    }

    with engine.begin() as connection:
        for table_name, ddl in tables.items():
            connection.execute(text(ddl))
            logger.info("Raw table ready: raw.%s", table_name)


def truncate_raw_tables(engine) -> None:
    """Remove existing raw data before a full reload."""
    table_names = list(CSV_CONFIG.keys())

    with engine.begin() as connection:
        for table_name in reversed(table_names):
            connection.execute(text(f"TRUNCATE TABLE raw.{table_name}"))
            logger.info("Truncated raw.%s", table_name)


def load_raw_table(engine, table_name: str, config: dict) -> None:
    """Load one Olist CSV into its corresponding raw table."""
    csv_path = DATA_DIR / config["file"]

    logger.info("Loading %s from %s", table_name, csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    read_csv_kwargs = {
        "dtype": config.get("dtype"),
    }

    if "parse_dates" in config:
        read_csv_kwargs["parse_dates"] = config["parse_dates"]

    data = __import__("pandas").read_csv(
        csv_path,
        **read_csv_kwargs,
    )

    logger.info(
        "Read %s rows from %s",
        len(data),
        config["file"],
    )

    data.to_sql(
        name=table_name,
        con=engine,
        schema="raw",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=5_000,
    )

    logger.info(
        "Loaded %s rows into raw.%s",
        len(data),
        table_name,
    )


if __name__ == "__main__":
    engine = get_engine()

    create_raw_schema(engine)
    create_raw_tables(engine)
    truncate_raw_tables(engine)

    for table_name, config in CSV_CONFIG.items():
        load_raw_table(engine, table_name, config)

    with engine.connect() as connection:
        result = connection.exec_driver_sql("SELECT current_database(), current_user").fetchone()

    logger.info("Database: %s", result[0])
    logger.info("User: %s", result[1])
    logger.info("Data directory: %s", DATA_DIR)
