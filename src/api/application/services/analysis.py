"""Service for querying security analysis views"""

import logging
from typing import List, Dict, Any
from uuid import UUID

from api.application.dto.analysis import (
    InjectionCandidateDTO,
    SSRFCandidateDTO,
    IDORCandidateDTO,
    FileUploadCandidateDTO,
    ReflectedParameterDTO,
    ArjunCandidateDTO,
    AdminDebugEndpointDTO,
    CORSAnalysisDTO,
    SensitiveHeaderDTO,
    HostTechnologyDTO,
    SubdomainTakeoverCandidateDTO,
    APIPatternDTO,
    AnalysisListDTO,
)
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork
from api.application.services.view_queries import (
    ReadOnlyView,
    view_count_query,
    view_data_query,
)

logger = logging.getLogger(__name__)

_PROGRAM_VIEW_FILTERS = frozenset({"program_id"})
_INJECTION_CANDIDATES_VIEW = ReadOnlyView("injection_candidates_view", _PROGRAM_VIEW_FILTERS)
_SSRF_CANDIDATES_VIEW = ReadOnlyView("ssrf_candidates_view", _PROGRAM_VIEW_FILTERS)
_IDOR_CANDIDATES_VIEW = ReadOnlyView("idor_candidates_view", _PROGRAM_VIEW_FILTERS)
_FILE_UPLOAD_CANDIDATES_VIEW = ReadOnlyView("file_upload_candidates", _PROGRAM_VIEW_FILTERS)
_REFLECTED_PARAMETERS_VIEW = ReadOnlyView("reflected_parameters_view", _PROGRAM_VIEW_FILTERS)
_ARJUN_CANDIDATE_ENDPOINTS_VIEW = ReadOnlyView("arjun_candidate_endpoints", _PROGRAM_VIEW_FILTERS)
_ADMIN_DEBUG_ENDPOINTS_VIEW = ReadOnlyView("admin_debug_endpoints", _PROGRAM_VIEW_FILTERS)
_CORS_ANALYSIS_VIEW = ReadOnlyView("cors_analysis", _PROGRAM_VIEW_FILTERS)
_SENSITIVE_HEADERS_VIEW = ReadOnlyView("sensitive_headers_view", _PROGRAM_VIEW_FILTERS)
_HOST_TECHNOLOGIES_VIEW = ReadOnlyView("host_technologies", _PROGRAM_VIEW_FILTERS)
_SUBDOMAIN_TAKEOVER_CANDIDATES_VIEW = ReadOnlyView("subdomain_takeover_candidates", _PROGRAM_VIEW_FILTERS)
_API_PATTERN_ANALYSIS_VIEW = ReadOnlyView("api_pattern_analysis", _PROGRAM_VIEW_FILTERS)


class AnalysisService:
    """Service for querying security analysis database views"""

    def __init__(self, uow: HTTPXUnitOfWork):
        self.uow = uow

    async def _query_view(
        self,
        view: ReadOnlyView,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        extra_filters: Dict[str, Any] | None = None
    ) -> tuple[List[Dict[str, Any]], int]:
        """Execute a bounded query against an allow-listed read-only view."""
        async with self.uow as uow:
            filters: Dict[str, Any] = {"program_id": program_id}
            if extra_filters:
                filters.update(extra_filters)
            params = {**filters, "limit": limit, "offset": offset}

            count_result = await uow._session.execute(view_count_query(view, filters), params)
            total = count_result.scalar() or 0

            result = await uow._session.execute(view_data_query(view, filters), params)
            rows = result.mappings().all()

            return [dict(row) for row in rows], total

    async def get_injection_candidates(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get injection candidates (SQLi, XSS, etc.)"""
        rows, total = await self._query_view(
            _INJECTION_CANDIDATES_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[InjectionCandidateDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_ssrf_candidates(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get SSRF candidates"""
        rows, total = await self._query_view(
            _SSRF_CANDIDATES_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[SSRFCandidateDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_idor_candidates(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get IDOR candidates"""
        rows, total = await self._query_view(
            _IDOR_CANDIDATES_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[IDORCandidateDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_file_upload_candidates(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get file upload candidates"""
        rows, total = await self._query_view(
            _FILE_UPLOAD_CANDIDATES_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[FileUploadCandidateDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_reflected_parameters(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get reflected parameters (XSS candidates)"""
        rows, total = await self._query_view(
            _REFLECTED_PARAMETERS_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[ReflectedParameterDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_arjun_candidates(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get Arjun parameter discovery candidates"""
        rows, total = await self._query_view(
            _ARJUN_CANDIDATE_ENDPOINTS_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[ArjunCandidateDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_admin_debug_endpoints(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get admin/debug endpoints"""
        rows, total = await self._query_view(
            _ADMIN_DEBUG_ENDPOINTS_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[AdminDebugEndpointDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_cors_analysis(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get CORS configuration analysis"""
        rows, total = await self._query_view(
            _CORS_ANALYSIS_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[CORSAnalysisDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_sensitive_headers(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get sensitive headers"""
        rows, total = await self._query_view(
            _SENSITIVE_HEADERS_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[SensitiveHeaderDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_host_technologies(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get host technologies"""
        rows, total = await self._query_view(
            _HOST_TECHNOLOGIES_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[HostTechnologyDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_subdomain_takeover_candidates(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get subdomain takeover candidates"""
        rows, total = await self._query_view(
            _SUBDOMAIN_TAKEOVER_CANDIDATES_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[SubdomainTakeoverCandidateDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )

    async def get_api_patterns(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> AnalysisListDTO:
        """Get API pattern analysis"""
        rows, total = await self._query_view(
            _API_PATTERN_ANALYSIS_VIEW, program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[APIPatternDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )
