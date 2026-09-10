from __future__ import annotations

import json
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_mcp_stdio_lists_and_calls_search_schema() -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "cardinal.mcp.server",
            "--transport",
            "stdio",
        ],
    )

    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        tools = await session.list_tools()

        names = {tool.name for tool in tools.tools}

        assert "search_schema" in names
        assert "execute_sql" in names

        result = await session.call_tool(
            "search_schema",
            {
                "query": "total revenue",
            },
        )

        assert result.isError is False
        assert result.content

        text_blocks = [
            block.text
            for block in result.content
            if hasattr(block, "text")
        ]

        assert text_blocks

        payload = json.loads(text_blocks[0])

        assert "cards" in payload
        assert "error" in payload
        assert payload["error"] is None
        assert payload["cards"]