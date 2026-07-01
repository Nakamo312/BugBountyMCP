from uuid import uuid4

import pytest
from sqlalchemy.sql import Select

from api.application.read_only_views import ReadOnlyView
from api.infrastructure.read_only_view_queries import view_count_query, view_data_query
from api.infrastructure.read_only_view_reader import SQLAlchemyReadOnlyViewReader


def test_read_only_view_queries_compile_to_core_selects() -> None:
    view = ReadOnlyView("injection_candidates_view", frozenset({"program_id"}))
    filters = {"program_id": uuid4()}

    count_query = view_count_query(view, filters)
    data_query = view_data_query(view, filters)

    assert isinstance(count_query, Select)
    assert isinstance(data_query, Select)
    assert "FROM injection_candidates_view" in str(count_query)
    assert "WHERE program_id = :program_id" in str(data_query)


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
async def test_sqlalchemy_read_only_view_reader_pages_views() -> None:
    uow = _FakeUow()
    reader = SQLAlchemyReadOnlyViewReader(uow)
    program_id = uuid4()

    page = await reader.page_view_rows(
        ReadOnlyView("injection_candidates_view", frozenset({"program_id"})),
        {"program_id": program_id},
        limit=50,
        offset=10,
    )

    assert page.total == 1
    assert page.rows == [{"program_id": program_id, "candidate": "xss"}]
    assert all(isinstance(statement, Select) for statement, _ in uow._session.executed)
    assert uow._session.executed[1][1] == {
        "program_id": program_id,
        "limit": 50,
        "offset": 10,
    }
