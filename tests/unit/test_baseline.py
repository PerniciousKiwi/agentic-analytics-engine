from __future__ import annotations

import sqlite3
from pathlib import Path

from eval.systems.baseline import load_sqlite_schema_dump


def test_load_sqlite_schema_dump(tmp_path: Path) -> None:
    database_path = tmp_path / "test.sqlite"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER
            )
            """
        )

    schema = load_sqlite_schema_dump(database_path)

    assert "CREATE TABLE customers" in schema
    assert "CREATE TABLE orders" in schema
    assert "customer_id INTEGER PRIMARY KEY" in schema
