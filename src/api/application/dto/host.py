"""DTOs for Host-related responses"""

from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from uuid import UUID


class HostResponseDTO(BaseModel):
    """Host response DTO"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    program_id: UUID
    host: str
    in_scope: bool
    cname: List[str]


class EndpointResponseDTO(BaseModel):
    """Endpoint response DTO"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    host_id: UUID
    service_id: UUID
    path: str
    normalized_path: str
    methods: List[str]
    status_code: Optional[int] = None


class InputParameterResponseDTO(BaseModel):
    """Input parameter response DTO"""
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
    """Header response DTO"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    endpoint_id: UUID
    name: str
    value: str


class HostWithEndpointsDTO(BaseModel):
    """Host with endpoints DTO"""
    host: HostResponseDTO
    endpoints: List[EndpointResponseDTO]


class EndpointWithDetailsDTO(BaseModel):
    """Endpoint with parameters and headers DTO"""
    endpoint: EndpointResponseDTO
    parameters: List[InputParameterResponseDTO]
    headers: List[HeaderResponseDTO]


class HostsListResponseDTO(BaseModel):
    """Paginated hosts list response"""
    hosts: List[HostResponseDTO]
    total: int
    limit: int
    offset: int
