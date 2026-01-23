"""Service for working with hosts, endpoints, parameters and headers"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import text

from api.application.dto.host import (
    HostResponseDTO,
    EndpointResponseDTO,
    InputParameterResponseDTO,
    HeaderResponseDTO,
    RawBodyResponseDTO,
    HostWithEndpointsDTO,
    EndpointWithDetailsDTO,
    HostsListResponseDTO,
    HostWithStatsDTO,
    HostWithServicesDTO,
    ServiceResponseDTO,
    EndpointFullDetailsDTO,
    EndpointWithBodyDTO,
    ProgramStatsDTO,
    HostsWithStatsListDTO,
)
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork

logger = logging.getLogger(__name__)


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

    async def get_hosts_with_stats(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        in_scope: Optional[bool] = None
    ) -> HostsWithStatsListDTO:
        """Get hosts with statistics from host_full_stats view"""
        async with self.uow as uow:
            where_clauses = ["program_id = :program_id"]
            params: Dict[str, Any] = {"program_id": program_id, "limit": limit, "offset": offset}

            if in_scope is not None:
                where_clauses.append("in_scope = :in_scope")
                params["in_scope"] = in_scope

            where_sql = " AND ".join(where_clauses)

            count_query = text(f"SELECT COUNT(*) FROM host_full_stats WHERE {where_sql}")
            count_result = await uow._session.execute(count_query, params)
            total = count_result.scalar() or 0

            data_query = text(
                f"SELECT * FROM host_full_stats WHERE {where_sql} LIMIT :limit OFFSET :offset"
            )
            result = await uow._session.execute(data_query, params)
            rows = result.mappings().all()

            return HostsWithStatsListDTO(
                hosts=[HostWithStatsDTO(**dict(row)) for row in rows],
                total=total,
                limit=limit,
                offset=offset
            )

    async def get_host_with_services(self, host_id: UUID) -> Optional[HostWithServicesDTO]:
        """Get host with all services from host_services_view"""
        async with self.uow as uow:
            query = text("SELECT * FROM host_services_view WHERE host_id = :host_id")
            result = await uow._session.execute(query, {"host_id": host_id})
            rows = result.mappings().all()

            if not rows:
                return None

            first_row = rows[0]
            services = []
            for row in rows:
                if row.get("service_id"):
                    services.append(ServiceResponseDTO(
                        id=row["service_id"],
                        scheme=row["scheme"],
                        port=row["port"],
                        technologies=row.get("technologies") or {},
                        favicon_hash=row.get("favicon_hash"),
                        websocket=row.get("websocket", False)
                    ))

            return HostWithServicesDTO(
                host_id=first_row["host_id"],
                host=first_row["host"],
                program_id=first_row["program_id"],
                in_scope=first_row["in_scope"],
                services=services
            )

    async def get_endpoint_full_details(
        self,
        endpoint_id: UUID
    ) -> Optional[EndpointFullDetailsDTO]:
        """Get full endpoint details from endpoint_full_details view"""
        async with self.uow as uow:
            query = text("SELECT * FROM endpoint_full_details WHERE endpoint_id = :endpoint_id")
            result = await uow._session.execute(query, {"endpoint_id": endpoint_id})
            row = result.mappings().first()

            if not row:
                return None

            return EndpointFullDetailsDTO(**dict(row))

    async def get_endpoints_with_body(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        host_id: Optional[UUID] = None
    ) -> tuple[List[EndpointWithBodyDTO], int]:
        """Get endpoints with request body from endpoints_with_body view"""
        async with self.uow as uow:
            where_clauses = ["program_id = :program_id"]
            params: Dict[str, Any] = {"program_id": program_id, "limit": limit, "offset": offset}

            if host_id:
                where_clauses.append("host_id = :host_id")
                params["host_id"] = host_id

            where_sql = " AND ".join(where_clauses)

            count_query = text(f"SELECT COUNT(*) FROM endpoints_with_body WHERE {where_sql}")
            count_result = await uow._session.execute(count_query, params)
            total = count_result.scalar() or 0

            data_query = text(
                f"SELECT * FROM endpoints_with_body WHERE {where_sql} LIMIT :limit OFFSET :offset"
            )
            result = await uow._session.execute(data_query, params)
            rows = result.mappings().all()

            return [EndpointWithBodyDTO(**dict(row)) for row in rows], total

    async def get_program_stats(self, program_id: UUID) -> Optional[ProgramStatsDTO]:
        """Get program statistics from program_stats view"""
        async with self.uow as uow:
            query = text("SELECT * FROM program_stats WHERE program_id = :program_id")
            result = await uow._session.execute(query, {"program_id": program_id})
            row = result.mappings().first()

            if not row:
                return None

            return ProgramStatsDTO(**dict(row))
