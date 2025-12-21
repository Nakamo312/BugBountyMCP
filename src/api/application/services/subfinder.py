"""Subfinder Scan Service - Discovers subdomains and delegates to HTTPX"""
from typing import AsyncIterator, Dict, Any, Iterable, Optional, Union
import json

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

    def __init__(self, httpx_service: HTTPXScanService):
        """
        Initialize SubfinderScanService.
        
        Args:
            httpx_service: HTTPXScanService instance for probing discovered subdomains
        """
        super().__init__()
        self.httpx_service = httpx_service

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
        # Discover subdomains
        subdomains = []
        async for subdomain in self.execute_scan(domain, **kwargs):
            subdomains.append(subdomain)
        
        result = {
            "scanner": self.name,
            "domain": domain,
            "subdomains_found": len(subdomains),
            "subdomains": subdomains,
        }
        
        # Optionally probe discovered subdomains with HTTPX
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
        command = [
            "subfinder",
            "-d", domain,
            "-silent",  # Only output subdomains
        ]
        
        # Add optional sources
        sources = kwargs.get("sources")
        if sources:
            command.extend(["-sources", ",".join(sources)])
        
        # Add recursive option
        if kwargs.get("recursive"):
            command.append("-recursive")
        
        # Add all option (use all sources)
        if kwargs.get("all_sources"):
            command.append("-all")
        
        # Execute and yield results
        async for line in self.exec_stream(
            command,
            timeout=kwargs.get("timeout", 300),
        ):
            subdomain = line.strip()
            if subdomain:
                yield subdomain