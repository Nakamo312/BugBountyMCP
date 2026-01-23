"""DTOs for Host-related responses"""

from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any
from uuid import UUID


class HostResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    program_id: UUID
    host: str
    in_scope: bool
    cname: List[str]


class ServiceResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scheme: str
    port: int
    technologies: Dict[str, Any] = {}
    favicon_hash: Optional[str] = None
    websocket: bool = False


class EndpointResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    host_id: UUID
    service_id: UUID
    path: str
    normalized_path: str
    methods: List[str]
    status_code: Optional[int] = None


class InputParameterResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint_id: UUID
    service_id: UUID
    name: str
    location: str
    param_type: str
    reflected: bool
    is_array: bool
    example_value: Optional[str] = None


class HeaderResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint_id: UUID
    name: str
    value: str


class RawBodyResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint_id: UUID
    body_content: str
    body_hash: str


class HostWithEndpointsDTO(BaseModel):
    host: HostResponseDTO
    endpoints: List[EndpointResponseDTO]


class EndpointWithDetailsDTO(BaseModel):
    endpoint: EndpointResponseDTO
    parameters: List[InputParameterResponseDTO]
    headers: List[HeaderResponseDTO]
    raw_bodies: List[RawBodyResponseDTO] = []


class HostsListResponseDTO(BaseModel):
    hosts: List[HostResponseDTO]
    total: int
    limit: int
    offset: int


class HostWithStatsDTO(BaseModel):
    """Host with statistics from host_full_stats view"""
    host_id: UUID
    host: str
    program_id: UUID
    in_scope: bool
    cname: List[str] = []
    endpoint_count: int = 0
    parameter_count: int = 0
    body_count: int = 0
    header_count: int = 0
    services: List[str] = []
    all_methods: List[str] = []


class HostWithServicesDTO(BaseModel):
    """Host with services from host_services_view"""
    host_id: UUID
    host: str
    program_id: UUID
    in_scope: bool
    services: List[ServiceResponseDTO] = []


class EndpointFullDetailsDTO(BaseModel):
    """Full endpoint details from endpoint_full_details view"""
    endpoint_id: UUID
    host_id: UUID
    host: str
    program_id: UUID
    service_id: UUID
    scheme: str
    port: int
    technologies: Dict[str, Any] = {}
    full_url: str
    path: str
    normalized_path: str
    methods: List[str]
    status_code: Optional[int] = None
    param_count: int = 0
    header_count: int = 0
    body_count: int = 0


class EndpointWithBodyDTO(BaseModel):
    """Endpoint with raw body from endpoints_with_body view"""
    endpoint_id: UUID
    host_id: UUID
    host: str
    program_id: UUID
    full_url: str
    path: str
    normalized_path: str
    methods: List[str]
    status_code: Optional[int] = None
    raw_body_id: Optional[UUID] = None
    body_content: Optional[str] = None
    body_hash: Optional[str] = None


class ProgramStatsDTO(BaseModel):
    """Program statistics from program_stats view"""
    program_id: UUID
    program_name: str
    host_count: int = 0
    in_scope_host_count: int = 0
    endpoint_count: int = 0
    parameter_count: int = 0
    service_count: int = 0
    ip_count: int = 0


class HostsWithStatsListDTO(BaseModel):
    """Paginated hosts with stats"""
    hosts: List[HostWithStatsDTO]
    total: int
    limit: int
    offset: int
