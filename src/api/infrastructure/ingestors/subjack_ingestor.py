"""Subjack result ingestor for subdomain takeover research signals."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from api.application.contracts import IngestContext
from api.config import Settings
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork

logger = logging.getLogger(__name__)

SUBDOMAIN_TAKEOVER_SIGNAL_TYPE = "subdomain_takeover_possible"
SUBDOMAIN_TAKEOVER_SIGNAL_VERSION = "subjack-signal-v1"
SUBDOMAIN_TAKEOVER_RULE_ID = "subjack_takeover_possible"
SUBDOMAIN_TAKEOVER_RULE_VERSION = "subjack-rule-v1"


class SubjackResultIngestor(BaseResultIngestor):
    """
    Handles batch ingestion of Subjack subdomain takeover scan results.

    Subjack output is stored as a research signal, not a FindingModel. A scanner
    observation is evidence for a later hypothesis/critic/promotion workflow;
    it is not itself a verified finding.
    """

    def __init__(self, uow: HTTPXUnitOfWork, settings: Settings):
        super().__init__(uow, settings.HTTPX_INGESTOR_BATCH_SIZE)
        self.settings = settings
        self._signals_created = 0
        self._skipped = 0

    async def before_ingest(
        self,
        uow: HTTPXUnitOfWork,
        program_id: UUID,
        results: list[dict[str, Any]],
        context: IngestContext | None = None,
    ) -> None:
        self._signals_created = 0
        self._skipped = 0

    def log_extra(self) -> str:
        return f"signals={self._signals_created} skipped={self._skipped}"

    async def process_record(
        self,
        uow: HTTPXUnitOfWork,
        program_id: UUID,
        data: dict[str, Any],
        context: IngestContext | None = None,
    ) -> None:
        """Process one Subjack result as a research signal."""
        subdomain = self._string_or_none(data.get("subdomain"))
        service = self._string_or_none(data.get("service")) or "unknown"
        vulnerable = bool(data.get("vulnerable", False))
        cname = self._string_or_none(data.get("cname"))

        if not subdomain or not vulnerable:
            self._skipped += 1
            logger.debug("Skipping non-vulnerable or invalid Subjack result")
            return

        host = await uow.hosts.get_by_fields(program_id=program_id, host=subdomain)
        if not host:
            self._skipped += 1
            logger.warning(
                "Host %s not found in program %s, skipping takeover signal",
                subdomain,
                program_id,
            )
            return

        payload = {
            "subdomain": subdomain,
            "service": service,
            "cname": cname,
            "source_tool": "subjack",
            "claim": "Subjack reported a possible subdomain takeover. Manual verification is required before promotion.",
            "job_id": str(context.job_id) if context and context.job_id else None,
            "run_id": str(context.run_id) if context and context.run_id else None,
            "correlation_id": str(context.correlation_id) if context and context.correlation_id else None,
            "raw_artifact_id": str(context.raw_artifact_id) if context and context.raw_artifact_id else None,
        }

        await uow.research_signals.upsert_signal(
            program_id=program_id,
            signal_type=SUBDOMAIN_TAKEOVER_SIGNAL_TYPE,
            signal_version=SUBDOMAIN_TAKEOVER_SIGNAL_VERSION,
            rule_id=SUBDOMAIN_TAKEOVER_RULE_ID,
            rule_version=SUBDOMAIN_TAKEOVER_RULE_VERSION,
            asset_type="host",
            asset_id=str(host.id),
            evidence_fingerprint=self._fingerprint(
                program_id=program_id,
                subdomain=subdomain,
                service=service,
                cname=cname,
            ),
            confidence=0.65,
            payload_json={key: value for key, value in payload.items() if value is not None},
        )
        self._signals_created += 1
        logger.info("Recorded subdomain takeover signal: %s (%s)", subdomain, service)

    @staticmethod
    def _fingerprint(
        *,
        program_id: UUID,
        subdomain: str,
        service: str,
        cname: str | None,
    ) -> str:
        payload = {
            "program_id": str(program_id),
            "signal_type": SUBDOMAIN_TAKEOVER_SIGNAL_TYPE,
            "subdomain": subdomain,
            "service": service,
            "cname": cname,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _string_or_none(value: Any) -> str | None:
        if value is None:
            return None
        string_value = str(value).strip()
        return string_value or None
