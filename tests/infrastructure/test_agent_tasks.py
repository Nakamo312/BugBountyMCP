from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from api.application.agent_tasks import (
    AGENT_TASK_PROMPT_MESSAGE_TYPE,
    AgentTaskAgentReplyRequest,
    AgentTaskFollowupRequest,
    AgentTaskMessageKind,
    AgentTaskMessageRole,
    AgentTaskPromptRequest,
    AgentTaskService,
    AgentTaskStatus,
)
from api.infrastructure.adapters.orm import metadata
from api.infrastructure.agent_tasks import AgentTaskStore


class RecordingTaskStore:
    def __init__(self) -> None:
        self.calls = []

    async def create_prompt_task(self, **kwargs):
        self.calls.append(kwargs)
        from api.application.agent_tasks import AgentTaskCreated, AgentTaskMessageRecord, AgentTaskMessageRole, AgentTaskRecord
        now = datetime.now(timezone.utc)
        return AgentTaskCreated(
            task=AgentTaskRecord(
                task_id=kwargs["task_id"],
                program_id=kwargs["request"].program_id,
                campaign_id=kwargs["request"].campaign_id,
                correlation_id=kwargs["request"].correlation_id,
                status=AgentTaskStatus.QUEUED,
                target_agent=kwargs["request"].target_agent,
                title=kwargs["title"],
                prompt_excerpt=kwargs["prompt_excerpt"],
                prompt_hash=kwargs["prompt_hash"],
                created_by=kwargs["request"].created_by,
                source=kwargs["request"].source,
                context_refs=kwargs["sanitized_context_refs"],
                metadata=kwargs["sanitized_metadata"],
                created_at=now,
                updated_at=now,
            ),
            first_message=AgentTaskMessageRecord(
                message_id=kwargs["message_id"],
                task_id=kwargs["task_id"],
                program_id=kwargs["request"].program_id,
                campaign_id=kwargs["request"].campaign_id,
                correlation_id=kwargs["request"].correlation_id,
                role=AgentTaskMessageRole.USER,
                agent_key=kwargs["request"].target_agent,
                body=kwargs["prompt_excerpt"],
                body_hash="0" * 64,
                created_at=now,
            ),
        )

    async def append_followup_message(self, **kwargs):
        self.calls.append(kwargs)
        now = datetime.now(timezone.utc)
        return __import__("api.application.agent_tasks", fromlist=["AgentTaskMessageRecord"]).AgentTaskMessageRecord(
            message_id=kwargs["message_id"],
            task_id=kwargs["task_id"],
            program_id=uuid4(),
            correlation_id=uuid4(),
            role=AgentTaskMessageRole.USER,
            message_kind=AgentTaskMessageKind.NOTE,
            agent_key="coordinator",
            body=kwargs["body"],
            body_hash=kwargs["body_hash"],
            created_at=now,
        )

    async def append_agent_reply(self, **kwargs):
        self.calls.append(kwargs)
        now = datetime.now(timezone.utc)
        return __import__("api.application.agent_tasks", fromlist=["AgentTaskMessageRecord"]).AgentTaskMessageRecord(
            message_id=kwargs["message_id"],
            task_id=kwargs["task_id"],
            program_id=uuid4(),
            correlation_id=uuid4(),
            role=AgentTaskMessageRole.AGENT,
            message_kind=kwargs["request"].message_kind,
            agent_key=kwargs["request"].agent_key,
            body=kwargs["body"],
            body_hash=kwargs["body_hash"],
            artifact_refs=kwargs["sanitized_refs"].get("artifact_refs", []),
            proposal_refs=kwargs["sanitized_refs"].get("proposal_refs", []),
            metadata=kwargs["sanitized_metadata"],
            created_at=now,
        )

    async def list_tasks(self, **kwargs):  # pragma: no cover
        return []

    async def list_task_messages(self, **kwargs):  # pragma: no cover
        return []


