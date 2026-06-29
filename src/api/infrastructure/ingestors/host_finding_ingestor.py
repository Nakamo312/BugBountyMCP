"""HostFinding ingestor."""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.contracts import IngestContext
from api.application.pipeline.records import HostFinding
from api.application.utils.scope_checker import ScopeChecker
from api.config import Settings
from api.domain.models import ScopeRuleModel
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.unit_of_work.interfaces.dnsx import DNSxUnitOfWork

logger = logging.getLogger(__name__)


class HostFindingIngestor(BaseResultIngestor):
    """Persist discovered host findings, independent of source tool."""

    def __init__(self, uow: DNSxUnitOfWork, settings: Settings):
        super().__init__(uow, batch_size=50)
        self.settings = settings
        self._scope_rules: list[ScopeRuleModel] = []
        self._in_scope_count = 0
        self._out_of_scope_count = 0
        self._saved_hosts: list[str] = []

    async def before_ingest(
        self,
        uow: DNSxUnitOfWork,
        program_id: UUID,
        results: list[HostFinding],
        context: IngestContext | None = None,
    ) -> None:
        self._in_scope_count = 0
        self._out_of_scope_count = 0
        self._saved_hosts = []
        self._scope_rules = await uow.scope_rules.find_by_program(program_id)

    def build_result(self) -> IngestResult:
        return IngestResult(raw_domains=self._saved_hosts)

    def log_extra(self) -> str:
        return (
            f"in_scope={self._in_scope_count} "
            f"out_of_scope={self._out_of_scope_count} new={len(self._saved_hosts)}"
        )

    async def process_record(
        self,
        uow: DNSxUnitOfWork,
        program_id: UUID,
        finding: HostFinding,
        context: IngestContext | None = None,
    ) -> None:
        if not isinstance(finding, HostFinding):
            raise TypeError(f"HostFindingIngestor expects HostFinding, got {type(finding).__name__}")

        host_name = finding.host.strip()
        if not host_name:
            logger.warning("Invalid host finding, missing host: %r", finding)
            return

        if not ScopeChecker.is_in_scope(host_name, self._scope_rules):
            self._out_of_scope_count += 1
            return

        existing = await uow.hosts.get_by_fields(
            program_id=program_id,
            host=host_name,
        )
        await uow.hosts.ensure(
            program_id=program_id,
            host=host_name,
            in_scope=True,
        )
        self._in_scope_count += 1

        if not existing:
            self._saved_hosts.append(host_name)
