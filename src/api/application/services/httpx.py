"""HTTPX Scan Service - Updated to use new repository methods"""
from typing import AsyncIterator, Dict, Any, Iterable, Optional, Union
from uuid import UUID
import json

from api.infrastructure.repositories.host import HostRepository
from api.infrastructure.repositories.ip_address import IPAddressRepository
from api.infrastructure.repositories.host_ip import HostIPRepository
from api.infrastructure.repositories.service import ServiceRepository
from api.infrastructure.repositories.endpoint import EndpointRepository
from api.infrastructure.repositories.input_parameters import InputParameterRepository
from .base_service import BaseScanService, CommandExecutionMixin, URLParseMixin


class HTTPXScanService(BaseScanService, CommandExecutionMixin, URLParseMixin):
    """Service for executing HTTPX scans and storing results"""
    
    name = "httpx"
    category = "http"

    def __init__(
        self,
        host_repository: HostRepository,
        ip_repository: IPAddressRepository,
        host_ip_repository: HostIPRepository,
        service_repository: ServiceRepository,
        endpoint_repository: EndpointRepository,
        input_param_repository: Optional[InputParameterRepository] = None,
    ):
        super().__init__()
        self.host_repository = host_repository
        self.ip_repository = ip_repository
        self.host_ip_repository = host_ip_repository
        self.service_repository = service_repository
        self.endpoint_repository = endpoint_repository
        self.input_param_repository = input_param_repository

    async def execute(
        self,
        program_id: str,
        targets: Union[str, Iterable[str]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute HTTPX scan and store results in database.
        
        Uses new repository methods:
        - get_or_create for hosts and IPs
        - link for host-IP relationships
        - get_or_create_with_tech for services (auto-merges technologies)
        - upsert_with_method for endpoints (auto-merges methods)
        - upsert for parameters (deduplication)
        """
        program_uuid = UUID(program_id)
        scanned_hosts = set()
        endpoints_count = 0

        scan_results = []
        async for result in self.execute_scan(targets, **kwargs):
            host_name = result.get("host") or result.get("input")
            if not host_name:
                continue
            scanned_hosts.add(host_name)
            scan_results.append(result)

        if scanned_hosts:
            hosts_data = [
                {
                    "program_id": program_uuid,
                    "host": host,
                    "in_scope": True,
                    "cname": []  
                }
                for host in scanned_hosts
            ]
            await self.host_repository.bulk_upsert(
                hosts_data,
                conflict_fields=["program_id", "host"],
                update_fields=["in_scope"]
            )

        # Process each scan result
        for data in scan_results:
            host_name = data.get("host") or data.get("input")
            
            host_model = await self.host_repository.find_by_host(program_uuid, host_name)
            if not host_model:
                continue

            main_ip = data.get("host_ip")
            ip_model = None
            if main_ip:
                ip_model, _ = await self.ip_repository.get_or_create(
                    program_id=program_uuid,
                    address=main_ip,
                    defaults={"in_scope": True}
                )
                await self.host_ip_repository.link(
                    host_model.id, 
                    ip_model.id, 
                    source="httpx"
                )

            for extra_ip in data.get("a", []):
                extra_ip_model, _ = await self.ip_repository.get_or_create(
                    program_id=program_uuid,
                    address=extra_ip,
                    defaults={"in_scope": True}
                )
                await self.host_ip_repository.link(
                    host_model.id, 
                    extra_ip_model.id, 
                    source="httpx-dns"
                )
            if not ip_model:
                continue

            technologies = {}
            tech_list = data.get("tech", [])
            if tech_list:
                technologies = {tech: True for tech in tech_list}
            
            service_model = await self.service_repository.get_or_create_with_tech(
                ip_id=ip_model.id,
                scheme=data.get("scheme", "http"),
                port=int(data.get("port", 80)),
                technologies=technologies
            )

            raw_path = data.get("path", "/")
            path, query_params = self.split_path_and_params(raw_path)
            
            normalized_path = path.lower()

            method = data.get("method", "GET")
            endpoint_model = await self.endpoint_repository.upsert_with_method(
                host_id=host_model.id,
                service_id=service_model.id,
                path=path,
                method=method,
                normalized_path=normalized_path,
                status_code=data.get("status_code", 200)
            )
            endpoints_count += 1

            # Create/update query parameters
            if query_params and self.input_param_repository:
                for name, value in query_params.items():
                    # Upsert parameter (deduplication by endpoint_id + location + name)
                    await self.input_param_repository.upsert(
                        {
                            "endpoint_id": endpoint_model.id,
                            "name": name,
                            "location": "query",
                            "param_type": "string",  # Default type
                            "reflected": False,
                            "is_array": False
                        },
                        conflict_fields=["endpoint_id", "location", "name"]
                    )

            # Update CNAMEs if present
            cnames = data.get("cname", [])
            if cnames:
                # Merge with existing cnames
                existing_cnames = host_model.cname or []
                merged_cnames = list(set(existing_cnames + cnames))
                await self.host_repository.update(
                    host_model.id, 
                    {"cname": merged_cnames}
                )

        return {
            "scanner": self.name,
            "hosts": len(scanned_hosts),
            "endpoints": endpoints_count,
        }

    async def execute_scan(
        self,
        targets: Union[str, Iterable[str]],
        **kwargs
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute HTTPX command and yield JSON results.
        
        Args:
            targets: Single target URL/domain or iterable of targets
            **kwargs: Additional options (timeout, etc.)
            
        Yields:
            Dict with scan results for each URL
        """
        command = [
            "httpx",
            "-status-code",
            "-title",
            "-tech-detect",
            "-ip",
            "-cname",
            "-json",
        ]

        stdin_input = None
        if isinstance(targets, str):
            command += ["-u", targets]
        else:
            command += ["-l", "-"]
            stdin_input = "\n".join(targets)

        async for line in self.exec_stream(
            command,
            stdin=stdin_input,
            timeout=kwargs.get("timeout", 600),
        ):
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue