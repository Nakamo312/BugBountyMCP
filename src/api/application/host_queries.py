"""Application-level host query contracts."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from api.application.dto.host import (
    EndpointResponseDTO,
    EndpointWithDetailsDTO,
    HeaderResponseDTO,
    HostWithEndpointsDTO,
    HostsListResponseDTO,
    InputParameterResponseDTO,
)


class HostAssetReader(Protocol):
    async def get_hosts_by_program(
        self,
        *,
        program_id: UUID,
        limit: int,
        offset: int,
        in_scope: bool | None = None,
    ) -> HostsListResponseDTO:
        ...

    async def get_host_with_endpoints(
        self,
        *,
        host_id: UUID,
    ) -> HostWithEndpointsDTO | None:
        ...

    async def get_endpoints_by_host(
        self,
        *,
        host_id: UUID,
        limit: int,
        offset: int,
    ) -> list[EndpointResponseDTO]:
        ...

    async def get_endpoint_with_details(
        self,
        *,
        endpoint_id: UUID,
    ) -> EndpointWithDetailsDTO | None:
        ...

    async def get_parameters_by_endpoint(
        self,
        *,
        endpoint_id: UUID,
        limit: int,
        offset: int,
    ) -> list[InputParameterResponseDTO]:
        ...

    async def get_headers_by_endpoint(
        self,
        *,
        endpoint_id: UUID,
        limit: int,
        offset: int,
    ) -> list[HeaderResponseDTO]:
        ...
