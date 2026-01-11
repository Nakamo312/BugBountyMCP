import logging
from typing import Any
from uuid import UUID

from api.config import Settings
from api.infrastructure.ingestors.base_result_ingestor import \
    BaseResultIngestor
from api.infrastructure.unit_of_work.interfaces.dnsx import DNSxUnitOfWork

logger = logging.getLogger(__name__)


class DNSxResultIngestor(BaseResultIngestor):
    """
    Handles batch ingestion of DNSx scan results into domain entities.
    Uses savepoints to allow partial success without rolling back entire transaction.
    """

    def __init__(self, uow: DNSxUnitOfWork, settings: Settings):
        super().__init__(uow, settings.DNSX_INGESTOR_BATCH_SIZE)
        self.settings = settings

    async def _process_batch(self, uow: DNSxUnitOfWork, program_id: UUID, batch: list[dict[str, Any]]):
        """Process a batch of DNSx results"""
        for data in batch:
            await self._process_record(uow, program_id, data)

    async def _process_record(
        self,
        uow: DNSxUnitOfWork,
        program_id: UUID,
        data: dict[str, Any]
    ):
        host_name = data.get("host")
        if not host_name:
            logger.debug("Skipping DNSx result without host")
            return

        host = await uow.hosts.get_by_fields(program_id=program_id, host=host_name)
        if not host:
            logger.warning(f"Host {host_name} not found in program {program_id}, skipping DNS records")
            return

        a_records = data.get("a", [])
        for record in a_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="A",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )

        aaaa_records = data.get("aaaa", [])
        for record in aaaa_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="AAAA",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )

        cname_records = data.get("cname", [])
        for record in cname_records:
            await uow.dns_records.ensure(
                host_id=host.id,
                record_type="CNAME",
                value=record,
                is_wildcard=data.get("wildcard", False)
            )

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
