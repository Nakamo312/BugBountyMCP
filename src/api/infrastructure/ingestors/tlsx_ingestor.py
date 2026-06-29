"""TLSx Result Ingestor with scope filtering"""

import ipaddress
import logging
from typing import Any, List, Set
from uuid import UUID

from api.application.contracts import IngestContext
from api.config import Settings
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.unit_of_work.interfaces.dnsx import DNSxUnitOfWork
from api.application.utils.scope_checker import ScopeChecker
from api.domain.models import ScopeRuleModel

logger = logging.getLogger(__name__)


class TLSxResultIngestor(BaseResultIngestor):
    """
    Handles TLSx certificate scan results with scope filtering.

    TLSx acts as scope filter:
    - Extracts domains from certificates (SAN/CN)
    - Filters domains by program scope rules
    - Saves IP targets to ip_addresses
    - Saves non-wildcard in-scope domains to hosts table
    - Returns discovered domains for downstream processing

    TLSx result format:
    {
        "host": "8.8.8.8",
        "ip": "8.8.8.8",
        "subject_an": ["dns.google", "*.dns.google"],
        "subject_cn": "dns.google"
    }

    Returns IngestResult with:
    - hostnames (list of non-wildcard certificate domains)
    """

    def __init__(self, uow: DNSxUnitOfWork, settings: Settings):
        super().__init__(uow, settings.TLSX_INGESTOR_BATCH_SIZE)
        self.settings = settings
        self._discovered_domains: Set[str] = set()
        self._saved_domains: Set[str] = set()
        self._in_scope_ips: Set[str] = set()
        self._scope_rules: List[ScopeRuleModel] = []

    async def before_ingest(
        self,
        uow: DNSxUnitOfWork,
        program_id: UUID,
        results: List[dict[str, Any]],
        context: IngestContext | None = None,
    ) -> None:
        self._discovered_domains = set()
        self._saved_domains = set()
        self._in_scope_ips = set()
        self._scope_rules = await uow.scope_rules.find_by_program(program_id)

    def build_result(self) -> IngestResult:
        return IngestResult(raw_domains=list(self._saved_domains))

    def log_extra(self) -> str:
        return f"in_scope_ips={len(self._in_scope_ips)} saved_domains={len(self._saved_domains)}"

    async def process_record(self, uow: DNSxUnitOfWork, program_id: UUID, data: dict[str, Any], context: IngestContext | None = None) -> None:
        """Process batch of TLSx results with scope filtering"""
        ip_host = data.get("host") or data.get("ip")
        if not ip_host:
            return

        cert_domains = set()

        subject_an = data.get("subject_an", [])
        if subject_an:
            for domain in subject_an:
                if domain and isinstance(domain, str):
                    cert_domains.add(domain)
                    self._discovered_domains.add(domain)

        subject_cn = data.get("subject_cn")
        if subject_cn and isinstance(subject_cn, str):
            cert_domains.add(subject_cn)
            self._discovered_domains.add(subject_cn)

        if cert_domains:
            in_scope_domains, _ = ScopeChecker.filter_in_scope(
                list(cert_domains), self._scope_rules
            )

            if in_scope_domains:
                self._in_scope_ips.add(ip_host)

                await self._ensure_target_identity(
                    uow,
                    program_id=program_id,
                    target=str(ip_host),
                )

                for domain in in_scope_domains:
                    if '*' not in domain:
                        await uow.hosts.ensure(
                            program_id=program_id,
                            host=domain,
                            in_scope=True
                        )
                        self._saved_domains.add(domain)

                logger.debug(
                    f"IP {ip_host} is in-scope (cert domains: {in_scope_domains})"
                )
            else:
                logger.debug(
                    f"IP {ip_host} filtered out (no in-scope cert domains)"
                )

    @staticmethod
    async def _ensure_target_identity(
        uow: DNSxUnitOfWork,
        *,
        program_id: UUID,
        target: str,
    ) -> None:
        normalized = target.strip()
        if not normalized:
            return

        try:
            ipaddress.ip_address(normalized)
        except ValueError:
            await uow.hosts.ensure(
                program_id=program_id,
                host=normalized,
                in_scope=True,
            )
            return

        await uow.ip_addresses.ensure(
            program_id=program_id,
            address=normalized,
            in_scope=True,
        )
