from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from .batch_store import GraphFactBatchStore, connect_postgres
from .settings import GraphProjectorSettings

_EnqueuerT = TypeVar("_EnqueuerT")
_ProducerT = TypeVar("_ProducerT")


class GraphFactEnqueuerFactory:
    """Build canonical GraphFact enqueuers from shared CLI runtime settings."""

    def __init__(self, settings: GraphProjectorSettings) -> None:
        self._settings = settings

    def build(
        self,
        *,
        producer_factory: Callable[[], _ProducerT],
        enqueuer_factory: Callable[..., _EnqueuerT],
    ) -> _EnqueuerT:
        connection = connect_postgres(self._settings.postgres_dsn)
        store = GraphFactBatchStore(connection)
        return enqueuer_factory(
            connection=connection,
            store=store,
            producer=producer_factory(),
            worker_id=self._settings.worker_id,
            lock_seconds=self._settings.batch_lock_seconds,
            max_attempts=self._settings.batch_max_attempts,
        )
