from typing import List, Dict, Any, Set
from uuid import UUID
import logging

from api.config import Settings
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork
from api.infrastructure.normalization.path_normalizer import PathNormalizer
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor

logger = logging.getLogger(__name__)


class HTTPXResultIngestor(BaseResultIngestor):
    """
    Handles batch ingestion of HTTPX scan results into domain entities.
    Uses savepoints to allow partial success without rolling back entire transaction.
    Publishes events for newly discovered hosts with active services.
    Detects live JS files and publishes them for LinkFinder analysis.
    """

    def __init__(self, uow: HTTPXUnitOfWork, bus: EventBus, settings: Settings):
        super().__init__(uow, settings.HTTPX_INGESTOR_BATCH_SIZE)
        self.bus = bus
        self.settings = settings
        self._new_hosts: Set[str] = set()
        self._seen_hosts: Set[str] = set()
        self._js_files: List[str] = []

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]):
        self._new_hosts = set()
        self._seen_hosts = set()
        self._js_files = []

        await super().ingest(program_id, results)

        if self._new_hosts:
            await self._publish_new_hosts(program_id, list(self._new_hosts))

        if self._js_files:
            await self._publish_js_files(program_id, self._js_files)

    async def _process_batch(self, uow: HTTPXUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]]):
        """Process a batch of HTTPX results and collect live JS files"""
        for data in batch:
            host_url, is_new = await self._process_record(uow, program_id, data, self._seen_hosts)
            if host_url and is_new:
                self._new_hosts.add(host_url)

            url = data.get("url")
            status_code = data.get("status_code")
            if url and status_code == 200 and self._is_js_file(url):
                self._js_files.append(url)

    async def _process_record(
        self,
        uow: HTTPXUnitOfWork,
        program_id: UUID,
        data: Dict[str, Any],
        seen_hosts: Set[str]
    ) -> tuple[str | None, bool]:
        host_name = data.get("host") or data.get("input")
        if not host_name:
            return None, False

        is_new_host = host_name not in seen_hosts
        if is_new_host:
            existing_host = await uow.hosts.get_by_fields(program_id=program_id, host=host_name)
            is_new_host = existing_host is None
            seen_hosts.add(host_name)

        host = await self._ensure_host(uow, program_id, data)
        if not host:
            return None, False

        ip = await self._ensure_ip(uow, program_id, host, data)
        if not ip:
            return None, False

        service = await self._ensure_service(uow, ip, data)
        endpoint = await self._ensure_endpoint(uow, host, service, data)
        await self._process_query_params(uow, endpoint, service, data)

        status_code = data.get("status_code")
        if status_code and 200 <= status_code < 400 and is_new_host:
            scheme = data.get("scheme", "http")
            port = int(data.get("port", 80 if scheme == "http" else 443))

            if port in (80, 443):
                return f"{scheme}://{host_name}", True
            else:
                return f"{scheme}://{host_name}:{port}", True

        return None, False

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
        clean_path = raw_path.split("?")[0] if "?" in raw_path else raw_path

        scheme = data.get("scheme", "http")
        host_name = data.get("host") or data.get("input")
        full_url = f"{scheme}://{host_name}{clean_path}"
        normalized_path = PathNormalizer.normalize_path(full_url)

        method = data.get("method", "GET")
        status_code = data.get("status_code")
        return await uow.endpoints.ensure(
            host_id=host.id,
            service_id=service.id,
            path=clean_path,
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

    async def _publish_new_hosts(self, program_id: UUID, hosts: List[str]):
        """Publish newly discovered active hosts to EventBus for Katana crawling"""
        for batch in self._chunks(hosts, self.settings.HTTPX_NEW_HOST_BATCH_SIZE):
            await self.bus.publish(
                EventType.HOST_DISCOVERED,
                {
                    "program_id": str(program_id),
                    "hosts": batch,
                },
            )
            logger.info(f"Published new hosts batch: program={program_id} count={len(batch)}")

    def _is_js_file(self, url: str) -> bool:
        """Check if URL points to a JavaScript file"""
        url_lower = url.lower()
        return url_lower.endswith('.js') or '.js?' in url_lower

    async def _publish_js_files(self, program_id: UUID, js_files: List[str]):
        """Publish discovered live JS files for LinkFinder analysis"""
        await self.bus.publish(
            EventType.JS_FILES_DISCOVERED,
            {
                "program_id": str(program_id),
                "js_files": js_files,
            },
        )
        logger.info(f"Published JS files for LinkFinder: program={program_id} count={len(js_files)}")
