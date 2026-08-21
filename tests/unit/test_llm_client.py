from __future__ import annotations

import httpx
import pytest

from cardinal.llm.client import OllamaClient


def make_client(
    handler,
) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)

    return OllamaClient(
        base_url="http://localhost:11434",
        model="qwen2.5-coder:7b-instruct-q4_K_M",
        timeout=1.0,
        http_client=http_client,
    )


@pytest.mark.asyncio
async def test_successful_response_parses_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == ("http://localhost:11434/v1/chat/completions")

        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "SELECT 1;"}}],
                "usage": {
                    "prompt_tokens": 42,
                    "completion_tokens": 8,
                },
            },
        )

    client = make_client(handler)

    try:
        result = await client.complete("How many orders are there?")

        assert result.text == "SELECT 1;"
        assert result.tokens_in == 42
        assert result.tokens_out == 8
        assert result.model == "qwen2.5-coder:7b-instruct-q4_K_M"
        assert result.latency_ms >= 0
    finally:
        await client.http_client.aclose()


@pytest.mark.asyncio
async def test_server_error_retries_and_succeeds_on_second_attempt() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            return httpx.Response(500)

        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "SELECT 2;"}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                },
            },
        )

    client = make_client(handler)

    try:
        result = await client.complete("test")

        assert result.text == "SELECT 2;"
        assert attempts == 2
    finally:
        await client.http_client.aclose()


@pytest.mark.asyncio
async def test_client_error_does_not_retry() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        return httpx.Response(
            400,
            json={"error": "bad request"},
        )

    client = make_client(handler)

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.complete("test")

        assert attempts == 1
    finally:
        await client.http_client.aclose()


@pytest.mark.asyncio
async def test_timeout_retries_and_eventually_raises() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("simulated timeout", request=request)

    client = make_client(handler)

    try:
        with pytest.raises(httpx.ReadTimeout):
            await client.complete("test")

        assert attempts == 3
    finally:
        await client.http_client.aclose()
