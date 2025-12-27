from typing import List, Dict, Any
from uuid import UUID
import logging

from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork

BATCH_SIZE = 50
logger = logging.getLogger(__name__)


class HTTPXResultIngestor:
    """
    Handles batch ingestion of HTTPX scan results into domain entities.
    Uses savepoints to allow partial success without rolling back entire transaction.
    """

    def __init__(self, uow: HTTPXUnitOfWork):
        self.uow = uow

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]):
        async with self.uow as uow:
            for batch_index, batch in enumerate(self._chunks(results, BATCH_SIZE)):
                savepoint_name = f"batch_{batch_index}"
                await uow.create_savepoint(savepoint_name)

                try:
                    for data in batch:
                        await self._process_record(uow, program_id, data)
                    await uow.release_savepoint(savepoint_name)
                except Exception as exc:
                    await uow.rollback_to_savepoint(savepoint_name)
                    logger.error("Batch %d failed: %s", batch_index, exc)
            await uow.commit()

    async def _process_record(self, uow: HTTPXUnitOfWork, program_id: UUID, data: Dict[str, Any]):
        host = await self._ensure_host(uow, program_id, data)
        if not host:
            return

        ip = await self._ensure_ip(uow, program_id, host, data)
        if not ip:
            return

        service = await self._ensure_service(uow, ip, data)
        endpoint = await self._ensure_endpoint(uow, host, service, data)
        await self._process_query_params(uow, endpoint, service, data)

    async def _ensure_host(self, uow: HTTPXUnitOfWork, program_id: UUID, data: Dict[str, Any]):
        host_name = data.get("host") or data.get("input")
        if not host_name:
            return None
        return await uow.hosts.ensure(program_id=program_id, host=host_name)

    async def _ensure_ip(self, uow: HTTPXUnitOfWork, program_id: UUID, host, data: Dict[str, Any]):
        host_ip = data.get("host_ip")
        if not host_ip:
            return None
        ip = await uow.ips.ensure(program_id=program_id, address=host_ip)
        await uow.host_ips.ensure(host_id=host.id, ip_id=ip.id, source="httpx")

        for extra_ip in data.get("a", []):
            ip2 = await uow.ips.ensure(program_id=program_id, address=extra_ip)
            await uow.host_ips.ensure(host_id=host.id, ip_id=ip2.id, source="httpx-dns")

        return ip

    async def _ensure_service(self, uow: HTTPXUnitOfWork, ip, data: Dict[str, Any]):
        scheme = data.get("scheme", "http")
        port = int(data.get("port", 80))
        technologies = {tech: True for tech in data.get("tech", [])}
        return await uow.services.ensure(ip_id=ip.id, scheme=scheme, port=port, technologies=technologies)

    async def _ensure_endpoint(self, uow: HTTPXUnitOfWork, host, service, data: Dict[str, Any]):
        raw_path = data.get("path") or "/"
        normalized_path = raw_path.lower()
        method = data.get("method", "GET")
        status_code = data.get("status_code")
        return await uow.endpoints.ensure(
            host_id=host.id,
            service_id=service.id,
            path=raw_path,
            normalized_path=normalized_path,
            method=method,
            status_code=status_code,
        )

    async def _process_query_params(self, uow: HTTPXUnitOfWork, endpoint, service, data: Dict[str, Any]):
        raw_path = data.get("path") or "/"
        if "?" not in raw_path:
            return
        _, query = raw_path.split("?", 1)
        for part in query.split("&"):
            if "=" in part:
                name, value = part.split("=", 1)
            else:
                name, value = part, ""
            if not name:
                continue
            await uow.input_parameters.ensure(
                endpoint_id=endpoint.id,
                service_id=service.id,
                name=name,
                location="query",
                example_value=value,
            )

    def _chunks(self, data: List[Any], size: int):
        """Split data into chunks of given size"""
        for i in range(0, len(data), size):
            yield data[i:i + size]
