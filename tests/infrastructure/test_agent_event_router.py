from __future__ import annotations

from uuid import uuid4

from api.application.contracts import EventEnvelope
from api.infrastructure.agent_coordination import AgentEventRouter


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


class RecordingInboxStore:
    def __init__(self) -> None:
        self.messages = []

    async def enqueue_once(self, message):
        self.messages.append(message)
        return uuid4()


async def test_agent_event_router_delivers_matching_event_to_agent_inbox() -> None:
    program_id = uuid4()
    campaign_id = uuid4()
    correlation_id = uuid4()
    workflow_id = uuid4()
    workflow_run_id = uuid4()
    subscription_id = uuid4()
    session = FakeSession(
        [
            {
                "id": subscription_id,
                "workflow_id": workflow_id,
                "workflow_run_id": workflow_run_id,
                "program_id": program_id,
                "campaign_id": campaign_id,
                "correlation_id": correlation_id,
                "event_type": "run.completed",
            }
        ]
    )
    inbox = RecordingInboxStore()
    router = AgentEventRouter(FakeSessionFactory(session), inbox)
    event = EventEnvelope(
        event="run.completed",
        program_id=program_id,
        correlation_id=correlation_id,
        payload={"campaign_id": str(campaign_id), "workflow_id": str(workflow_id)},
    )

    delivered = await router.route_event(event)

    assert delivered == 1
    message = inbox.messages[0]
    assert message.subscription_id == subscription_id
    assert message.workflow_id == workflow_id
    assert message.workflow_run_id == workflow_run_id
    assert message.program_id == program_id
    assert message.campaign_id == campaign_id
    assert message.correlation_id == correlation_id
    assert message.event_id == event.event_id
    assert message.message_type == "run.completed"
    assert message.dedupe_key == f"event:{event.event_id}:subscription:{subscription_id}"


async def test_agent_event_router_ignores_events_without_matching_subscription() -> None:
    session = FakeSession([])
    inbox = RecordingInboxStore()
    router = AgentEventRouter(FakeSessionFactory(session), inbox)
    event = EventEnvelope(event="irrelevant", program_id=uuid4())

    delivered = await router.route_event(event)

    assert delivered == 0
    assert inbox.messages == []
