from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from cardinal.config import get_settings


class WarehouseReader:
    """Read-only access to the warehouse using the configured RO credentials."""

    def __init__(self) -> None:
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(
                get_settings().postgres_ro_dsn,
            )
        return self._engine

    def fetch_all(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            result = connection.execute(
                text(query),
                params or {},
            )
            return [dict(row) for row in result.mappings().all()]

    def fetch_scalar(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        with self.engine.connect() as connection:
            result = connection.execute(
                text(query),
                params or {},
            )
            return result.scalar_one()

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> WarehouseReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.dispose()
