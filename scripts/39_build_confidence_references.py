from __future__ import annotations

import psycopg

from cardinal.confidence.reference import (
    write_row_count_reference,
    write_warehouse_bounds,
)
from cardinal.config import get_settings


def execute_postgres_sql(
    sql: str,
) -> list[tuple]:
    settings = get_settings()

    with (
        psycopg.connect(
            host=settings.warehouse_ro_host,
            port=settings.warehouse_ro_port,
            dbname=settings.warehouse_ro_db,
            user=settings.warehouse_ro_user,
            password=settings.warehouse_ro_password,
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(sql)
        return cursor.fetchall()


def main() -> None:
    bounds_path = write_warehouse_bounds()

    row_counts_path = write_row_count_reference(
        execute_postgres_sql,
    )

    print(
        f"Warehouse bounds: {bounds_path}"
    )
    print(
        f"Row-count reference: {row_counts_path}"
    )


if __name__ == "__main__":
    main()