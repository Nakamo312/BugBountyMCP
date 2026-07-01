"""Service for working with hosts, endpoints, parameters and headers"""

from typing import List, Optional, Dict, Any
from uuid import UUID

from api.application.dto.host import (
    EndpointResponseDTO,
    InputParameterResponseDTO,
    HeaderResponseDTO,
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
from api.application.host_queries import HostAssetReader
from api.application.read_only_views import ReadOnlyView, ReadOnlyViewReader

_PROGRAM_VIEW_FILTERS = frozenset({"program_id"})
_PROGRAM_HOST_VIEW_FILTERS = frozenset({"program_id", "host_id"})
_HOST_ID_VIEW_FILTERS = frozenset({"host_id"})
_ENDPOINT_ID_VIEW_FILTERS = frozenset({"endpoint_id"})
RELATED_ROWS_LIMIT = 1000

_HOST_FULL_STATS_VIEW = ReadOnlyView("host_full_stats", _PROGRAM_VIEW_FILTERS | frozenset({"in_scope"}))
_HOST_SERVICES_VIEW = ReadOnlyView("host_services_view", _HOST_ID_VIEW_FILTERS)
_ENDPOINT_FULL_DETAILS_VIEW = ReadOnlyView("endpoint_full_details", _ENDPOINT_ID_VIEW_FILTERS)
_ENDPOINTS_WITH_BODY_VIEW = ReadOnlyView("endpoints_with_body", _PROGRAM_HOST_VIEW_FILTERS)
_PROGRAM_STATS_VIEW = ReadOnlyView("program_stats", _PROGRAM_VIEW_FILTERS)


class HostService:
    """Service for querying hosts and related data"""

    def __init__(
        self,
        host_reader: HostAssetReader,
        view_reader: ReadOnlyViewReader,
    ):
        self._host_reader = host_reader
        self._view_reader = view_reader
    
    async def get_hosts_by_program(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        in_scope: Optional[bool] = None,
    ) -> HostsListResponseDTO:
        """Get hosts by program_id with pagination"""
        return await self._host_reader.get_hosts_by_program(
            program_id=program_id,
            limit=limit,
            offset=offset,
            in_scope=in_scope,
        )

    async def get_host_with_endpoints(
        self,
        host_id: UUID,
    ) -> Optional[HostWithEndpointsDTO]:
        """Get host with all endpoints"""
        return await self._host_reader.get_host_with_endpoints(host_id=host_id)

    async def get_endpoints_by_host(
        self,
        host_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[EndpointResponseDTO]:
        """Get endpoints by host_id"""
        return await self._host_reader.get_endpoints_by_host(
            host_id=host_id,
            limit=limit,
            offset=offset,
        )

    async def get_endpoint_with_details(
        self,
        endpoint_id: UUID,
    ) -> Optional[EndpointWithDetailsDTO]:
        """Get endpoint with parameters and headers"""
        return await self._host_reader.get_endpoint_with_details(endpoint_id=endpoint_id)

    async def get_parameters_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[InputParameterResponseDTO]:
        """Get input parameters by endpoint_id"""
        return await self._host_reader.get_parameters_by_endpoint(
            endpoint_id=endpoint_id,
            limit=limit,
            offset=offset,
        )

    async def get_headers_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[HeaderResponseDTO]:
        """Get headers by endpoint_id"""
        return await self._host_reader.get_headers_by_endpoint(
            endpoint_id=endpoint_id,
            limit=limit,
            offset=offset,
        )

    async def get_hosts_with_stats(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        in_scope: Optional[bool] = None,
    ) -> HostsWithStatsListDTO:
        """Get hosts with statistics from host_full_stats view"""
        filters: Dict[str, Any] = {"program_id": program_id}
        if in_scope is not None:
            filters["in_scope"] = in_scope

        page = await self._view_reader.page_view_rows(
            _HOST_FULL_STATS_VIEW,
            filters,
            limit=limit,
            offset=offset,
        )
        return HostsWithStatsListDTO(
            hosts=[HostWithStatsDTO(**row) for row in page.rows],
            total=page.total or 0,
            limit=limit,
            offset=offset,
        )

    async def get_host_with_services(self, host_id: UUID) -> Optional[HostWithServicesDTO]:
        """Get host with all services from host_services_view"""
        filters = {"host_id": host_id}
        rows = await self._view_reader.list_view_rows(
            _HOST_SERVICES_VIEW,
            filters,
            limit=RELATED_ROWS_LIMIT,
            offset=0,
        )

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
                    websocket=row.get("websocket", False),
                ))

        return HostWithServicesDTO(
            host_id=first_row["host_id"],
            host=first_row["host"],
            program_id=first_row["program_id"],
            in_scope=first_row["in_scope"],
            services=services,
        )

    async def get_endpoint_full_details(
        self,
        endpoint_id: UUID,
    ) -> Optional[EndpointFullDetailsDTO]:
        """Get full endpoint details from endpoint_full_details view"""
        rows = await self._view_reader.list_view_rows(
            _ENDPOINT_FULL_DETAILS_VIEW,
            {"endpoint_id": endpoint_id},
            limit=1,
            offset=0,
        )
        if not rows:
            return None
        return EndpointFullDetailsDTO(**rows[0])

    async def get_endpoints_with_body(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        host_id: Optional[UUID] = None,
    ) -> tuple[List[EndpointWithBodyDTO], int]:
        """Get endpoints with request body from endpoints_with_body view"""
        filters: Dict[str, Any] = {"program_id": program_id}
        if host_id:
            filters["host_id"] = host_id

        page = await self._view_reader.page_view_rows(
            _ENDPOINTS_WITH_BODY_VIEW,
            filters,
            limit=limit,
            offset=offset,
        )
        return [EndpointWithBodyDTO(**row) for row in page.rows], page.total or 0

    async def get_program_stats(self, program_id: UUID) -> Optional[ProgramStatsDTO]:
        """Get program statistics from program_stats view"""
        rows = await self._view_reader.list_view_rows(
            _PROGRAM_STATS_VIEW,
            {"program_id": program_id},
            limit=1,
            offset=0,
        )
        if not rows:
            return None
        return ProgramStatsDTO(**rows[0])
