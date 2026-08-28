from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import yaml
from transformers import AutoTokenizer

from cardinal.config import get_settings
from cardinal.retrieval.models import RetrievalResult


class SchemaCardReranker:
    """Rerank retrieved schema cards using an ONNX cross-encoder."""

    def __init__(
        self,
        session: ort.InferenceSession | None = None,
        tokenizer: Any | None = None,
        config_path: Path | str = "configs/retrieval.yaml",
    ) -> None:
        config_path = Path(config_path)
        config = yaml.safe_load(
            config_path.read_text(encoding="utf-8"),
        )

        rerank_config = config.get("rerank", {})

        self.batch_size = int(rerank_config.get("batch_size", 16))
        self.input_top_k = int(rerank_config.get("input_top_k", 50))
        self.output_top_k = int(rerank_config.get("output_top_k", 10))

        if self.batch_size <= 0:
            raise ValueError("rerank.batch_size must be positive.")

        if self.input_top_k <= 0:
            raise ValueError("rerank.input_top_k must be positive.")

        if self.output_top_k <= 0:
            raise ValueError("rerank.output_top_k must be positive.")

        model_path = Path(get_settings().rerank_model_path)

        if session is None:
            self.session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )
        else:
            self.session = session

        if tokenizer is None:
            tokenizer_path = model_path.parent
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r"The tokenizer you are loading.*incorrect regex pattern.*",
                    category=UserWarning,
                )
                self.tokenizer = AutoTokenizer.from_pretrained(
                    str(tokenizer_path),
                    local_files_only=True,
                )
        else:
            self.tokenizer = tokenizer

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        limit: int | None = None,
    ) -> list[RetrievalResult]:
        """Rerank candidates and return the highest-scoring cards."""
        if not query.strip() or not candidates:
            return []

        candidates = candidates[: self.input_top_k]

        scores: list[float] = []

        for start in range(0, len(candidates), self.batch_size):
            batch = candidates[start : start + self.batch_size]

            encoded = self.tokenizer(
                [query] * len(batch),
                [candidate.card_text for candidate in batch],
                padding=True,
                truncation=True,
                return_tensors="np",
            )

            inputs = {
                name: encoded[name].astype(np.int64) for name in ("input_ids", "attention_mask")
            }

            outputs = self.session.run(["logits"], inputs)
            batch_scores = np.asarray(outputs[0]).reshape(-1)

            scores.extend(float(score) for score in batch_scores)

        reranked = [
            candidate.model_copy(update={"score": score})
            for candidate, score in zip(
                candidates,
                scores,
                strict=True,
            )
        ]

        reranked.sort(
            key=lambda result: (-result.score, result.card_id),
        )

        output_limit = limit if limit is not None else self.output_top_k

        return reranked[:output_limit]
