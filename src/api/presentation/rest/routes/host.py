"""REST routes for hosts, endpoints, parameters and headers"""

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, status

from api.application.dto.host import (
    HostResponseDTO,
    EndpointResponseDTO,
    InputParameterResponseDTO,
    HeaderResponseDTO,
    HostWithEndpointsDTO,
    EndpointWithDetailsDTO,
    HostsListResponseDTO
)
from api.application.services.host import HostService

router = APIRouter(tags=["Hosts"], route_class=DishkaRoute)


@router.get(
    "/program/{program_id}",
    response_model=HostsListResponseDTO,
    summary="Get hosts by program",
    description="Get paginated list of hosts for a program with optional filtering by scope"
)
async def get_hosts_by_program(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    in_scope: bool | None = None,
    host_service: FromDishka[HostService] = None
) -> HostsListResponseDTO:
    """Get hosts by program_id with pagination"""
    try:
        return await host_service.get_hosts_by_program(
            program_id=program_id,
            limit=limit,
            offset=offset,
            in_scope=in_scope
        )
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Error fetching hosts for program {program_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching hosts: {str(e)}"
        )


@router.get(
    "/{host_id}",
    response_model=HostWithEndpointsDTO,
    summary="Get host with endpoints",
    description="Get host details with all associated endpoints"
)
async def get_host_with_endpoints(
    host_id: UUID,
    host_service: FromDishka[HostService] = None
) -> HostWithEndpointsDTO:
    """Get host with all endpoints"""
    result = await host_service.get_host_with_endpoints(host_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Host {host_id} not found"
        )
    return result


@router.get(
    "/{host_id}/endpoints",
    response_model=list[EndpointResponseDTO],
    summary="Get endpoints by host",
    description="Get all endpoints for a specific host"
)
async def get_endpoints_by_host(
    host_id: UUID,
    limit: int = 100,
    offset: int = 0,
    host_service: FromDishka[HostService] = None
) -> list[EndpointResponseDTO]:
    """Get endpoints by host_id"""
    try:
        return await host_service.get_endpoints_by_host(
            host_id=host_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching endpoints: {str(e)}"
        )


@router.get(
    "/endpoints/{endpoint_id}",
    response_model=EndpointWithDetailsDTO,
    summary="Get endpoint with details",
    description="Get endpoint details with parameters and headers"
)
async def get_endpoint_with_details(
    endpoint_id: UUID,
    host_service: FromDishka[HostService] = None
) -> EndpointWithDetailsDTO:
    """Get endpoint with parameters and headers"""
    result = await host_service.get_endpoint_with_details(endpoint_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint {endpoint_id} not found"
        )
    return result


@router.get(
    "/endpoints/{endpoint_id}/parameters",
    response_model=list[InputParameterResponseDTO],
    summary="Get parameters by endpoint",
    description="Get all input parameters for a specific endpoint"
)
async def get_parameters_by_endpoint(
    endpoint_id: UUID,
    limit: int = 100,
    offset: int = 0,
    host_service: FromDishka[HostService] = None
) -> list[InputParameterResponseDTO]:
    """Get input parameters by endpoint_id"""
    try:
        return await host_service.get_parameters_by_endpoint(
            endpoint_id=endpoint_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching parameters: {str(e)}"
        )


@router.get(
    "/endpoints/{endpoint_id}/headers",
    response_model=list[HeaderResponseDTO],
    summary="Get headers by endpoint",
    description="Get all response headers for a specific endpoint"
)
async def get_headers_by_endpoint(
    endpoint_id: UUID,
    limit: int = 100,
    offset: int = 0,
    host_service: FromDishka[HostService] = None
) -> list[HeaderResponseDTO]:
    """Get headers by endpoint_id"""
    try:
        return await host_service.get_headers_by_endpoint(
            endpoint_id=endpoint_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching headers: {str(e)}"
        )