@pytest.mark.asyncio
async def test_agent_task_service_sanitizes_prompt_and_enqueues_bounded_message() -> None:
    store = RecordingTaskStore()
    service = AgentTaskService(store)
    request = AgentTaskPromptRequest(
        program_id=uuid4(),
        campaign_id=uuid4(),
        prompt="Проверь ветку account, Authorization: Bearer super-secret-token",
        target_agent="coordinator",
        metadata={"api_key": "secret-value", "note": "keep"},
    )

    created = await service.create_prompt_task(request)

    call = store.calls[0]
    payload = call["inbox_payload"]
    assert created.task.status is AgentTaskStatus.QUEUED
    assert payload["schema_version"] == "agent-task-prompt.v1"
    assert payload["target_agent"] == "coordinator"
    assert payload["boundary"]["tool_execution"] == "forbidden_from_prompt"
    assert "super-secret-token" not in payload["prompt_excerpt"]
    assert payload["metadata"]["api_key"] == "[redacted]"
    assert call["dedupe_key"].startswith("agent-task:")


@pytest.mark.asyncio
async def test_agent_task_followup_enqueues_thread_message_without_tool_execution() -> None:
    store = RecordingTaskStore()
    service = AgentTaskService(store)
    task_id = uuid4()

    message = await service.append_followup_message(
        task_id=task_id,
        request=AgentTaskFollowupRequest(
            body="А теперь объясни, почему это важно. Authorization: Bearer secret",
            metadata={"token": "secret-value"},
        ),
    )

    call = store.calls[0]
    payload = call["inbox_payload"]
    assert message.role is AgentTaskMessageRole.USER
    assert payload["schema_version"] == "agent-task-followup.v1"
    assert payload["boundary"]["tool_execution"] == "forbidden_from_prompt"
    assert "secret" not in payload["body_excerpt"].lower()
    assert payload["metadata"]["token"] == "[redacted]"
    assert call["dedupe_key"].startswith(f"agent-task:{task_id}:followup:")


@pytest.mark.asyncio
async def test_agent_task_agent_reply_records_visible_finding_with_refs() -> None:
    store = RecordingTaskStore()
    service = AgentTaskService(store)
    task_id = uuid4()

    message = await service.append_agent_reply(
        task_id=task_id,
        request=AgentTaskAgentReplyRequest(
            agent_key="artifact-agent",
            message_kind=AgentTaskMessageKind.FINDING,
            status=AgentTaskStatus.WAITING,
            body="Нашёл 9 новых JS-путей, ключ sk-live-secret скрыт.",
            artifact_refs=[{"artifact_id": str(uuid4()), "secret": "must-redact"}],
            proposal_refs=[{"proposal_id": str(uuid4())}],
            metadata={"note": "visible"},
        ),
    )

    call = store.calls[0]
    assert message.role is AgentTaskMessageRole.AGENT
    assert message.message_kind is AgentTaskMessageKind.FINDING
    assert message.agent_key == "artifact-agent"
    assert "JS-путей" in message.body
    assert call["request"].status is AgentTaskStatus.WAITING
    assert message.artifact_refs[0]["secret"] == "[redacted]"
    assert message.proposal_refs
    assert message.metadata["boundary"]["tool_execution"] == "forbidden_from_agent_reply"


def test_agent_task_tables_are_declared_for_visible_prompt_workflow() -> None:
    assert "agent_tasks" in metadata.tables
    assert "agent_task_messages" in metadata.tables
    tasks = metadata.tables["agent_tasks"]
    messages = metadata.tables["agent_task_messages"]

    for column in (
        "program_id",
        "campaign_id",
        "correlation_id",
        "status",
        "target_agent",
        "prompt_excerpt",
        "prompt_hash",
        "inbox_message_id",
    ):
        assert column in tasks.c
    for column in (
        "task_id",
        "role",
        "message_kind",
        "agent_key",
        "body",
        "artifact_refs",
        "fact_refs",
        "graph_refs",
        "action_refs",
        "proposal_refs",
        "decision_refs",
        "metadata",
    ):
        assert column in messages.c
    assert "idx_agent_tasks_program_status_created" in {index.name for index in tasks.indexes}
    assert "idx_agent_task_messages_task_created" in {index.name for index in messages.indexes}


def test_agent_task_migration_extends_internal_proposal_head() -> None:
    source = Path("alembic/versions/o0p1q2r3s4t5_add_agent_prompt_tasks.py").read_text(encoding="utf-8")
    assert 'down_revision = "n9o0p1q2r3s4"' in source
    assert '"agent_tasks"' in source
    assert '"agent_task_messages"' in source
    assert '"agent_inbox.id"' in source


