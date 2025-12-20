"""Subdomain enumeration service"""
from typing import AsyncIterator, Dict, Any
from uuid import UUID
import re

from .base_service import BaseScanService, ScanResult
from ...infrastructure.repositories import HostRepository


class SubdomainScanService(BaseScanService):
    """Subdomain enumeration using subfinder"""
    
    name = "subfinder"
    category = "subdomain"
    
    def __init__(self, host_repository: HostRepository):
        super().__init__(host_repository)
        self.host_repository = host_repository
    
    async def execute_scan(self, target: str, **kwargs) -> AsyncIterator[str]:
        """
        Execute subfinder scan
        
        Args:
            target: Domain to enumerate
            **kwargs: silent (bool), timeout (int), resolvers (str)
        """
        command = ["subfinder", "-d", target]
        
        if kwargs.get("silent", True):
            command.append("-silent")
        
        if kwargs.get("all", False):
            command.append("-all")
        
        if resolvers := kwargs.get("resolvers"):
            command.extend(["-r", resolvers])
        
        timeout = kwargs.get("timeout", 600)
        
        async for line in self._exec_stream(command, timeout=timeout):
            if line and self._is_valid_domain(line):
                yield line
    
    async def parse_and_save(self, program_id: str, target: str, **kwargs) -> Dict[str, Any]:
        """
        Execute subfinder scan and save results to database
        
        Args:
            program_id: Program UUID
            target: Domain to scan
            **kwargs: Scanner parameters
            
        Returns:
            Summary: total found, new, existing
        """
        program_uuid = UUID(program_id)
        found_count = 0
        new_count = 0
        existing_count = 0
        
        subdomains = []
        
        async for subdomain in self.execute_scan(target, **kwargs):
            found_count += 1
            subdomains.append(subdomain)
        
        # Bulk save to database with deduplication
        result = await self.host_repository.bulk_upsert_hosts(
            program_id=program_uuid,
            hosts=subdomains,
            in_scope=True
        )
        
        new_count = result.get("created", 0)
        existing_count = result.get("existing", 0)
        
        return {
            "scanner": self.name,
            "target": target,
            "total_found": found_count,
            "new": new_count,
            "existing": existing_count,
            "subdomains": subdomains
        }
    
    @staticmethod
    def _is_valid_domain(domain: str) -> bool:
        """Validate domain format"""
        pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        return bool(re.match(pattern, domain))
