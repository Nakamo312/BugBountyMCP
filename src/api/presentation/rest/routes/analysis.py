"""REST routes for security analysis views"""

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, status

from api.application.dto.analysis import AnalysisListDTO
from api.application.services.analysis import AnalysisService

router = APIRouter(tags=["Analysis"], route_class=DishkaRoute)


@router.get(
    "/program/{program_id}/injection-candidates",
    response_model=AnalysisListDTO,
    summary="Get injection candidates",
    description="Get SQL injection, XSS, and other injection candidates"
)
async def get_injection_candidates(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    param_location: str | None = None,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_injection_candidates(
            program_id=program_id,
            limit=limit,
            offset=offset,
            param_location=param_location
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching injection candidates: {str(e)}"
        )


@router.get(
    "/program/{program_id}/ssrf-candidates",
    response_model=AnalysisListDTO,
    summary="Get SSRF candidates",
    description="Get Server-Side Request Forgery candidates"
)
async def get_ssrf_candidates(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_ssrf_candidates(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching SSRF candidates: {str(e)}"
        )


@router.get(
    "/program/{program_id}/idor-candidates",
    response_model=AnalysisListDTO,
    summary="Get IDOR candidates",
    description="Get Insecure Direct Object Reference candidates"
)
async def get_idor_candidates(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_idor_candidates(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching IDOR candidates: {str(e)}"
        )


@router.get(
    "/program/{program_id}/file-upload-candidates",
    response_model=AnalysisListDTO,
    summary="Get file upload candidates",
    description="Get endpoints that accept file uploads"
)
async def get_file_upload_candidates(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_file_upload_candidates(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching file upload candidates: {str(e)}"
        )


@router.get(
    "/program/{program_id}/reflected-parameters",
    response_model=AnalysisListDTO,
    summary="Get reflected parameters",
    description="Get parameters that are reflected in responses (XSS candidates)"
)
async def get_reflected_parameters(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_reflected_parameters(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching reflected parameters: {str(e)}"
        )


@router.get(
    "/program/{program_id}/arjun-candidates",
    response_model=AnalysisListDTO,
    summary="Get Arjun candidates",
    description="Get endpoints suitable for parameter discovery with Arjun"
)
async def get_arjun_candidates(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_arjun_candidates(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching Arjun candidates: {str(e)}"
        )


@router.get(
    "/program/{program_id}/admin-debug-endpoints",
    response_model=AnalysisListDTO,
    summary="Get admin/debug endpoints",
    description="Get endpoints that appear to be admin or debug interfaces"
)
async def get_admin_debug_endpoints(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_admin_debug_endpoints(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching admin/debug endpoints: {str(e)}"
        )


@router.get(
    "/program/{program_id}/cors-analysis",
    response_model=AnalysisListDTO,
    summary="Get CORS analysis",
    description="Get CORS configuration analysis for endpoints"
)
async def get_cors_analysis(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_cors_analysis(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching CORS analysis: {str(e)}"
        )


@router.get(
    "/program/{program_id}/sensitive-headers",
    response_model=AnalysisListDTO,
    summary="Get sensitive headers",
    description="Get headers containing sensitive information"
)
async def get_sensitive_headers(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    sensitivity_type: str | None = None,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_sensitive_headers(
            program_id=program_id,
            limit=limit,
            offset=offset,
            sensitivity_type=sensitivity_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching sensitive headers: {str(e)}"
        )


@router.get(
    "/program/{program_id}/technologies",
    response_model=AnalysisListDTO,
    summary="Get host technologies",
    description="Get detected technologies for hosts"
)
async def get_host_technologies(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_host_technologies(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching host technologies: {str(e)}"
        )


@router.get(
    "/program/{program_id}/subdomain-takeover",
    response_model=AnalysisListDTO,
    summary="Get subdomain takeover candidates",
    description="Get potential subdomain takeover vulnerabilities"
)
async def get_subdomain_takeover_candidates(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_subdomain_takeover_candidates(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching subdomain takeover candidates: {str(e)}"
        )


@router.get(
    "/program/{program_id}/api-patterns",
    response_model=AnalysisListDTO,
    summary="Get API patterns",
    description="Get API pattern analysis for the program"
)
async def get_api_patterns(
    program_id: UUID,
    limit: int = 100,
    offset: int = 0,
    analysis_service: FromDishka[AnalysisService] = None
) -> AnalysisListDTO:
    try:
        return await analysis_service.get_api_patterns(
            program_id=program_id,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching API patterns: {str(e)}"
        )
