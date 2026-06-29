"""REST routes for security analysis views."""

from dataclasses import dataclass
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from api.application.dto.analysis import AnalysisListDTO
from api.application.services.analysis import AnalysisService

router = APIRouter(tags=["Analysis"], route_class=DishkaRoute)


@dataclass(frozen=True)
class AnalysisEndpoint:
    path: str
    method_name: str
    summary: str
    description: str


_ANALYSIS_ENDPOINTS = (
    AnalysisEndpoint(
        path="/program/{program_id}/injection-candidates",
        method_name="get_injection_candidates",
        summary="Get injection candidates",
        description="Get SQL injection, XSS, and other injection candidates",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/ssrf-candidates",
        method_name="get_ssrf_candidates",
        summary="Get SSRF candidates",
        description="Get Server-Side Request Forgery candidates",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/idor-candidates",
        method_name="get_idor_candidates",
        summary="Get IDOR candidates",
        description="Get Insecure Direct Object Reference candidates",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/file-upload-candidates",
        method_name="get_file_upload_candidates",
        summary="Get file upload candidates",
        description="Get endpoints that accept file uploads",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/reflected-parameters",
        method_name="get_reflected_parameters",
        summary="Get reflected parameters",
        description="Get parameters that are reflected in responses (XSS candidates)",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/arjun-candidates",
        method_name="get_arjun_candidates",
        summary="Get Arjun candidates",
        description="Get endpoints suitable for parameter discovery with Arjun",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/admin-debug-endpoints",
        method_name="get_admin_debug_endpoints",
        summary="Get admin/debug endpoints",
        description="Get endpoints that appear to be admin or debug interfaces",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/cors-analysis",
        method_name="get_cors_analysis",
        summary="Get CORS analysis",
        description="Get CORS configuration analysis for endpoints",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/sensitive-headers",
        method_name="get_sensitive_headers",
        summary="Get sensitive headers",
        description="Get headers containing sensitive information",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/technologies",
        method_name="get_host_technologies",
        summary="Get host technologies",
        description="Get detected technologies for hosts",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/subdomain-takeover",
        method_name="get_subdomain_takeover_candidates",
        summary="Get subdomain takeover candidates",
        description="Get potential subdomain takeover vulnerabilities",
    ),
    AnalysisEndpoint(
        path="/program/{program_id}/api-patterns",
        method_name="get_api_patterns",
        summary="Get API patterns",
        description="Get API pattern analysis for the program",
    ),
)


def _build_analysis_handler(endpoint: AnalysisEndpoint):
    async def handler(
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        analysis_service: FromDishka[AnalysisService] = None,
    ) -> AnalysisListDTO:
        service_method = getattr(analysis_service, endpoint.method_name)
        return await service_method(program_id=program_id, limit=limit, offset=offset)

    handler.__name__ = endpoint.method_name
    return handler


for endpoint in _ANALYSIS_ENDPOINTS:
    router.add_api_route(
        endpoint.path,
        _build_analysis_handler(endpoint),
        methods=["GET"],
        response_model=AnalysisListDTO,
        summary=endpoint.summary,
        description=endpoint.description,
    )
