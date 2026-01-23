"""Service for querying security analysis views"""

import logging
from typing import List, Dict, Any
from uuid import UUID

from sqlalchemy import text

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

logger = logging.getLogger(__name__)


class AnalysisService:
    """Service for querying security analysis database views"""

    def __init__(self, uow: HTTPXUnitOfWork):
        self.uow = uow

    async def _query_view(
        self,
        view_name: str,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        extra_filters: Dict[str, Any] | None = None
    ) -> tuple[List[Dict[str, Any]], int]:
        """Execute query against a view with pagination"""
        async with self.uow as uow:
            where_clauses = ["program_id = :program_id"]
            params = {"program_id": program_id, "limit": limit, "offset": offset}

            if extra_filters:
                for key, value in extra_filters.items():
                    where_clauses.append(f"{key} = :{key}")
                    params[key] = value

            where_sql = " AND ".join(where_clauses)

            count_query = text(f"SELECT COUNT(*) FROM {view_name} WHERE {where_sql}")
            count_result = await uow._session.execute(count_query, params)
            total = count_result.scalar() or 0

            data_query = text(
                f"SELECT * FROM {view_name} WHERE {where_sql} LIMIT :limit OFFSET :offset"
            )
            result = await uow._session.execute(data_query, params)
            rows = result.mappings().all()

            return [dict(row) for row in rows], total

    async def get_injection_candidates(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        param_location: str | None = None
    ) -> AnalysisListDTO:
        """Get injection candidates (SQLi, XSS, etc.)"""
        filters = {}
        if param_location:
            filters["param_location"] = param_location

        rows, total = await self._query_view(
            "injection_candidates_view", program_id, limit, offset, filters
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
            "ssrf_candidates_view", program_id, limit, offset
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
            "idor_candidates_view", program_id, limit, offset
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
            "file_upload_candidates", program_id, limit, offset
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
            "reflected_parameters_view", program_id, limit, offset
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
            "arjun_candidate_endpoints", program_id, limit, offset
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
            "admin_debug_endpoints", program_id, limit, offset
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
            "cors_analysis", program_id, limit, offset
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
        offset: int = 0,
        sensitivity_type: str | None = None
    ) -> AnalysisListDTO:
        """Get sensitive headers"""
        filters = {}
        if sensitivity_type:
            filters["sensitivity_type"] = sensitivity_type

        rows, total = await self._query_view(
            "sensitive_headers_view", program_id, limit, offset, filters
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
            "host_technologies", program_id, limit, offset
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
            "subdomain_takeover_candidates", program_id, limit, offset
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
            "api_pattern_analysis", program_id, limit, offset
        )
        return AnalysisListDTO(
            items=[APIPatternDTO(**row) for row in rows],
            total=total,
            limit=limit,
            offset=offset
        )
