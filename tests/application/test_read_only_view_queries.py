from uuid import uuid4

import pytest
from sqlalchemy.sql import Select

from api.application.services.analysis import AnalysisService
from api.application.services.view_queries import (
    ReadOnlyView,
    view_count_query,
    view_data_query,
)


def test_read_only_view_queries_compile_to_core_selects() -> None:
    view = ReadOnlyView("injection_candidates_view", frozenset({"program_id"}))
    filters = {"program_id": uuid4()}

    count_query = view_count_query(view, filters)
    data_query = view_data_query(view, filters)

    assert isinstance(count_query, Select)
    assert isinstance(data_query, Select)
    assert "FROM injection_candidates_view" in str(count_query)
    assert "WHERE program_id = :program_id" in str(data_query)


@pytest.mark.parametrize("bad_name", ["", "HostStats", "host-stats", "host_stats;drop"])
def test_read_only_view_rejects_invalid_view_names(bad_name: str) -> None:
    with pytest.raises(ValueError):
        ReadOnlyView(bad_name, frozenset({"program_id"}))


def test_view_queries_reject_filters_outside_view_contract() -> None:
    view = ReadOnlyView("host_full_stats", frozenset({"program_id"}))

    with pytest.raises(ValueError):
        view_data_query(view, {"program_id": uuid4(), "in_scope": True})


class _FakeMappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, *, scalar_value=None, rows=None):
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self):
        return self._scalar_value

    def mappings(self):
        return _FakeMappings(self._rows)


class _FakeSession:
    def __init__(self, row=None):
        self.executed = []
        self.row = row

    async def execute(self, statement, params):
        self.executed.append((statement, params))
        if len(self.executed) == 1:
            return _FakeResult(scalar_value=1)
        row = self.row or {"program_id": params["program_id"], "candidate": "xss"}
        return _FakeResult(rows=[row])


class _FakeUow:
    def __init__(self, row=None):
        self._session = _FakeSession(row=row)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_analysis_service_queries_views_through_core_builder() -> None:
    uow = _FakeUow()
    service = AnalysisService(uow)
    program_id = uuid4()

    rows, total = await service._query_view(
        ReadOnlyView("injection_candidates_view", frozenset({"program_id"})),
        program_id,
        limit=50,
        offset=10,
    )

    assert total == 1
    assert rows == [{"program_id": program_id, "candidate": "xss"}]
    assert all(isinstance(statement, Select) for statement, _ in uow._session.executed)
    assert uow._session.executed[1][1] == {
        "program_id": program_id,
        "limit": 50,
        "offset": 10,
    }


@pytest.mark.asyncio
async def test_analysis_service_reads_registered_analysis_kind() -> None:
    program_id = uuid4()
    uow = _FakeUow(
        row={
            "program_id": program_id,
            "host": "example.com",
            "full_url": "https://example.com/search?q=x",
            "path": "/search",
        }
    )
    service = AnalysisService(uow)

    result = await service.get_analysis(
        "injection_candidates",
        program_id=program_id,
        limit=50,
        offset=10,
    )

    assert result.total == 1
    assert result.limit == 50
    assert result.offset == 10
    assert result.items[0].program_id == program_id
    assert "FROM injection_candidates_view" in str(uow._session.executed[1][0])


@pytest.mark.asyncio
async def test_analysis_service_rejects_unknown_analysis_kind() -> None:
    service = AnalysisService(_FakeUow())

    with pytest.raises(ValueError, match="Unknown analysis kind"):
        await service.get_analysis("unknown", program_id=uuid4())
