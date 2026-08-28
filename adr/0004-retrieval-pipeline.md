# ADR 0004: Hybrid Retrieval with Cross-Encoder Reranking

- **Status:** Accepted
- **Date:** 2026-08-27
- **Decision:** Use dense retrieval and PostgreSQL lexical retrieval as complementary candidate generators, combine them with Reciprocal Rank Fusion (RRF), and rerank the fused candidates with an ONNX cross-encoder.

## Context

Cardinal needs reliable schema retrieval for natural-language SQL questions.

The retrieval system must identify the warehouse tables required to answer a question. The Phase 6 evaluation uses the Olist gold retrieval suite containing 150 questions:

- 130 answerable questions
- 20 unanswerable questions

Answerable questions are annotated with `required_tables`.

A question is counted as a retrieval hit only when all required tables appear among the retrieved table cards at the evaluated cutoff.

Phase 6 evaluated:

1. PostgreSQL lexical retrieval
2. Dense vector retrieval
3. Reciprocal Rank Fusion of lexical and dense retrieval
4. RRF followed by cross-encoder reranking

## Decision

Use a hybrid retrieval pipeline:

```text
Natural-language question
          |
          +------------------+
          |                  |
          v                  v
   PostgreSQL lexical    Dense retrieval
       retrieval          (BGE embeddings)
          |                  |
          +--------+---------+
                   |
                   v
        Reciprocal Rank Fusion
                   |
                   v
          Candidate pool
                   |
                   v
       ONNX cross-encoder
            reranking
                   |
                   v
              Top-k cards
