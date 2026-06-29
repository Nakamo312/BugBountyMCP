from __future__ import annotations

from typing import Any, Mapping

from ..contracts import GraphFactBatch
from .canonical_inventory_fact_builder import build_canonical_inventory_batch
from .canonical_inventory_keys import canonical_inventory_dedupe_key, inventory_service_key


class CanonicalInventoryGraphFactProducer:
    def __init__(self, *, parser_version: str = "canonical-inventory.v1") -> None:
        self._parser_version = parser_version

    @property
    def parser_version(self) -> str:
        return self._parser_version

    def produce(self, rows: list[Mapping[str, Any]]) -> GraphFactBatch | None:
        return build_canonical_inventory_batch(rows, parser_version=self._parser_version)


__all__ = [
    "CanonicalInventoryGraphFactProducer",
    "canonical_inventory_dedupe_key",
    "inventory_service_key",
]
