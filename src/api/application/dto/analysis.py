"""DTOs for security analysis views"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID


class InjectionCandidateDTO(BaseModel):
    """Injection candidate from injection_candidates_view"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    methods: Optional[List[str]] = None
    status_code: Optional[int] = None
    query_params: Optional[List[str]] = None
    body_params: Optional[List[str]] = None
    path_params: Optional[List[str]] = None
    injectable_params: Optional[List[str]] = None


class SSRFCandidateDTO(BaseModel):
    """SSRF candidate from ssrf_candidates_view"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    methods: Optional[List[str]] = None
    param_name: str
    location: str
    example_value: Optional[str] = None


class IDORCandidateDTO(BaseModel):
    """IDOR candidate from idor_candidates_view"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    normalized_path: str
    methods: Optional[List[str]] = None
    status_code: Optional[int] = None
    param_count: int = 0
    parameters: Optional[List[str]] = None


class FileUploadCandidateDTO(BaseModel):
    """File upload candidate from file_upload_candidates"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    methods: Optional[List[str]] = None
    file_params: Optional[List[str]] = None
    file_param_names: Optional[List[str]] = None


class ReflectedParameterDTO(BaseModel):
    """Reflected parameter from reflected_parameters_view"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    methods: Optional[List[str]] = None
    status_code: Optional[int] = None
    param_name: str
    param_location: str
    param_type: str
    example_value: Optional[str] = None
    is_array: bool = False


class ArjunCandidateDTO(BaseModel):
    """Arjun candidate from arjun_candidate_endpoints"""
    endpoint_id: UUID
    full_url: str
    path: str
    normalized_path: str
    status_code: Optional[int] = None
    methods: Optional[List[str]] = None
    host: str
    program_id: UUID


class AdminDebugEndpointDTO(BaseModel):
    """Admin/debug endpoint from admin_debug_endpoints"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    methods: Optional[List[str]] = None
    status_code: Optional[int] = None


class CORSAnalysisDTO(BaseModel):
    """CORS analysis from cors_analysis"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    cors_header_value: Optional[str] = None


class SensitiveHeaderDTO(BaseModel):
    """Sensitive header from sensitive_headers_view"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    header_name: str
    header_value: str


class HostTechnologyDTO(BaseModel):
    """Host technology from host_technologies"""
    program_id: UUID
    host: str
    address: str
    port: int
    scheme: str
    technologies: Optional[Dict[str, Any]] = None
    server_headers: Optional[Dict[str, Any]] = None


class SubdomainTakeoverCandidateDTO(BaseModel):
    """Subdomain takeover candidate from subdomain_takeover_candidates"""
    host: str
    program_id: UUID
    cname_target: Optional[str] = None
    platform: Optional[str] = None


class APIPatternDTO(BaseModel):
    """API pattern from api_pattern_analysis"""
    program_id: UUID
    normalized_path: str
    host_count: int = 0
    endpoint_count: int = 0
    all_methods: Optional[List[str]] = None
    all_status_codes: Optional[List[int]] = None
    unique_params: int = 0
    param_names: Optional[List[str]] = None


class AnalysisListDTO(BaseModel):
    """Generic paginated analysis list"""
    items: List[Any]
    total: int
    limit: int
    offset: int
