"""TLSx Result Ingestor with scope filtering"""

import logging
from typing import Any, List, Set
from uuid import UUID

from api.config import Settings
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork
from api.application.utils.scope_checker import ScopeChecker
from api.domain.models import ScopeRuleModel

logger = logging.getLogger(__name__)


class TLSxResultIngestor(BaseResultIngestor):
    """
    Handles TLSx certificate scan results with scope filtering.

    TLSx acts as scope filter:
    - Extracts domains from certificates (SAN/CN)
    - Filters domains by program scope rules
    - Saves IPs to hosts table
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

    def __init__(self, uow: ProgramUnitOfWork, settings: Settings):
        super().__init__(uow, settings.TLSX_INGESTOR_BATCH_SIZE)
        self.settings = settings
        self._discovered_domains: Set[str] = set()
        self._saved_domains: Set[str] = set()
        self._in_scope_ips: Set[str] = set()
        self._scope_rules: List[ScopeRuleModel] = []

    async def ingest(self, program_id: UUID, results: List[dict[str, Any]]) -> IngestResult:
        """
        Ingest TLSx results with scope filtering.

        Args:
            program_id: Program UUID
            results: List of TLSx result dicts

        Returns:
            IngestResult with hostnames (non-wildcard certificate domains)
        """
        self._discovered_domains = set()
        self._saved_domains = set()
        self._in_scope_ips = set()

        async with self.uow as uow:
            self._scope_rules = await uow.scope_rules.find_by_program(program_id)

        await super().ingest(program_id, results)

        return IngestResult(
            raw_domains=list(self._saved_domains)
        )

    async def _process_batch(self, uow: ProgramUnitOfWork, program_id: UUID, batch: List[dict[str, Any]]):
        """Process batch of TLSx results with scope filtering"""
        from api.domain.models import HostModel

        for data in batch:
            ip_host = data.get("host") or data.get("ip")
            if not ip_host:
                continue

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

                    host_model = HostModel(
                        host=ip_host,
                        program_id=program_id,
                        source="tlsx",
                        discovery_method="cert_scan"
                    )
                    await uow.hosts.ensure(host_model, unique_fields=["host", "program_id"])

                    for domain in in_scope_domains:
                        if '*' not in domain:
                            domain_model = HostModel(
                                host=domain,
                                program_id=program_id,
                                source="tlsx",
                                discovery_method="cert_domain"
                            )
                            await uow.hosts.ensure(domain_model, unique_fields=["host", "program_id"])
                            self._saved_domains.add(domain)

                    logger.debug(
                        f"IP {ip_host} is in-scope (cert domains: {in_scope_domains})"
                    )
                else:
                    logger.debug(
                        f"IP {ip_host} filtered out (no in-scope cert domains)"
                    )
