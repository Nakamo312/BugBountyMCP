"""Subfinder Scan Service - Discovers subdomains and delegates to HTTPX"""
from typing import AsyncIterator, Dict, Any, Iterable, Optional, Union
import json

from api.config import Settings, settings

from .base_service import BaseScanService, CommandExecutionMixin
from .httpx import HTTPXScanService


class SubfinderScanService(BaseScanService, CommandExecutionMixin):
    """
    Service for executing Subfinder scans.
    
    Discovers subdomains and delegates HTTP probing to HTTPXScanService.
    This demonstrates service composition - SubfinderScanService depends
    only on HTTPXScanService, which handles all repository interactions.
    """
    
    name = "subfinder"
    category = "subdomain"

    def __init__(self, httpx_service: HTTPXScanService, settings: Settings):
        """
        Initialize SubfinderScanService.
        
        Args:
            httpx_service: HTTPXScanService instance for probing discovered subdomains
        """
        super().__init__()
        self.httpx_service = httpx_service
        self.settings = settings

    async def execute(
        self,
        program_id: str,
        domain: str,
        probe: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute Subfinder scan to discover subdomains.
        
        Args:
            program_id: Program UUID
            domain: Target domain to scan
            probe: If True, probe discovered subdomains with HTTPX (default: True)
            **kwargs: Additional options (timeout, sources, etc.)
            
        Returns:
            Dict with scan results:
                - scanner: "subfinder"
                - domain: target domain
                - subdomains_found: count of discovered subdomains
                - subdomains_probed: count of probed subdomains (if probe=True)
                - httpx_results: HTTPX results (if probe=True)
        """
        subdomains = []
        async for subdomain in self.execute_scan(domain, **kwargs):
            subdomains.append(subdomain)
        
        result = {
            "scanner": self.name,
            "domain": domain,
            "subdomains_found": len(subdomains),
            "subdomains": subdomains,
        }
        
        if probe and subdomains:
            self.logger.info(
                f"Probing {len(subdomains)} discovered subdomains with HTTPX"
            )
            
            httpx_results = await self.httpx_service.execute(
                program_id=program_id,
                targets=subdomains,
                timeout=kwargs.get("httpx_timeout", 300)
            )
            
            result["subdomains_probed"] = httpx_results["hosts"]
            result["httpx_results"] = httpx_results
        
        return result

    async def execute_scan(
        self,
        domain: str,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Execute Subfinder command and yield discovered subdomains.
        
        Args:
            domain: Target domain
            **kwargs: Additional options:
                - sources: List of sources to use (e.g., ["virustotal", "crtsh"])
                - timeout: Timeout in seconds
                - recursive: Enable recursive subdomain discovery
                - silent: Silent mode (less verbose)
                
        Yields:
            Discovered subdomain strings
        """
        tool_path = self.settings.get_tool_path("subfinder")
        command = [
            tool_path,
            "-d", domain,
            "-silent",  
        ]
        
        sources = kwargs.get("sources")
        if sources:
            command.extend(["-sources", ",".join(sources)])
        
        if kwargs.get("recursive"):
            command.append("-recursive")
        
        if kwargs.get("all_sources"):
            command.append("-all")
        
        async for line in self.exec_stream(
            command,
            timeout=kwargs.get("timeout", 300),
        ):
            subdomain = line.strip()
            if subdomain:
                yield subdomain