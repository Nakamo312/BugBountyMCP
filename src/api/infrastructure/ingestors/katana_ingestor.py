from typing import List, Dict, Any
from uuid import UUID
from urllib.parse import urlparse, parse_qs
import logging

from api.config import Settings
from api.domain.models import ScopeRuleModel
from api.infrastructure.unit_of_work.interfaces.katana import KatanaUnitOfWork
from api.infrastructure.normalization.path_normalizer import PathNormalizer
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.application.utils.scope_checker import ScopeChecker

logger = logging.getLogger(__name__)


class KatanaResultIngestor(BaseResultIngestor):
    """
    Handles batch ingestion of Katana crawl results into domain entities.
    Uses savepoints to allow partial success without rolling back entire transaction.
    Returns JS files discovered during crawling.
    """

    def __init__(self, uow: KatanaUnitOfWork, settings: Settings):
        super().__init__(uow, settings.KATANA_INGESTOR_BATCH_SIZE)
        self._js_files = []
        self._scope_rules: List[ScopeRuleModel] = []

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]) -> IngestResult:
        """
        Ingest Katana results and return discovered JS files.

        Args:
            program_id: Program UUID
            results: List of Katana JSON results

        Returns:
            IngestResult with js_files list
        """
        self._js_files = []

        async with self.uow as uow:
            self._scope_rules = await uow.scope_rules.find_by_program(program_id)

        await super().ingest(program_id, results)

        return IngestResult(js_files=list(set(self._js_files)))

    async def _process_batch(self, uow: KatanaUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]]):
        """Process a batch of Katana results and collect JS files"""
        for data in batch:
            await self._process_record(uow, program_id, data)

            endpoint_url = data.get("request", {}).get("endpoint")
            if endpoint_url and self._is_js_file(endpoint_url):
                self._js_files.append(endpoint_url)

    async def _process_record(
        self,
        uow: KatanaUnitOfWork,
        program_id: UUID,
        data: Dict[str, Any]
    ):
        request = data.get("request", {})
        response = data.get("response", {})

        endpoint_url = request.get("endpoint")
        if not endpoint_url:
            return

        parsed = urlparse(endpoint_url)
        host_name = parsed.hostname
        if not host_name:
            return

        if not ScopeChecker.is_in_scope(host_name, self._scope_rules):
            logger.info(f"Out-of-scope host: {host_name} program={program_id}")
            return

        scheme = parsed.scheme or "http"
        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path or "/"
        query_string = parsed.query

        host = await uow.hosts.ensure(program_id=program_id, host=host_name)

        host_ip_records = await uow.host_ips.find_many(filters={"host_id": host.id}, limit=1)
        if not host_ip_records:
            return
        ip = await uow.ips.get(host_ip_records[0].ip_id)
        if not ip:
            return

        service = await uow.services.get_by_fields(ip_id=ip.id, scheme=scheme, port=port)
        if not service:
            return

        endpoint = await self._ensure_endpoint(uow, host, service, request, response, path)

        await self._process_query_params(uow, endpoint, service, query_string)
        await self._process_body_params(uow, endpoint, request)
        await self._process_headers(uow, endpoint, response)

    async def _ensure_endpoint(
        self,
        uow: KatanaUnitOfWork,
        host,
        service,
        request: Dict[str, Any],
        response: Dict[str, Any],
        path: str
    ):
        endpoint_url = request.get("endpoint")
        normalized_path = PathNormalizer.normalize_path(endpoint_url)

        method = request.get("method", "GET")
        status_code = response.get("status_code")

        return await uow.endpoints.ensure(
            host_id=host.id,
            service_id=service.id,
            path=path,
            normalized_path=normalized_path,
            method=method,
            status_code=status_code,
        )

    async def _process_query_params(
        self,
        uow: KatanaUnitOfWork,
        endpoint,
        service,
        query_string: str
    ):
        if not query_string:
            return

        params = parse_qs(query_string, keep_blank_values=True)
        for name, values in params.items():
            if not name:
                continue
            example_value = values[0] if values else ""
            await uow.input_parameters.ensure(
                endpoint_id=endpoint.id,
                service_id=service.id,
                name=name,
                location="query",
                example_value=example_value,
            )

    async def _process_body_params(
        self,
        uow: KatanaUnitOfWork,
        endpoint,
        request: Dict[str, Any]
    ):
        body = request.get("body")
        if not body:
            return

        import hashlib
        body_hash = hashlib.sha256(body.encode()).hexdigest()

        await uow.raw_bodies.ensure(
            endpoint_id=endpoint.id,
            body_content=body,
            body_hash=body_hash,
        )

    async def _process_headers(
        self,
        uow: KatanaUnitOfWork,
        endpoint,
        response: Dict[str, Any]
    ):
        headers = response.get("headers", {})
        if not headers:
            return

        for name, value in headers.items():
            if not name:
                continue
            await uow.headers.ensure(
                endpoint_id=endpoint.id,
                name=name.lower(),
                value=str(value),
            )

    def _is_js_file(self, url: str) -> bool:
        """Check if URL points to a JavaScript file"""
        url_lower = url.lower()
        return url_lower.endswith('.js') or '.js?' in url_lower
