"""Subfinder Scan Service - Refactored with DTOs"""
from typing import AsyncIterator
import logging

from api.config import Settings
from api.application.dto import (
    SubfinderScanInputDTO,
    SubfinderScanOutputDTO,
    HTTPXScanInputDTO,
)
from .base_service import BaseScanService, CommandExecutionMixin
from .httpx import HTTPXScanService

logger = logging.getLogger(__name__)


class SubfinderScanService(BaseScanService, CommandExecutionMixin):
    """
    Service for executing Subfinder scans.
    
    Depends on HTTPXScanService for probing discovered subdomains.
    """
    
    def __init__(self, httpx_service: HTTPXScanService, settings: Settings):
        super().__init__()
        self.httpx_service = httpx_service
        self.settings = settings

    async def execute(self, input_dto: SubfinderScanInputDTO) -> SubfinderScanOutputDTO:
        """
        Execute Subfinder scan to discover subdomains.
        
        Args:
            input_dto: Scan input parameters
            
        Returns:
            Scan output with discovered subdomains and optional probe results
        """
        self.logger.info(f"Starting Subfinder scan for domain: {input_dto.domain}")
        
        # Discover subdomains
        subdomains = []
        async for subdomain in self.execute_scan(input_dto.domain, input_dto.timeout):
            subdomains.append(subdomain)
        
        self.logger.info(f"Discovered {len(subdomains)} subdomains for {input_dto.domain}")
        
        # Optionally probe with HTTPX
        httpx_results = None
        if input_dto.probe and subdomains:
            self.logger.info(f"Probing {len(subdomains)} subdomains with HTTPX")
            httpx_input = HTTPXScanInputDTO(
                program_id=input_dto.program_id,
                targets=subdomains,
                timeout=input_dto.timeout
            )
            httpx_results = await self.httpx_service.execute(httpx_input)
        
        return SubfinderScanOutputDTO(
            scanner="subfinder",
            domain=input_dto.domain,
            subdomains=len(subdomains),
            probed=input_dto.probe,
            httpx_results=httpx_results
        )

    async def execute_scan(
        self,
        domain: str,
        timeout: int = 600
    ) -> AsyncIterator[str]:
        """
        Execute Subfinder command and yield discovered subdomains.
        
        Args:
            domain: Target domain
            timeout: Scan timeout in seconds
            
        Yields:
            Discovered subdomains
        """
        tool_path = self.settings.get_tool_path("subfinder")
        command = [
            tool_path,
            "-d", domain,
            "-silent",
            "-all"
        ]

        async for line in self.exec_stream(command, timeout=timeout):
            if line.strip():
                yield line.strip()
