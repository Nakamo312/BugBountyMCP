"""Replay raw artifact sidecar markers into the metadata store."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from api.infrastructure.artifacts.raw_artifact_repository import RawArtifactRepository
from api.infrastructure.orchestration.store import OrchestrationStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawArtifactReconcileResult:
    processed: int = 0
    repaired: int = 0
    failed: int = 0


class RawArtifactReconciler:
    """Reconcile raw artifact files whose metadata insert previously failed."""

    MARKER_GLOB = "*.ndjson.reconcile.json"
    MARKER_TYPE = "raw_artifact_metadata_record_failed"

    def __init__(
        self,
        *,
        base_dir: str | Path,
        repository: RawArtifactRepository,
        orchestration_store: OrchestrationStore,
    ):
        self.base_dir = Path(base_dir)
        self.repository = repository
        self.orchestration_store = orchestration_store

    async def reconcile_once(self) -> RawArtifactReconcileResult:
        processed = 0
        repaired = 0
        failed = 0

        for marker_path in sorted(self.base_dir.rglob(self.MARKER_GLOB)):
            processed += 1
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                if marker.get("type") != self.MARKER_TYPE:
                    continue
                metadata = self._normalize_metadata(marker["artifact"])
                await self.repository.record(metadata)
                run_id = metadata.get("run_id")
                if run_id is not None:
                    await self.orchestration_store.clear_run_reconcile(run_id=run_id)
                marker_path.unlink()
                repaired += 1
            except Exception:
                failed += 1
                logger.exception("Failed to reconcile raw artifact marker: %s", marker_path)

        return RawArtifactReconcileResult(
            processed=processed,
            repaired=repaired,
            failed=failed,
        )

    @staticmethod
    def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(metadata)
        for key in ("id", "program_id", "job_id", "run_id"):
            value = normalized.get(key)
            if value in (None, ""):
                normalized[key] = None
            elif not isinstance(value, UUID):
                normalized[key] = UUID(str(value))
        return normalized
