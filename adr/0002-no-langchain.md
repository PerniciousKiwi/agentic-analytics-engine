# ADR 0002: Do Not Use LangChain for the SQL Generation Path

- **Status:** Accepted
- **Date:** 2026-08-21
- **Decision:** Implement the LLM interaction directly using `httpx`, `tenacity`, Jinja2, and Ollama's OpenAI-compatible API.

## Context

Cardinal needs an LLM-backed SQL generation path.

For the Phase 3 baseline, the system intentionally uses a minimal architecture:

1. Load the warehouse schema.
2. Render a Jinja2 prompt.
3. Send the prompt to Ollama.
4. Parse the returned SQL.
5. Execute the SQL through the evaluation harness.

The implementation uses:

- `httpx` for HTTP communication
- Ollama's OpenAI-compatible `/v1/chat/completions` endpoint
- `tenacity` for retries
- Jinja2 for prompt rendering
- `structlog` for structured logging

LangChain could provide higher-level abstractions around some of these operations.

## Decision

Do not introduce LangChain into the SQL generation path.

Cardinal will maintain a small, explicit LLM client and orchestration layer.

The LLM client owns:

- HTTP communication
- request configuration
- retry behavior
- timeout handling
- token accounting
- latency measurement
- structured logging

The baseline system owns:

- schema loading
- prompt rendering
- response parsing
- interaction with the evaluation-system protocol

## Why

### What LangChain would provide

LangChain could reduce the amount of application code required for:

- model/provider abstraction
- prompt chains
- message construction
- response handling
- integrations with other model providers
- higher-level agent abstractions

These abstractions can become useful in larger or more heterogeneous applications.

### What Cardinal would give up

For this project, the additional abstraction would make the core SQL-generation path less explicit.

The direct implementation makes it possible to see exactly:

- what HTTP request is sent to the model
- which endpoint is being used
- how timeouts are handled
- which failures are retried
- how retry backoff works
- how token usage is captured
- how latency is measured
- how the response is parsed
- how the generated SQL reaches the evaluation harness

This explicitness is particularly valuable because Cardinal is an evaluation-oriented system. Reproducibility and attribution of improvements matter more than minimizing the amount of application code.

The direct implementation also keeps the baseline deliberately small. Later improvements can be added as explicit components rather than being hidden inside a framework abstraction.

## Consequences

### Positive

- Small and understandable LLM integration.
- Full control over retry and timeout behavior.
- Explicit token and latency accounting.
- Easy to unit-test the HTTP layer using `httpx.MockTransport`.
- Provider-specific behavior is visible rather than hidden behind a framework.
- Easier to explain the complete SQL-generation path.
- Prompt versions can be tracked explicitly through the prompt hash.
- No additional framework abstraction is required for the baseline.

### Negative

- More application code must be maintained directly.
- Provider-specific integration work is owned by Cardinal.
- Switching between many model providers may require additional adapter code.
- Higher-level agent and tool abstractions available in LangChain are not available automatically.

## Reconsideration Criteria

This decision should be reconsidered if Cardinal later requires substantial framework capabilities that would otherwise require maintaining a large amount of duplicated infrastructure.

Examples include:

- multiple model providers with substantially different APIs
- complex multi-step agent orchestration
- a large number of reusable tool integrations
- framework features that provide measurable engineering benefits without obscuring evaluation behavior

Until those requirements arise, the direct implementation is preferred.

## Relationship to Phase 3

Phase 3 provided the first real implementation of the LLM call path.

The baseline uses a deliberately minimal prompt and full schema dump so that later improvements can be measured against a known reference.

The decision to avoid LangChain keeps that baseline path explicit and makes it easier to attribute future changes in evaluation results to specific Cardinal components.
