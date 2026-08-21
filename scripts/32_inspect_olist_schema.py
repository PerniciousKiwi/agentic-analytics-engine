import os

import psycopg


def main() -> None:
    connection = psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )

    with connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema IN ('staging', 'intermediate', 'marts')
                ORDER BY table_schema, table_name
                """
        )

        print("TABLES")
        print("=" * 50)

        for schema, table in cursor.fetchall():
            print(f"{schema}.{table}")

        print()
        print("MART COLUMNS")
        print("=" * 50)

        for schema, table in [
            ("marts", "fct_orders"),
            ("marts", "fct_order_items"),
            ("marts", "fct_payments"),
            ("marts", "fct_reviews"),
            ("marts", "dim_customer"),
            ("marts", "dim_date"),
            ("marts", "dim_geography"),
            ("marts", "dim_products"),
            ("marts", "dim_sellers"),
            ("marts", "agg_customer_lifetime"),
            ("marts", "agg_daily_revenue"),
            ("marts", "agg_seller_performance"),
        ]:
            print()
            print(f"{schema}.{table}")
            print("-" * 50)

            cursor.execute(
                """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                (schema, table),
            )

            for column_name, data_type in cursor.fetchall():
                print(f"  {column_name}: {data_type}")


if __name__ == "__main__":
    main()
