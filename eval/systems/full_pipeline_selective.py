from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import joblib
import psycopg

from cardinal.confidence.grounding import grounding_score
from cardinal.confidence.model import ConfidenceModel
from cardinal.confidence.signals import (
    build_feature_vector,
    load_row_count_reference,
    load_warehouse_bounds,
)
from eval.systems.retrieval_guarded_repaired import (
    RetrievalGuardedRepairedSystem,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_model.joblib"
)

POLICY_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "confidence_policy.json"
)



class FullPipelineSelectiveSystem:
    """Full SQL pipeline with learned selective abstention."""

    def __init__(self) -> None:
        self.base_system = RetrievalGuardedRepairedSystem()

        pipeline = joblib.load(
            MODEL_PATH
        )

        self.confidence_model = ConfidenceModel(
            pipeline=pipeline
        )

        policy = json.loads(
            POLICY_PATH.read_text(
                encoding="utf-8",
            )
        )

        self.threshold = float(
            policy["threshold"]
        )

        self.warehouse_bounds = (
            load_warehouse_bounds()
        )

        self.row_count_references = (
            load_row_count_reference()
        )

    def close(self) -> None:
        self.base_system.close()

    @staticmethod
    def _execute_sqlite(
        sql: str,
        database_path: Path,
    ) -> tuple[
        list[str],
        list[tuple[Any, ...]],
    ]:
        with sqlite3.connect(
            database_path
        ) as connection:
            cursor = connection.execute(
                sql
            )

            columns = [
                description[0]
                for description in cursor.description
            ]

            rows = cursor.fetchall()

        return columns, rows

    @staticmethod
    def _execute_postgres(
        sql: str,
    ) -> tuple[
        list[str],
        list[tuple[Any, ...]],
    ]:
        with (
            psycopg.connect(
                host=os.environ["POSTGRES_HOST"],
                port=os.environ["POSTGRES_PORT"],
                user=os.environ["POSTGRES_USER"],
                password=os.environ[
                    "POSTGRES_PASSWORD"
                ],
                dbname=os.environ["POSTGRES_DB"],
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(sql)

            columns = [
                description.name
                for description in cursor.description
            ]

            rows = cursor.fetchall()

        return columns, rows

    @staticmethod
    def _non_negative_fields(
        metadata: Mapping[str, Any],
    ) -> set[str]:
        fields: set[str] = set()

        selected_metrics = metadata.get(
            "selected_metrics",
            [],
        )

        if not isinstance(
            selected_metrics,
            list,
        ):
            return fields

        for metric in selected_metrics:
            non_negative = getattr(
                metric,
                "non_negative",
                False,
            )

            name = getattr(
                metric,
                "name",
                None,
            )

            if non_negative and isinstance(
                name,
                str,
            ):
                fields.add(name)

        return fields

    def _execute_prediction(
        self,
        sql: str,
        db_context: Mapping[str, Any],
    ) -> tuple[
        list[str],
        list[tuple[Any, ...]],
    ]:
        source = db_context.get("source")

        if source == "sqlite":
            database_path = db_context.get(
                "database_path"
            )

            if not isinstance(
                database_path,
                Path,
            ):
                raise ValueError(
                    "SQLite selective prediction requires "
                    "database_path."
                )

            return self._execute_sqlite(
                sql,
                database_path,
            )

        if source == "postgres":
            return self._execute_postgres(
                sql
            )

        raise ValueError(
            f"Unsupported database source: {source}"
        )

    def answer(
        self,
        question: str,
        db_context: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        predicted_sql, metadata = (
            self.base_system.answer(
                question,
                db_context,
            )
        )

        columns, rows = (
            self._execute_prediction(
                predicted_sql,
                db_context,
            )
        )

        answer_text = (
            self.base_system.loop.run_until_complete(
                self.base_system.answer_synthesizer.synthesize(
                    question,
                    rows,
                )
            )
        )

        grounding = grounding_score(
            answer_text,
            rows,
        )

        source = str(
            db_context.get("source")
        )

        category_value = db_context.get(
            "category"
        )

        category = (
            str(category_value)
            if category_value is not None
            else None
        )

        features = build_feature_vector(
            agreement=float(
                metadata.get(
                    "agreement_rate",
                    0.0,
                )
            ),
            columns=columns,
            rows=rows,
            category=category,
            source=source,
            grounding=grounding,
            top_rrf_score=metadata.get(
                "top_rrf_score"
            ),
            reranker_margin=metadata.get(
                "reranker_margin"
            ),
            repair_attempts=int(
                metadata.get(
                    "repair_attempts",
                    0,
                )
            ),
            guardrail_failures=int(
                metadata.get(
                    "guardrail_failures",
                    0,
                )
            ),
            estimated_query_cost=metadata.get(
                "estimated_query_cost"
            ),
            agent_steps=int(
                metadata.get(
                    "agent_steps",
                    0,
                )
            ),
            non_negative_fields=(
                self._non_negative_fields(
                    metadata
                )
            ),
            row_count_references=(
                self.row_count_references
            ),
            warehouse_bounds=(
                self.warehouse_bounds
            ),
        )

        confidence = (
            self.confidence_model.predict_proba(
                features.to_dict()
            )
        )

        abstained = (
            confidence < self.threshold
        )

        metadata["confidence"] = confidence
        metadata["abstained"] = abstained
        metadata["confidence_threshold"] = (
            self.threshold
        )
        metadata["grounding_score"] = grounding
        metadata["synthesized_answer"] = (
            answer_text
        )
        metadata["confidence_features"] = (
            features.to_dict()
        )

        return predicted_sql, metadata