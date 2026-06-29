from __future__ import annotations

from uuid import uuid4

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from api.application.hypotheses import HypothesisBuildRequest
from api.application.research_control_graph import ResearchControlGraph
from api.application.research_pass import ResearchPassResult


pytestmark = pytest.mark.integration


class EmptyResearchWorkflow:
    async def run(self, request: HypothesisBuildRequest) -> ResearchPassResult:
        return ResearchPassResult(items=())


async def test_langgraph_checkpoint_round_trip_uses_migrated_postgres_schema(
    integration_postgres_async_url: str,
    migrated_postgres,
) -> None:
    connection_url = integration_postgres_async_url.replace(
        "postgresql+asyncpg://",
        "postgresql://",
    )
    thread_id = str(uuid4())
    program_id = uuid4()

    async with AsyncPostgresSaver.from_conn_string(
        connection_url,
        serde=JsonPlusSerializer(allowed_msgpack_modules=()),
    ) as checkpointer:
        graph = ResearchControlGraph(
            research_workflow=EmptyResearchWorkflow(),
            checkpointer=checkpointer,
        )
        result = await graph.ainvoke(
            HypothesisBuildRequest(program_id=program_id),
            thread_id=thread_id,
        )
        restored = await graph.aget_state(thread_id=thread_id)

    assert restored.values == result
    assert restored.values["program_id"] == str(program_id)
    assert restored.values["hypothesis_ids"] == []
    assert restored.values["finding_ids"] == []
