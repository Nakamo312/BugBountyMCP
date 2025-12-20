"""URL discovery service (GAU/waybackurls)"""
from typing import AsyncIterator, Dict, Any, List
from uuid import UUID
from urllib.parse import urlparse

from .base_service import BaseScanService
from ...infrastructure.repositories import EndpointRepository, ServiceRepository, HostRepository


class URLDiscoveryService(BaseScanService):
    """URL discovery using gau, waybackurls, etc."""
    
    name = "gau"
    category = "url_discovery"
    
    def __init__(
        self, 
        endpoint_repository: EndpointRepository,
        service_repository: ServiceRepository,
        host_repository: HostRepository
    ):
        super().__init__(endpoint_repository)
        self.endpoint_repository = endpoint_repository
        self.service_repository = service_repository
        self.host_repository = host_repository
    
    async def execute_scan(self, target: str, **kwargs) -> AsyncIterator[str]:
        """
        Execute gau scan
        
        Args:
            target: Domain to scan
            **kwargs: providers (list), blacklist (list), threads (int)
        """
        command = ["gau", target]
        
        if providers := kwargs.get("providers"):
            command.extend(["--providers", ",".join(providers)])
        
        if blacklist := kwargs.get("blacklist"):
            command.extend(["--blacklist", ",".join(blacklist)])
        
        if threads := kwargs.get("threads"):
            command.extend(["--threads", str(threads)])
        
        if kwargs.get("subs", False):
            command.append("--subs")
        
        timeout = kwargs.get("timeout", 600)
        
        async for line in self._exec_stream(command, timeout=timeout):
            if line and self._is_valid_url(line):
                yield line
    
    async def parse_and_save(self, program_id: str, target: str, **kwargs) -> Dict[str, Any]:
        """
        Execute URL discovery and save endpoints to database
        
        Args:
            program_id: Program UUID
            target: Domain to scan
            **kwargs: Scanner parameters
            
        Returns:
            Summary with statistics
        """
        program_uuid = UUID(program_id)
        found_count = 0
        
        endpoints_data = []
        
        async for url in self.execute_scan(target, **kwargs):
            found_count += 1
            parsed = self._parse_url(url)
            if parsed:
                endpoints_data.append(parsed)
        
        # Save endpoints with deduplication
        result = await self.endpoint_repository.bulk_upsert_endpoints(
            program_id=program_uuid,
            endpoints=endpoints_data
        )
        
        return {
            "scanner": self.name,
            "target": target,
            "total_found": found_count,
            "new_endpoints": result.get("created", 0),
            "existing_endpoints": result.get("existing", 0)
        }
    
    def _parse_url(self, url: str) -> Dict[str, Any]:
        """Parse URL into components"""
        parsed = urlparse(url)
        return {
            "url": url,
            "scheme": parsed.scheme,
            "host": parsed.netloc,
            "port": parsed.port or (443 if parsed.scheme == "https" else 80),
            "path": parsed.path or "/",
            "query": parsed.query,
            "method": "GET"
        }
    
    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Validate URL format"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
