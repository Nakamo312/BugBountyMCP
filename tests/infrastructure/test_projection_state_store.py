from __future__ import annotations

from uuid import uuid4

from api.application.projections import ProjectionKey
from api.infrastructure.projections import ProjectionStateStore


class FakeResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.rows)


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self.session


async def test_projection_state_store_returns_only_requested_state_shape() -> None:
    program_id = uuid4()
    session = FakeSession(
        [
            {
                "projection_type": "opensearch",
                "projection_name": "http-observations",
                "status": "ready",
                "source_watermark": "42",
                "applied_watermark": "42",
                "lag_count": 0,
            }
        ]
    )
    store = ProjectionStateStore(FakeSessionFactory(session))

    states = await store.list_states(
        program_id=program_id,
        required=[ProjectionKey("opensearch", "http-observations")],
    )

    assert len(states) == 1
    assert states[0].key == ProjectionKey("opensearch", "http-observations")
    assert states[0].status == "ready"
    assert states[0].lag_count == 0
    sql = str(session.statements[0])
    assert "projection_watermarks.program_id" in sql
    assert "projection_watermarks.projection_type" in sql
    assert "projection_watermarks.projection_name" in sql
