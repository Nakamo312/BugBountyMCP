# api/application/services/httpx.py
import json
import logging
from typing import AsyncIterator, Dict, Any, List
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from api.config import Settings
from api.application.dto.scan_dto import HTTPXScanInputDTO, HTTPXScanOutputDTO
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork
from api.domain.models import EndpointModel, HostIPModel, HostModel, IPAddressModel, InputParameterModel, ServiceModel

logger = logging.getLogger(__name__)


class HTTPXScanService:
    
    def __init__(self, uow_factory, settings: Settings):
        self.uow_factory = uow_factory
        self.settings = settings
    
    async def execute(self, input_dto: HTTPXScanInputDTO) -> HTTPXScanOutputDTO:
        logger.info(f"Starting HTTPX scan for program {input_dto.program_id}")
        
        async with self.uow_factory() as uow:
            try:
                scan_results = []
                async for scan_result in self._execute_httpx_scan(input_dto.targets, input_dto.timeout):
                    host_name = scan_result.get("host") or scan_result.get("input")
                    if not host_name:
                        continue
                    scan_results.append((host_name, scan_result))
                
                if not scan_results:
                    logger.warning("No scan results received")
                    return HTTPXScanOutputDTO(
                        scanner="httpx",
                        hosts=0,
                        endpoints=0,
                        services=0
                    )
                
                host_names = {host_name for host_name, _ in scan_results}
                await self._bulk_upsert_hosts(uow, input_dto.program_id, host_names)
                
                endpoints_count = 0
                processed_pairs = set()
                
                for host_name, scan_result in scan_results:
                    result = await self._process_scan_result(
                        uow, input_dto.program_id, host_name, scan_result, processed_pairs
                    )
                    endpoints_count += result
                
                await uow.commit()
                
                logger.info(f"HTTPX scan completed: {len(host_names)} hosts, {endpoints_count} endpoints")
                
                return HTTPXScanOutputDTO(
                    scanner="httpx",
                    hosts=len(host_names),
                    endpoints=endpoints_count,
                    services=len(host_names)
                )
                
            except Exception as e:
                logger.error(f"Scan failed: {e}")
                await uow.rollback()
                raise
    
    async def _bulk_upsert_hosts(self, uow: HTTPXUnitOfWork, program_id: UUID, hosts: set):
        if not hosts:
            return
        
        host_entities = [
            HostModel(
                id=uuid4(),
                program_id=program_id,
                host=host,
                in_scope=True,
                cname=[]
            )
            for host in hosts
        ]
        
        await uow.hosts.bulk_upsert(
            entities=host_entities,
            conflict_fields=["program_id", "host"],
            update_fields=["in_scope"]
        )
        await uow._session.flush()
    
    async def _process_scan_result(
        self, 
        uow: HTTPXUnitOfWork, 
        program_id: UUID, 
        host_name: str,
        data: Dict[str, Any],
        processed_pairs: set
    ) -> int:
        host = await uow.hosts.get_by_fields(
            program_id=program_id,
            host=host_name
        )
        
        if not host:
            logger.error(f"Host {host_name} not found after bulk upsert")
            return 0
        
        main_ip = data.get("host_ip")
        if main_ip:
            pair_key = (host.id, main_ip, "httpx")
            if pair_key in processed_pairs:
                logger.debug(f"Host-IP pair already processed: {host_name} - {main_ip}")
                return 0
            processed_pairs.add(pair_key)
        
        try:
            ip_model = await self._process_ip_addresses(uow, program_id, host.id, data, processed_pairs)
            if not ip_model:
                return 0
            
            service_model = await self._process_service(uow, ip_model.id, data)
            await self._process_endpoint(uow, host.id, service_model.id, data)
            await self._process_cnames(uow, host, data.get("cname", []))
            
            return 1
        except Exception as e:
            logger.error(f"Error processing {host_name}: {e}")
            raise
    
    async def _process_ip_addresses(
        self, 
        uow: HTTPXUnitOfWork,
        program_id: UUID, 
        host_id: UUID, 
        data: Dict[str, Any],
        processed_pairs: set
    ) -> IPAddressModel:
        main_ip = data.get("host_ip")
        ip_model = None
        
        if main_ip:
            pair_key = (host_id, main_ip, "httpx")
            
            if pair_key in processed_pairs:
                existing_ip = await uow.ips.get_by_fields(
                    program_id=program_id,
                    address=main_ip
                )
                return existing_ip
            
            existing_ip = await uow.ips.get_by_fields(
                program_id=program_id,
                address=main_ip
            )
            
            if existing_ip:
                ip_model = existing_ip
            else:
                ip_model = IPAddressModel(
                    id=uuid4(),
                    program_id=program_id,
                    address=main_ip,
                    in_scope=True
                )
                ip_model = await uow.ips.create(ip_model)
            
            existing_link = await uow.host_ips.get_by_fields(
                host_id=host_id,
                ip_id=ip_model.id
            )
            
            if not existing_link:
                host_ip = HostIPModel(
                    id=uuid4(),
                    host_id=host_id,
                    ip_id=ip_model.id,
                    source="httpx"
                )
                await uow.host_ips.create(host_ip)
        
        for extra_ip in data.get("a", []):
            pair_key = (host_id, extra_ip, "httpx-dns")
            if pair_key in processed_pairs:
                continue
            
            processed_pairs.add(pair_key)
            
            existing_extra_ip = await uow.ips.get_by_fields(
                program_id=program_id,
                address=extra_ip
            )
            
            if not existing_extra_ip:
                extra_ip_model = IPAddressModel(
                    id=uuid4(),
                    program_id=program_id,
                    address=extra_ip,
                    in_scope=True
                )
                await uow.ips.create(extra_ip_model)
                ip_id_to_use = extra_ip_model.id
            else:
                ip_id_to_use = existing_extra_ip.id
            
            existing_extra_link = await uow.host_ips.get_by_fields(
                host_id=host_id,
                ip_id=ip_id_to_use
            )
            
            if not existing_extra_link:
                extra_host_ip = HostIPModel(
                    id=uuid4(),
                    host_id=host_id,
                    ip_id=ip_id_to_use,
                    source="httpx-dns"
                )
                await uow.host_ips.create(extra_host_ip)
        
        return ip_model
    
    async def _process_service(
        self, 
        uow: HTTPXUnitOfWork,
        ip_id: UUID, 
        data: Dict[str, Any]
    ) -> ServiceModel:
        technologies = {}
        tech_list = data.get("tech", [])
        if tech_list:
            technologies = {tech: True for tech in tech_list}
        
        scheme = data.get("scheme", "http")
        port = int(data.get("port", 80))

        existing_service = await uow.services.get_by_fields(
            ip_id=ip_id,
            scheme=scheme,
            port=port
        )
        
        if existing_service:
            merged_tech = {**existing_service.technologies, **technologies}
            updated_service = existing_service.copy(update={"technologies": merged_tech})
            return await uow.services.update(existing_service.id, updated_service)
        
        service = ServiceModel(
            id=uuid4(),
            ip_id=ip_id,
            scheme=scheme,
            port=port,
            technologies=technologies
        )
        return await uow.services.create(service)
    
    async def _process_endpoint(
        self, 
        uow: HTTPXUnitOfWork,
        host_id: UUID, 
        service_id: UUID, 
        data: Dict[str, Any]
    ):
        raw_path = data.get("path", "/")
        
        if "?" in raw_path:
            path, query_string = raw_path.split("?", 1)
            query_params = dict(p.split("=") if "=" in p else (p, "") 
                              for p in query_string.split("&"))
        else:
            path = raw_path
            query_params = {}
        
        normalized_path = path.lower()
        method = data.get("method", "GET")
        
        existing_endpoint = await uow.endpoints.get_by_fields(
            host_id=host_id,
            service_id=service_id,
            normalized_path=normalized_path
        )
        
        if existing_endpoint:
            methods = existing_endpoint.methods or []
            if method not in methods:
                methods.append(method)
            
            update_data = {
                "methods": methods,
                "status_code": data.get("status_code", 200)
            }
            updated_endpoint = existing_endpoint.copy(update=update_data)
            endpoint = await uow.endpoints.update(existing_endpoint.id, updated_endpoint)
        else:
            endpoint = EndpointModel(
                id=uuid4(),
                host_id=host_id,
                service_id=service_id,
                path=path,
                normalized_path=normalized_path,
                methods=[method],
                status_code=data.get("status_code", 200)
            )
            endpoint = await uow.endpoints.create(endpoint)
        
        for name, value in query_params.items():
            existing_param = await uow.input_parameters.get_by_fields(
                endpoint_id=endpoint.id,
                location="query",
                name=name
            )
            
            if existing_param:
                updated_param = existing_param.copy(update={"example_value": value})
                await uow.input_parameters.update(existing_param.id, updated_param)
            else:
                param = InputParameterModel(
                    id=uuid4(),
                    endpoint_id=endpoint.id,
                    name=name,
                    location="query",
                    param_type="string",
                    reflected=False,
                    is_array=False,
                    example_value=value
                )
                await uow.input_parameters.create(param)
        
        return endpoint
    
    async def _process_cnames(
        self, 
        uow: HTTPXUnitOfWork,
        host: HostModel, 
        cnames: list
    ):
        if not cnames:
            return
        
        existing_cnames = host.cname or []
        merged_cnames = list(set(existing_cnames + cnames))
        
        updated_host = host.copy(update={"cname": merged_cnames})
        await uow.hosts.update(host.id, updated_host)
    
    async def _execute_httpx_scan(
        self, 
        targets: List[str], 
        timeout: int
    ) -> AsyncIterator[Dict[str, Any]]:
        import asyncio
        
        tool_path = self.settings.get_tool_path("httpx")
        command = [
            tool_path,
            "-json",
            "-silent",
            "-status-code",
            "-tech-detect",
            "-title",
            "-ip",
            "-cdn",
            "-asn",
            "-follow-redirects",
            "-filter-duplicates",
            "-s"
        ]
        
        if isinstance(targets, str):
            command += ["-u", targets]
            stdin_input = None
        else:
            stdin_input = "\n".join(targets)
        
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE if stdin_input else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            if stdin_input:
                process.stdin.write(stdin_input.encode())
                await process.stdin.drain()
                process.stdin.close()
            
            async for line in process.stdout:
                try:
                    yield json.loads(line.decode().strip())
                except json.JSONDecodeError:
                    continue
            
            await process.wait()
            
        except Exception as e:
            logger.error(f"HTTPX scan execution error: {e}")
            raise
        finally:
            if process and process.returncode is None:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except (asyncio.TimeoutError, ProcessLookupError):
                    pass