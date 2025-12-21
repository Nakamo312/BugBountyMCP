"""HTTPX Scan Service - Refactored with DTOs and SOLID principles"""
from typing import AsyncIterator, Dict, Any
import json
import logging

from api.domain.repositories import (
    IHostRepository,
    IIPAddressRepository,
    IHostIPRepository,
    IServiceRepository,
    IEndpointRepository,
    IInputParameterRepository,
)
from api.config import Settings
from api.application.dto import HTTPXScanInputDTO, HTTPXScanOutputDTO
from .base_service import BaseScanService, CommandExecutionMixin, URLParseMixin

logger = logging.getLogger(__name__)


class HTTPXScanService(BaseScanService, CommandExecutionMixin, URLParseMixin):
    """
    Service for executing HTTPX scans and storing results.
    
    Follows SOLID principles:
    - Single Responsibility: Only handles HTTPX scanning
    - Open/Closed: Extensible through inheritance
    - Liskov Substitution: Can be substituted with other scan services
    - Interface Segregation: Uses specific repository interfaces
    - Dependency Inversion: Depends on abstractions (interfaces), not concrete implementations
    """
    
    def __init__(
        self,
        host_repository: IHostRepository,
        ip_repository: IIPAddressRepository,
        host_ip_repository: IHostIPRepository,
        service_repository: IServiceRepository,
        endpoint_repository: IEndpointRepository,
        input_param_repository: IInputParameterRepository,
        settings: Settings
    ):
        super().__init__()
        self.settings = settings
        self.host_repository = host_repository
        self.ip_repository = ip_repository
        self.host_ip_repository = host_ip_repository
        self.service_repository = service_repository
        self.endpoint_repository = endpoint_repository
        self.input_param_repository = input_param_repository

    async def execute(self, input_dto: HTTPXScanInputDTO) -> HTTPXScanOutputDTO:
        """
        Execute HTTPX scan and store results in database.
        
        Args:
            input_dto: Scan input parameters
            
        Returns:
            Scan output with statistics
        """
        self.logger.info(f"Starting HTTPX scan for program {input_dto.program_id}")
        
        scanned_hosts = set()
        endpoints_count = 0

        # Collect all scan results first
        scan_results = []
        async for result in self._execute_scan(
            input_dto.targets,
            timeout=input_dto.timeout
        ):
            host_name = result.get("host") or result.get("input")
            if not host_name:
                continue
            scanned_hosts.add(host_name)
            scan_results.append(result)

        # Bulk insert/update hosts
        if scanned_hosts:
            await self._bulk_upsert_hosts(input_dto.program_id, scanned_hosts)

        # Process each scan result
        for data in scan_results:
            count = await self._process_scan_result(input_dto.program_id, data)
            endpoints_count += count

        self.logger.info(
            f"HTTPX scan completed: {len(scanned_hosts)} hosts, {endpoints_count} endpoints"
        )

        return HTTPXScanOutputDTO(
            scanner="httpx",
            hosts=len(scanned_hosts),
            endpoints=endpoints_count,
        )

    async def _bulk_upsert_hosts(self, program_id, hosts):
        """Bulk insert/update discovered hosts"""
        hosts_data = [
            {
                "program_id": program_id,
                "host": host,
                "in_scope": True,
                "cname": []
            }
            for host in hosts
        ]
        await self.host_repository.bulk_upsert(
            hosts_data,
            conflict_fields=["program_id", "host"],
            update_fields=["in_scope"]
        )

    async def _process_scan_result(self, program_id, data: Dict[str, Any]) -> int:
        """
        Process single HTTPX scan result.
        
        Returns:
            Number of endpoints created
        """
        host_name = data.get("host") or data.get("input")
        
        # Get host from DB
        host_model = await self.host_repository.get_by_fields(
            program_id=program_id,
            host=host_name
        )
        if not host_model:
            return 0

        # Process IP addresses
        ip_model = await self._process_ip_addresses(program_id, host_model.id, data)
        if not ip_model:
            return 0

        # Process service and technologies
        service_model = await self._process_service(ip_model.id, data)

        # Process endpoint
        await self._process_endpoint(host_model.id, service_model.id, data)

        # Update CNAMEs if present
        await self._process_cnames(host_model, data.get("cname", []))

        return 1

    async def _process_ip_addresses(self, program_id, host_id, data):
        """Process IP addresses from scan result"""
        main_ip = data.get("host_ip")
        ip_model = None
        
        if main_ip:
            ip_model, _ = await self.ip_repository.get_or_create(
                program_id=program_id,
                address=main_ip,
                defaults={"in_scope": True}
            )
            await self.host_ip_repository.link(host_id, ip_model.id, source="httpx")

        # Process additional A records
        for extra_ip in data.get("a", []):
            extra_ip_model, _ = await self.ip_repository.get_or_create(
                program_id=program_id,
                address=extra_ip,
                defaults={"in_scope": True}
            )
            await self.host_ip_repository.link(host_id, extra_ip_model.id, source="httpx-dns")

        return ip_model

    async def _process_service(self, ip_id, data):
        """Process service and technologies"""
        technologies = {}
        tech_list = data.get("tech", [])
        if tech_list:
            technologies = {tech: True for tech in tech_list}
        
        return await self.service_repository.get_or_create_with_tech(
            ip_id=ip_id,
            scheme=data.get("scheme", "http"),
            port=int(data.get("port", 80)),
            technologies=technologies
        )

    async def _process_endpoint(self, host_id, service_id, data):
        """Process endpoint and parameters"""
        raw_path = data.get("path", "/")
        path, query_params = self.split_path_and_params(raw_path)
        normalized_path = path.lower()
        method = data.get("method", "GET")

        endpoint_model = await self.endpoint_repository.upsert_with_method(
            host_id=host_id,
            service_id=service_id,
            path=path,
            method=method,
            normalized_path=normalized_path,
            status_code=data.get("status_code", 200),
            title=data.get("title"),
            content_length=data.get("content_length")
        )

        # Create/update query parameters
        if query_params:
            for name, value in query_params.items():
                await self.input_param_repository.upsert(
                    {
                        "endpoint_id": endpoint_model.id,
                        "name": name,
                        "location": "query",
                        "param_type": "string",
                        "reflected": False,
                        "is_array": False,
                        "example_value": value
                    },
                    conflict_fields=["endpoint_id", "location", "name"]
                )

        return endpoint_model

    async def _process_cnames(self, host_model, cnames):
        """Process and merge CNAME records"""
        if not cnames:
            return
        
        existing_cnames = host_model.cname or []
        merged_cnames = list(set(existing_cnames + cnames))
        await self.host_repository.update(host_model.id, {"cname": merged_cnames})

    async def _execute_scan(
        self,
        targets: list,
        timeout: int = 600
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute HTTPX command and yield JSON results.
        
        Args:
            targets: List of target URLs/domains
            timeout: Scan timeout in seconds
            
        Yields:
            Dict with scan results for each URL
        """
        tool_path = self.settings.get_tool_path("httpx")
        command = [
            tool_path,
            "-status-code",
            "-title",
            "-tech-detect",
            "-ip",
            "-cname",
            "-json",
            "-l", "-"  # Read from stdin
        ]

        stdin_input = "\n".join(targets)

        async for line in self.exec_stream(command, stdin=stdin_input, timeout=timeout):
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                self.logger.warning(f"Failed to parse HTTPX output: {line}")
                continue
