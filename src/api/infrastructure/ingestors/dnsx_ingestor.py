import logging
from typing import Any, List, Set
from uuid import UUID

from api.application.contracts import IngestContext
from api.config import Settings
from api.infrastructure.ingestors.base_result_ingestor import \
    BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.unit_of_work.interfaces.dnsx import DNSxUnitOfWork

logger = logging.getLogger(__name__)


class DNSxResultIngestor(BaseResultIngestor):
    """
    Handles batch ingestion of DNSx scan results into domain entities.

    Creates:
    - IP addresses from A and AAAA records
    - Host-IP associations
    - DNS records (A, AAAA, CNAME, MX, TXT, NS, SOA, PTR)

    Returns:
    - ips: List of discovered IP addresses for port scanning
    - hostnames: List of CNAME targets for further resolution
    """

    def __init__(
        self,
        uow: DNSxUnitOfWork,
        settings: Settings,
        create_missing_hosts: bool = False,
    ):
        super().__init__(uow, settings.DNSX_INGESTOR_BATCH_SIZE)
        self.settings = settings
        self.create_missing_hosts = create_missing_hosts
        self._discovered_ips: Set[str] = set()
        self._discovered_hostnames: Set[str] = set()

    async def before_ingest(
        self,
        uow: DNSxUnitOfWork,
        program_id: UUID,
        results: List[dict[str, Any]],
        context: IngestContext | None = None,
    ) -> None:
        self._discovered_ips = set()
        self._discovered_hostnames = set()

    def build_result(self) -> IngestResult:
        return IngestResult(
            ips=list(self._discovered_ips),
            hostnames=list(self._discovered_hostnames),
        )

    async def process_record(
        self,
        uow: DNSxUnitOfWork,
        program_id: UUID,
        data: dict[str, Any],
        context: IngestContext | None = None,
    ):
        host_name = data.get("host")
        if not host_name:
            logger.debug("Skipping DNSx result without host")
            return

        host = await uow.hosts.get_by_fields(program_id=program_id, host=host_name)
        if not host:
            if not self.create_missing_hosts:
                logger.warning(f"Host {host_name} not found in program {program_id}, skipping DNS records")
                return
            logger.info(f"Host {host_name} not found in program {program_id}, creating from DNSx result")
            host = await uow.hosts.ensure(program_id=program_id, host=host_name)

        a_records = data.get("a", [])
        for record in a_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="A",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )
            ip = await uow.ip_addresses.ensure(program_id=program_id, address=record)
            await uow.host_ips.ensure(host_id=host.id, ip_id=ip.id, source="dnsx")
            self._discovered_ips.add(record)

        aaaa_records = data.get("aaaa", [])
        for record in aaaa_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="AAAA",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )
            ip = await uow.ip_addresses.ensure(program_id=program_id, address=record)
            await uow.host_ips.ensure(host_id=host.id, ip_id=ip.id, source="dnsx")
            self._discovered_ips.add(record)

        cname_records = data.get("cname", [])
        for record in cname_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="CNAME",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )
            self._discovered_hostnames.add(record)

        mx_records = data.get("mx", [])
        for record in mx_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="MX",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )

        txt_records = data.get("txt", [])
        for record in txt_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="TXT",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )

        ns_records = data.get("ns", [])
        for record in ns_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="NS",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )

        soa_records = data.get("soa", [])
        for record in soa_records:
            if isinstance(record, dict):
                soa_value = f"{record.get('ns', '')} {record.get('mailbox', '')} {record.get('serial', 0)} {record.get('refresh', 0)} {record.get('retry', 0)} {record.get('expire', 0)} {record.get('minttl', 0)}"
            else:
                soa_value = str(record)

            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="SOA",
                value=soa_value,
                is_wildcard=data.get("wildcard", False)
            )

        ptr_records = data.get("ptr", [])
        for record in ptr_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="PTR",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )

        logger.debug(f"Processed DNS records for host {host_name}: A={len(a_records)}, AAAA={len(aaaa_records)}, CNAME={len(cname_records)}, MX={len(mx_records)}, TXT={len(txt_records)}, NS={len(ns_records)}, SOA={len(soa_records)}, PTR={len(ptr_records)}")

class DNSxDiscoveryResultIngestor(DNSxResultIngestor):
    """DNSx ingestor for discovery edges that should materialize new hosts."""

    def __init__(self, uow: DNSxUnitOfWork, settings: Settings):
        super().__init__(uow=uow, settings=settings, create_missing_hosts=True)
