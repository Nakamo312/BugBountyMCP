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
    methods: List[str]
    status_code: Optional[int] = None
    param_name: str
    param_location: str
    param_type: str
    example_value: Optional[str] = None
    vuln_indicators: List[str] = []


class SSRFCandidateDTO(BaseModel):
    """SSRF candidate from ssrf_candidates_view"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    methods: List[str]
    status_code: Optional[int] = None
    param_name: str
    param_location: str
    example_value: Optional[str] = None


class IDORCandidateDTO(BaseModel):
    """IDOR candidate from idor_candidates_view"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    normalized_path: str
    methods: List[str]
    status_code: Optional[int] = None
    param_count: int = 0
    parameters: List[str] = []


class FileUploadCandidateDTO(BaseModel):
    """File upload candidate from file_upload_candidates"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    methods: List[str]
    status_code: Optional[int] = None
    param_name: str
    param_location: str


class ReflectedParameterDTO(BaseModel):
    """Reflected parameter from reflected_parameters_view"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    methods: List[str]
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
    methods: List[str]
    host: str
    program_id: UUID


class AdminDebugEndpointDTO(BaseModel):
    """Admin/debug endpoint from admin_debug_endpoints"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    normalized_path: str
    methods: List[str]
    status_code: Optional[int] = None
    match_type: str


class CORSAnalysisDTO(BaseModel):
    """CORS analysis from cors_analysis"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    cors_header: Optional[str] = None
    cors_credentials: Optional[str] = None
    cors_methods: Optional[str] = None
    cors_headers: Optional[str] = None


class SensitiveHeaderDTO(BaseModel):
    """Sensitive header from sensitive_headers_view"""
    program_id: UUID
    host: str
    full_url: str
    path: str
    header_name: str
    header_value: str
    sensitivity_type: str


class HostTechnologyDTO(BaseModel):
    """Host technology from host_technologies"""
    host: str
    program_id: UUID
    scheme: str
    port: int
    technologies: Dict[str, Any] = {}
    favicon_hash: Optional[str] = None


class SubdomainTakeoverCandidateDTO(BaseModel):
    """Subdomain takeover candidate"""
    program_id: UUID
    host: str
    cname: List[str] = []
    status_code: Optional[int] = None
    takeover_type: Optional[str] = None


class APIPatternDTO(BaseModel):
    """API pattern from api_pattern_analysis"""
    program_id: UUID
    normalized_path: str
    host_count: int = 0
    endpoint_count: int = 0
    all_methods: List[str] = []
    all_status_codes: List[int] = []
    unique_params: int = 0
    param_names: List[str] = []


class AnalysisListDTO(BaseModel):
    """Generic paginated analysis list"""
    items: List[Any]
    total: int
    limit: int
    offset: int
