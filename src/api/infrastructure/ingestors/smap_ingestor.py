"""Smap Result Ingestor"""

import logging
from uuid import UUID
from typing import Any, List, Set, Dict

from api.domain.models import ScopeRuleModel
from api.infrastructure.unit_of_work.interfaces.naabu import AbstractNaabuUnitOfWork
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.application.contracts import IngestContext
from api.config import Settings
from api.application.utils.scope_checker import ScopeChecker

logger = logging.getLogger(__name__)


class SmapResultIngestor(BaseResultIngestor):
    """
    Ingests Smap port scan results into database.

    Processing flow:
    1. Ensure IP address exists
    2. If hostnames exist and in scope - create host records
    3. Create service records for each port
    4. Batch processing with savepoint recovery

    Smap result format:
    {
        "ip": "217.12.106.105",
        "hostnames": ["suoext.alfabank.ru"],
        "ports": [
            {"port": 443, "service": "https?", "protocol": "tcp"}
        ],
        "start_time": "2026-01-16T02:34:41.519350018Z",
        "end_time": "2026-01-16T02:34:42.143294138Z"
    }
    """

    def __init__(self, uow: AbstractNaabuUnitOfWork, settings: Settings):
        super().__init__(uow, batch_size=settings.NAABU_INGESTOR_BATCH_SIZE)
        self._scope_rules: List[ScopeRuleModel] = []
        self._discovered_ips: Set[str] = set()
        self._discovered_hostnames: Set[str] = set()
        self._processed = 0
        self._skipped = 0

    async def before_ingest(
        self,
        uow: AbstractNaabuUnitOfWork,
        program_id: UUID,
        results: List[Dict[str, Any]],
        context: IngestContext | None = None,
    ) -> None:
        self._discovered_ips = set()
        self._discovered_hostnames = set()
        self._processed = 0
        self._skipped = 0
        self._scope_rules = await uow.scope_rules.find_by_program(program_id)

    def build_result(self) -> IngestResult:
        return IngestResult(
            ips=list(self._discovered_ips),
            raw_domains=list(self._discovered_hostnames),
        )

    def log_extra(self) -> str:
        return (
            f"processed={self._processed} skipped={self._skipped} "
            f"ips={len(self._discovered_ips)} hostnames={len(self._discovered_hostnames)}"
        )

    async def process_record(self, uow: AbstractNaabuUnitOfWork, program_id: UUID, result: Dict[str, Any], context: IngestContext | None = None) -> None:
        """Process a single batch of Smap results"""
        try:
            ip_address = result.get("ip")
            ports = result.get("ports", [])
            hostnames = result.get("hostnames", [])

            if not ip_address:
                logger.warning(f"Invalid Smap result, missing ip: {result}")
                self._skipped += 1
                return

            if not ports:
                logger.debug(f"Smap result has no ports: {ip_address}")
                self._skipped += 1
                return

            ip_obj = await uow.ip_addresses.ensure(
                program_id=program_id,
                address=ip_address,
                in_scope=True
            )

            self._discovered_ips.add(ip_address)

            if hostnames:
                for hostname in hostnames:
                    if ScopeChecker.is_in_scope(hostname, self._scope_rules):
                        self._discovered_hostnames.add(hostname)
                        await uow.hosts.ensure(
                            program_id=program_id,
                            host=hostname,
                            in_scope=True
                        )

            for port_info in ports:
                port = port_info.get("port")
                service_name = port_info.get("service", "")

                if port is None:
                    continue

                scheme = "https" if int(port) == 443 else "http"

                await uow.services.ensure(
                    ip_id=ip_obj.id,
                    scheme=scheme,
                    port=int(port),
                    technologies={"service": service_name} if service_name else {}
                )

            self._processed += 1

        except Exception as e:
            logger.error(
                f"Failed to process Smap result {result}: {e}",
                exc_info=True
            )
            self._skipped += 1
            return
