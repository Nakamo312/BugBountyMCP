"""Service for querying security analysis views"""

from dataclasses import dataclass
from typing import List, Dict, Any
from uuid import UUID

from pydantic import BaseModel

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


@dataclass(frozen=True)
class AnalysisQuery:
    view: ReadOnlyView
    item_model: type[BaseModel]


_ANALYSIS_QUERIES = {
    "injection_candidates": AnalysisQuery(_INJECTION_CANDIDATES_VIEW, InjectionCandidateDTO),
    "ssrf_candidates": AnalysisQuery(_SSRF_CANDIDATES_VIEW, SSRFCandidateDTO),
    "idor_candidates": AnalysisQuery(_IDOR_CANDIDATES_VIEW, IDORCandidateDTO),
    "file_upload_candidates": AnalysisQuery(_FILE_UPLOAD_CANDIDATES_VIEW, FileUploadCandidateDTO),
    "reflected_parameters": AnalysisQuery(_REFLECTED_PARAMETERS_VIEW, ReflectedParameterDTO),
    "arjun_candidates": AnalysisQuery(_ARJUN_CANDIDATE_ENDPOINTS_VIEW, ArjunCandidateDTO),
    "admin_debug_endpoints": AnalysisQuery(_ADMIN_DEBUG_ENDPOINTS_VIEW, AdminDebugEndpointDTO),
    "cors_analysis": AnalysisQuery(_CORS_ANALYSIS_VIEW, CORSAnalysisDTO),
    "sensitive_headers": AnalysisQuery(_SENSITIVE_HEADERS_VIEW, SensitiveHeaderDTO),
    "host_technologies": AnalysisQuery(_HOST_TECHNOLOGIES_VIEW, HostTechnologyDTO),
    "subdomain_takeover": AnalysisQuery(
        _SUBDOMAIN_TAKEOVER_CANDIDATES_VIEW,
        SubdomainTakeoverCandidateDTO,
    ),
    "api_patterns": AnalysisQuery(_API_PATTERN_ANALYSIS_VIEW, APIPatternDTO),
}


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

    async def get_analysis(
        self,
        kind: str,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> AnalysisListDTO:
        """Get a registered analysis view."""
        query = _ANALYSIS_QUERIES.get(kind)
        if query is None:
            raise ValueError(f"Unknown analysis kind: {kind}")

        rows, total = await self._query_view(query.view, program_id, limit, offset)
        return AnalysisListDTO(
            items=[query.item_model(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
