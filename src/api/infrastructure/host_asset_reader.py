"""Repository-backed host query adapter."""
from __future__ import annotations

from uuid import UUID

from api.application.dto.host import (
    EndpointResponseDTO,
    EndpointWithDetailsDTO,
    HeaderResponseDTO,
    HostResponseDTO,
    HostWithEndpointsDTO,
    HostsListResponseDTO,
    InputParameterResponseDTO,
)
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork

RELATED_ROWS_LIMIT = 1000


class RepositoryHostAssetReader:
    """Read host-facing DTOs through repository UoW internals."""

    def __init__(self, uow: HTTPXUnitOfWork):
        self._uow = uow

    async def get_hosts_by_program(
        self,
        *,
        program_id: UUID,
        limit: int,
        offset: int,
        in_scope: bool | None = None,
    ) -> HostsListResponseDTO:
        async with self._uow as uow:
            hosts = await uow.hosts.find_by_program(
                program_id=program_id,
                limit=limit,
                offset=offset,
                in_scope=in_scope,
            )
            filters = {"program_id": program_id}
            if in_scope is not None:
                filters["in_scope"] = in_scope
            total = await uow.hosts.count(filters=filters)

        return HostsListResponseDTO(
            hosts=[HostResponseDTO.model_validate(host) for host in hosts],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_host_with_endpoints(
        self,
        *,
        host_id: UUID,
    ) -> HostWithEndpointsDTO | None:
        async with self._uow as uow:
            host = await uow.hosts.get(host_id)
            if not host:
                return None
            endpoints = await uow.endpoints.find_by_host(
                host_id,
                limit=RELATED_ROWS_LIMIT,
            )

        return HostWithEndpointsDTO(
            host=HostResponseDTO.model_validate(host),
            endpoints=[EndpointResponseDTO.model_validate(ep) for ep in endpoints],
        )

    async def get_endpoints_by_host(
        self,
        *,
        host_id: UUID,
        limit: int,
        offset: int,
    ) -> list[EndpointResponseDTO]:
        async with self._uow as uow:
            endpoints = await uow.endpoints.find_by_host(
                host_id=host_id,
                limit=limit,
                offset=offset,
            )
        return [EndpointResponseDTO.model_validate(ep) for ep in endpoints]

    async def get_endpoint_with_details(
        self,
        *,
        endpoint_id: UUID,
    ) -> EndpointWithDetailsDTO | None:
        async with self._uow as uow:
            endpoint = await uow.endpoints.get(endpoint_id)
            if not endpoint:
                return None
            parameters = await uow.input_parameters.find_by_endpoint(
                endpoint_id=endpoint_id,
                limit=RELATED_ROWS_LIMIT,
            )
            headers = await uow.headers.find_by_endpoint(
                endpoint_id=endpoint_id,
                limit=RELATED_ROWS_LIMIT,
            )

        return EndpointWithDetailsDTO(
            endpoint=EndpointResponseDTO.model_validate(endpoint),
            parameters=[
                InputParameterResponseDTO.model_validate(param) for param in parameters
            ],
            headers=[HeaderResponseDTO.model_validate(header) for header in headers],
        )

    async def get_parameters_by_endpoint(
        self,
        *,
        endpoint_id: UUID,
        limit: int,
        offset: int,
    ) -> list[InputParameterResponseDTO]:
        async with self._uow as uow:
            parameters = await uow.input_parameters.find_by_endpoint(
                endpoint_id=endpoint_id,
                limit=limit,
                offset=offset,
            )
        return [InputParameterResponseDTO.model_validate(param) for param in parameters]

    async def get_headers_by_endpoint(
        self,
        *,
        endpoint_id: UUID,
        limit: int,
        offset: int,
    ) -> list[HeaderResponseDTO]:
        async with self._uow as uow:
            headers = await uow.headers.find_by_endpoint(
                endpoint_id=endpoint_id,
                limit=limit,
                offset=offset,
            )
        return [HeaderResponseDTO.model_validate(header) for header in headers]
