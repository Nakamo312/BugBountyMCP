from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol, TypeVar

from .batch_store import GraphFactBatchStore
from .contracts import GraphFactBatch

GroupKey = TypeVar("GroupKey")


class RowProducer(Protocol):
    def produce(self, row: Mapping[str, Any]) -> GraphFactBatch | None: ...


class GroupedRowsProducer(Protocol):
    def produce(self, rows: Iterable[Mapping[str, Any]]) -> GraphFactBatch | None: ...


@dataclass(frozen=True)
class RebuildSourceResult:
    rows_scanned: int = 0
    groups_scanned: int = 0
    enqueued: int = 0
    skipped: int = 0


def rebuild_row_source(
    *,
    rows: list[Mapping[str, Any]],
    producer: RowProducer,
    store: GraphFactBatchStore,
    dedupe_key: Callable[[Mapping[str, Any], str], str],
) -> RebuildSourceResult:
    enqueued = 0
    skipped = 0
    for row in rows:
        batch = producer.produce(row)
        if batch is None:
            skipped += 1
            continue
        _enqueue_rebuild_batch(store, batch, dedupe_key(row, batch.parser_version))
        enqueued += 1
    return RebuildSourceResult(rows_scanned=len(rows), enqueued=enqueued, skipped=skipped)


def rebuild_grouped_source(
    *,
    rows: list[Mapping[str, Any]],
    group_key: Callable[[Mapping[str, Any]], GroupKey],
    producer: GroupedRowsProducer,
    store: GraphFactBatchStore,
    dedupe_key: Callable[[GroupKey, str], str],
) -> RebuildSourceResult:
    grouped_rows = _group_rows(rows, group_key)
    enqueued = 0
    skipped = 0
    for key, group in grouped_rows.items():
        batch = producer.produce(group)
        if batch is None:
            skipped += 1
            continue
        _enqueue_rebuild_batch(store, batch, dedupe_key(key, batch.parser_version))
        enqueued += 1
    return RebuildSourceResult(
        rows_scanned=len(rows),
        groups_scanned=len(grouped_rows),
        enqueued=enqueued,
        skipped=skipped,
    )


def _group_rows(
    rows: Iterable[Mapping[str, Any]],
    group_key: Callable[[Mapping[str, Any]], GroupKey],
) -> "OrderedDict[GroupKey, list[Mapping[str, Any]]]":
    grouped: "OrderedDict[GroupKey, list[Mapping[str, Any]]]" = OrderedDict()
    for row in rows:
        grouped.setdefault(group_key(row), []).append(row)
    return grouped


def _enqueue_rebuild_batch(store: GraphFactBatchStore, batch: GraphFactBatch, dedupe_key: str) -> None:
    store.enqueue(batch, dedupe_key=f"rebuild:{dedupe_key}", reset_existing=True)
