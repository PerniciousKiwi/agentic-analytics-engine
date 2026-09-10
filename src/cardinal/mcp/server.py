from __future__ import annotations

import argparse
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings as FastMCPSettings

from cardinal.agent.schemas import (
    ExecuteSqlIn,
    ExecuteSqlOut,
    SearchSchemaIn,
    SearchSchemaOut,
)
from cardinal.agent.tools import execute_sql, search_schema

FastMCPSettings.model_rebuild()

mcp = FastMCP(
    "Cardinal Analytics",
    json_response=True,
)


@mcp.tool(name="search_schema")
def search_schema_tool(
    query: str,
    domain: str | None = None,
) -> SearchSchemaOut:
    """Search the warehouse schema using Cardinal's existing retrieval pipeline."""
    return search_schema(
        SearchSchemaIn(
            query=query,
            domain=domain,
        )
    )


@mcp.tool(name="execute_sql")
def execute_sql_tool(
    sql: str,
    row_limit: int = 1000,
) -> ExecuteSqlOut:
    """Execute guarded read-only SQL against the configured warehouse."""
    return execute_sql(
        ExecuteSqlIn(
            sql=sql,
            row_limit=row_limit,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Cardinal MCP server.",
    )

    parser.add_argument(
        "--transport",
        choices=[
            "stdio",
            "sse",
            "streamable-http",
        ],
        default="stdio",
    )

    args = parser.parse_args()

    transport: Literal[
        "stdio",
        "sse",
        "streamable-http",
    ] = args.transport

    mcp.run(
        transport=transport,
    )


if __name__ == "__main__":
    main()