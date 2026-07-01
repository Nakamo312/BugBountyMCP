"""Infrastructure adapter for bounded read-only database view reads."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.application.read_only_views import ReadOnlyView, ReadOnlyViewPage
from api.infrastructure.read_only_view_queries import view_count_query, view_data_query
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork


class SQLAlchemyReadOnlyViewReader:
    def __init__(self, uow: HTTPXUnitOfWork):
        self._uow = uow

    async def list_view_rows(
        self,
        view: ReadOnlyView,
        filters: Mapping[str, object],
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        view.validate_filters(filters)
        params = {**filters, "limit": limit, "offset": offset}
        async with self._uow as uow:
            result = await uow._session.execute(view_data_query(view, filters), params)
            return [dict(row) for row in result.mappings().all()]

    async def page_view_rows(
        self,
        view: ReadOnlyView,
        filters: Mapping[str, object],
        *,
        limit: int,
        offset: int,
    ) -> ReadOnlyViewPage:
        view.validate_filters(filters)
        params = {**filters, "limit": limit, "offset": offset}
        async with self._uow as uow:
            count_result = await uow._session.execute(view_count_query(view, filters), params)
            total = count_result.scalar() or 0
            result = await uow._session.execute(view_data_query(view, filters), params)
            rows = [dict(row) for row in result.mappings().all()]
            return ReadOnlyViewPage(rows=rows, total=total)