def test_agent_task_live_thread_migration_extends_messages() -> None:
    source = Path("alembic/versions/p1q2r3s4t5u6_extend_agent_task_messages_for_live_threads.py").read_text(encoding="utf-8")
    assert 'down_revision = "o0p1q2r3s4t5"' in source
    assert '"message_kind"' in source
    assert '"proposal_refs"' in source
    assert '"decision_refs"' in source
    assert "ck_agent_task_messages_kind_valid" in source


def test_agent_task_routes_support_followup_and_internal_agent_replies() -> None:
    public_source = Path("src/api/presentation/rest/routes/agent_tasks.py").read_text(encoding="utf-8")
    internal_source = Path("src/api/presentation/rest/routes/agent_protocol.py").read_text(encoding="utf-8")
    assert '"/{task_id}/messages"' in public_source
    assert '@router.post("/tasks/{task_id}/messages"' in internal_source
    assert "AgentTaskAgentReplyRequest" in internal_source
    assert "append_agent_reply" in internal_source


class FakeMappingResult:
    def __init__(self, row=None, scalar=None):
        self.row = row
        self.scalar = scalar

    def mappings(self):
        return self

    def one(self):
        return self.row

    def all(self):
        return [self.row]

    def scalar_one_or_none(self):
        return self.scalar


class FakeSession:
    def __init__(self) -> None:
        self.statements = []
        self.committed = False
        self.task_id = uuid4()
        self.message_id = uuid4()
        self.program_id = uuid4()
        self.campaign_id = uuid4()
        self.correlation_id = uuid4()
        self.inbox_id = uuid4()
        self.now = datetime.now(timezone.utc)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        compiled = str(statement.compile(dialect=postgresql.dialect()))
        if "INSERT INTO agent_tasks" in compiled:
            return FakeMappingResult(
                {
                    "id": self.task_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "correlation_id": self.correlation_id,
                    "status": "queued",
                    "target_agent": "coordinator",
                    "title": "Проверь JavaScript",
                    "prompt_excerpt": "Проверь JavaScript",
                    "prompt_hash": "a" * 64,
                    "created_by": "human",
                    "source": "ui",
                    "context_refs": [],
                    "metadata": {},
                    "inbox_message_id": None,
                    "created_at": self.now,
                    "updated_at": self.now,
                }
            )
        if "INSERT INTO agent_task_messages" in compiled:
            return FakeMappingResult(
                {
                    "id": self.message_id,
                    "task_id": self.task_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "correlation_id": self.correlation_id,
                    "role": "user",
                    "message_kind": "note",
                    "agent_key": "coordinator",
                    "body": "Проверь JavaScript",
                    "body_hash": "b" * 64,
                    "artifact_refs": [],
                    "fact_refs": [],
                    "graph_refs": [],
                    "action_refs": [],
                    "proposal_refs": [],
                    "decision_refs": [],
                    "metadata": {},
                    "created_at": self.now,
                }
            )
        if "INSERT INTO agent_inbox" in compiled:
            return FakeMappingResult(scalar=self.inbox_id)
        return FakeMappingResult()

    async def commit(self):
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self.session


@pytest.mark.asyncio
async def test_agent_task_store_creates_task_message_and_inbox_item() -> None:
    session = FakeSession()
    store = AgentTaskStore(FakeSessionFactory(session))
    request = AgentTaskPromptRequest(
        program_id=session.program_id,
        campaign_id=session.campaign_id,
        correlation_id=session.correlation_id,
        prompt="Проверь JavaScript",
    )

    created = await store.create_prompt_task(
        request=request,
        task_id=session.task_id,
        message_id=session.message_id,
        title="Проверь JavaScript",
        prompt_excerpt="Проверь JavaScript",
        prompt_hash="a" * 64,
        sanitized_context_refs=[],
        sanitized_metadata={},
        inbox_payload={"task_id": str(session.task_id)},
        dedupe_key=f"agent-task:{session.task_id}:prompted",
    )

    assert session.committed is True
    compiled = "\n".join(str(stmt.compile(dialect=postgresql.dialect())) for stmt in session.statements)
    assert "INSERT INTO agent_tasks" in compiled
    assert "INSERT INTO agent_task_messages" in compiled
    assert "INSERT INTO agent_inbox" in compiled
    assert "ON CONFLICT (dedupe_key) DO NOTHING" in compiled
    inbox_params = session.statements[2].compile(dialect=postgresql.dialect()).params
    assert inbox_params["message_type"] == AGENT_TASK_PROMPT_MESSAGE_TYPE
    assert created.inbox_message_id == session.inbox_id
