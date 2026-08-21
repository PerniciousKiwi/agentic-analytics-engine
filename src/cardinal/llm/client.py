from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    stop_any,
    wait_random_exponential,
)

from cardinal.logging import get_logger


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response from an LLM completion."""

    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    model: str


class _RetryableServerError(Exception):
    """HTTP 5xx response that is safe to retry."""


class OllamaClient:
    """Async client for Ollama's OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
        http_client: httpx.AsyncClient,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.http_client = http_client
        self.logger = get_logger(__name__)

    async def complete(
        self,
        prompt: str,
        **overrides: Any,
    ) -> LLMResponse:
        """Generate a completion from Ollama."""
        request_model = str(overrides.get("model", self.model))

        payload: dict[str, Any] = {
            "model": request_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": overrides.get("temperature", 0.0),
        }

        for key in ("max_tokens", "top_p", "seed"):
            if key in overrides:
                payload[key] = overrides[key]

        start = time.perf_counter()
        attempts = 0

        async def make_request() -> httpx.Response:
            nonlocal attempts
            attempts += 1

            try:
                response = await self.http_client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code >= 500:
                    raise _RetryableServerError(f"Ollama returned HTTP {response.status_code}.")

                if 400 <= response.status_code < 500:
                    response.raise_for_status()

                return response

            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.NetworkError,
            ) as exc:
                self.logger.warning(
                    "ollama_request_retry",
                    model=request_model,
                    attempt=attempts,
                    error_type=type(exc).__name__,
                )
                raise

        decorated_request = retry(
            stop=stop_any(
                stop_after_attempt(3),
                stop_after_delay(120),
            ),
            wait=wait_random_exponential(
                multiplier=1,
                max=10,
            ),
            retry=retry_if_exception_type(
                (
                    httpx.TimeoutException,
                    httpx.ConnectError,
                    httpx.NetworkError,
                    _RetryableServerError,
                )
            ),
            reraise=True,
        )(make_request)
        response = await decorated_request()

        latency_ms = (time.perf_counter() - start) * 1000

        data = response.json()

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Ollama response contains no choices.")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("Ollama response contains no message.")

        text = message.get("content")
        if not isinstance(text, str):
            raise ValueError("Ollama response contains no text content.")

        usage = data.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}

        tokens_in = int(usage.get("prompt_tokens", 0))
        tokens_out = int(usage.get("completion_tokens", 0))

        self.logger.info(
            "ollama_completion",
            model=request_model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=round(latency_ms, 2),
            retried=attempts > 1,
            attempts=attempts,
        )

        self.logger.debug(
            "ollama_completion_payload",
            model=request_model,
            prompt=prompt,
            response=text,
        )

        return LLMResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            model=request_model,
        )
