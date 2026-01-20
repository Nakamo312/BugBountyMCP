"""Service for working with hosts, endpoints, parameters and headers"""

from typing import List, Optional
from uuid import UUID

from api.application.dto.host import (
    HostResponseDTO,
    EndpointResponseDTO,
    InputParameterResponseDTO,
    HeaderResponseDTO,
    HostWithEndpointsDTO,
    EndpointWithDetailsDTO,
    HostsListResponseDTO
)
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork


class HostService:
    """Service for querying hosts and related data"""
    
    def __init__(self, uow: HTTPXUnitOfWork):
        self.uow = uow
    
    async def get_hosts_by_program(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        in_scope: Optional[bool] = None
    ) -> HostsListResponseDTO:
        """Get hosts by program_id with pagination"""
        async with self.uow as uow:
            hosts = await uow.hosts.find_by_program(
                program_id=program_id,
                limit=limit,
                offset=offset,
                in_scope=in_scope
            )
            # Count total with same filters
            filters = {"program_id": program_id}
            if in_scope is not None:
                filters["in_scope"] = in_scope
            total = await uow.hosts.count(filters=filters)
            
            return HostsListResponseDTO(
                hosts=[
                    HostResponseDTO(
                        id=host.id,
                        program_id=host.program_id,
                        host=host.host,
                        in_scope=host.in_scope,
                        cname=host.cname
                    ) for host in hosts
                ],
                total=total,
                limit=limit,
                offset=offset
            )
    
    async def get_host_with_endpoints(
        self,
        host_id: UUID
    ) -> Optional[HostWithEndpointsDTO]:
        """Get host with all endpoints"""
        async with self.uow as uow:
            host = await uow.hosts.get(host_id)
            if not host:
                return None
            
            endpoints = await uow.endpoints.find_by_host(host_id, limit=1000)
            
            return HostWithEndpointsDTO(
                host=HostResponseDTO(
                    id=host.id,
                    program_id=host.program_id,
                    host=host.host,
                    in_scope=host.in_scope,
                    cname=host.cname
                ),
                endpoints=[
                    EndpointResponseDTO(
                        id=ep.id,
                        host_id=ep.host_id,
                        service_id=ep.service_id,
                        path=ep.path,
                        normalized_path=ep.normalized_path,
                        methods=ep.methods,
                        status_code=ep.status_code
                    ) for ep in endpoints
                ]
            )
    
    async def get_endpoints_by_host(
        self,
        host_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[EndpointResponseDTO]:
        """Get endpoints by host_id"""
        async with self.uow as uow:
            endpoints = await uow.endpoints.find_by_host(
                host_id=host_id,
                limit=limit,
                offset=offset
            )
            
            return [
                EndpointResponseDTO(
                    id=ep.id,
                    host_id=ep.host_id,
                    service_id=ep.service_id,
                    path=ep.path,
                    normalized_path=ep.normalized_path,
                    methods=ep.methods,
                    status_code=ep.status_code
                ) for ep in endpoints
            ]
    
    async def get_endpoint_with_details(
        self,
        endpoint_id: UUID
    ) -> Optional[EndpointWithDetailsDTO]:
        """Get endpoint with parameters and headers"""
        async with self.uow as uow:
            endpoint = await uow.endpoints.get(endpoint_id)
            if not endpoint:
                return None
            
            parameters = await uow.input_parameters.find_by_endpoint(
                endpoint_id=endpoint_id,
                limit=1000
            )
            headers = await uow.headers.find_by_endpoint(
                endpoint_id=endpoint_id,
                limit=1000
            )
            
            return EndpointWithDetailsDTO(
                endpoint=EndpointResponseDTO(
                    id=endpoint.id,
                    host_id=endpoint.host_id,
                    service_id=endpoint.service_id,
                    path=endpoint.path,
                    normalized_path=endpoint.normalized_path,
                    methods=endpoint.methods,
                    status_code=endpoint.status_code
                ),
                parameters=[
                    InputParameterResponseDTO(
                        id=param.id,
                        endpoint_id=param.endpoint_id,
                        service_id=param.service_id,
                        name=param.name,
                        location=param.location,
                        param_type=param.param_type,
                        reflected=param.reflected,
                        is_array=param.is_array,
                        example_value=param.example_value
                    ) for param in parameters
                ],
                headers=[
                    HeaderResponseDTO(
                        id=header.id,
                        endpoint_id=header.endpoint_id,
                        name=header.name,
                        value=header.value
                    ) for header in headers
                ]
            )
    
    async def get_parameters_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[InputParameterResponseDTO]:
        """Get input parameters by endpoint_id"""
        async with self.uow as uow:
            parameters = await uow.input_parameters.find_by_endpoint(
                endpoint_id=endpoint_id,
                limit=limit,
                offset=offset
            )
            
            return [
                InputParameterResponseDTO(
                    id=param.id,
                    endpoint_id=param.endpoint_id,
                    service_id=param.service_id,
                    name=param.name,
                    location=param.location,
                    param_type=param.param_type,
                    reflected=param.reflected,
                    is_array=param.is_array,
                    example_value=param.example_value
                ) for param in parameters
            ]
    
    async def get_headers_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[HeaderResponseDTO]:
        """Get headers by endpoint_id"""
        async with self.uow as uow:
            headers = await uow.headers.find_by_endpoint(
                endpoint_id=endpoint_id,
                limit=limit,
                offset=offset
            )
            
            return [
                HeaderResponseDTO(
                    id=header.id,
                    endpoint_id=header.endpoint_id,
                    name=header.name,
                    value=header.value
                ) for header in headers
            ]
