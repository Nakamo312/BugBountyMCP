import re
import logging
from typing import Dict, Any, List
from uuid import UUID
from urllib.parse import urlparse, parse_qs

from api.config import Settings
from api.domain.models import ScopeRuleModel
from api.domain.enums import RuleType
from api.infrastructure.unit_of_work.interfaces.linkfinder import LinkFinderUnitOfWork
from api.infrastructure.normalization.path_normalizer import PathNormalizer
from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class LinkFinderResultIngestor:
    """
    Handles ingestion of LinkFinder results with scope validation.
    Only ingests URLs that match program scope rules.
    """

    def __init__(self, uow: LinkFinderUnitOfWork, settings: Settings):
        self.uow = uow
        self.settings = settings

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]) -> IngestResult:
        """
        Ingest LinkFinder results with scope validation.

        Args:
            program_id: Target program ID
            results: List of LinkFinder results containing source_js, urls, host
        """
        async with self.uow:
            try:
                scope_rules = await self.uow.scope_rules.find_by_program(program_id)
                in_scope_count = 0
                out_of_scope_count = 0

                for result in results:
                    urls = result.get("urls", [])
                    host_name = result.get("host")

                    if not urls or not host_name:
                        continue

                    logger.debug(
                        f"Processing LinkFinder result: program={program_id} "
                        f"source={result.get('source_js')} urls={len(urls)}"
                    )

                    host = await self.uow.hosts.ensure(program_id=program_id, host=host_name)

                    host_ip_records = await self.uow.host_ips.find_many(filters={"host_id": host.id}, limit=1)
                    if not host_ip_records:
                        logger.debug(f"No IP found for host {host_name}, skipping")
                        continue

                    ip = await self.uow.ips.get(host_ip_records[0].ip_id)
                    if not ip:
                        continue

                    for url in urls:
                        if self._is_in_scope(url, scope_rules):
                            await self._ingest_url(url, host, ip)
                            in_scope_count += 1
                        else:
                            out_of_scope_count += 1

                await self.uow.commit()

                logger.info(
                    f"LinkFinder ingestion completed: program={program_id} "
                    f"in_scope={in_scope_count} out_of_scope={out_of_scope_count}"
                )

                return IngestResult()

            except Exception as e:
                logger.error(f"LinkFinder ingestion failed: program={program_id} error={e}")
                await self.uow.rollback()
                raise

    async def _ingest_url(self, url: str, host, ip):
        """Ingest single URL as endpoint"""
        parsed = urlparse(url)
        scheme = parsed.scheme or "https"
        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path or "/"
        query_string = parsed.query

        service = await self.uow.services.ensure(
            ip_id=ip.id,
            scheme=scheme,
            port=port,
            technologies={}
        )

        normalized_path = PathNormalizer.normalize_path(url)

        endpoint = await self.uow.endpoints.ensure(
            host_id=host.id,
            service_id=service.id,
            path=path,
            normalized_path=normalized_path,
            method="GET",
            status_code=None,
        )

        if query_string:
            params = parse_qs(query_string, keep_blank_values=True)
            for name, values in params.items():
                if not name:
                    continue
                example_value = values[0] if values else ""
                await self.uow.input_parameters.ensure(
                    endpoint_id=endpoint.id,
                    service_id=service.id,
                    name=name,
                    location="query",
                    example_value=example_value,
                )

    def _is_in_scope(self, url: str, scope_rules: list[ScopeRuleModel]) -> bool:
        """
        Check if URL matches any scope rule.

        Args:
            url: URL to check
            scope_rules: List of program scope rules

        Returns:
            True if URL is in scope
        """
        if not scope_rules:
            return True

        parsed = urlparse(url)
        domain = parsed.hostname

        if not domain:
            return False

        for rule in scope_rules:
            if rule.rule_type == RuleType.DOMAIN:
                if domain == rule.pattern or domain.endswith(f".{rule.pattern}"):
                    return True

            elif rule.rule_type == RuleType.REGEX:
                if re.match(rule.pattern, url):
                    return True

        return False
