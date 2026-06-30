from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.action_experience_proposals import (
    ActionExperienceProposalAcceptanceService,
    ActionExperienceProposalReviewService,
)
from api.application.agent_action_proposals import (
    AgentActionProposalAcceptanceService,
    AgentActionProposalReviewService,
    AgentActionProposalService,
)
from api.application.agent_task_runtime_contracts import AgentTaskRuntime
from api.application.agent_task_langgraph_runtime import AgentTaskRuntimeFactory
from api.application.agent_task_runtime_results import AgentTaskRuntimeResultIngestService
from api.application.agent_tasks import AgentTaskService
from api.application.services.action import ActionService
from api.application.services.action_catalog import ActionCatalogService
from api.config import Settings
from api.infrastructure.action_experience_proposals import ActionExperienceProposalStore
from api.infrastructure.agent_action_proposals import AgentActionProposalStore
from api.infrastructure.agent_coordination import AgentEventRouter, AgentInboxStore, AgentProtocolStore
from api.infrastructure.agent_task_context import PostgresAgentTaskContextReader
from api.infrastructure.agent_tasks import AgentTaskStore


class AgentRuntimeProvider(Provider):
    scope = Scope.APP

    @provide(scope=Scope.APP)
    def get_agent_inbox_store(self, session_factory: async_sessionmaker) -> AgentInboxStore:
        return AgentInboxStore(session_factory)

    @provide(scope=Scope.APP)
    def get_agent_event_router(
        self,
        session_factory: async_sessionmaker,
        agent_inbox_store: AgentInboxStore,
    ) -> AgentEventRouter:
        return AgentEventRouter(session_factory, agent_inbox_store)

    @provide(scope=Scope.APP)
    def get_agent_protocol_store(self, session_factory: async_sessionmaker) -> AgentProtocolStore:
        return AgentProtocolStore(session_factory)

    @provide(scope=Scope.APP)
    def get_agent_task_store(self, session_factory: async_sessionmaker) -> AgentTaskStore:
        return AgentTaskStore(session_factory)

    @provide(scope=Scope.APP)
    def get_agent_action_proposal_store(self, session_factory: async_sessionmaker) -> AgentActionProposalStore:
        return AgentActionProposalStore(session_factory)

    @provide(scope=Scope.APP)
    def get_action_experience_proposal_store(self, session_factory: async_sessionmaker) -> ActionExperienceProposalStore:
        return ActionExperienceProposalStore(session_factory)

    @provide(scope=Scope.APP)
    def get_agent_action_proposal_service(
        self,
        store: AgentActionProposalStore,
    ) -> AgentActionProposalService:
        return AgentActionProposalService(store)

    @provide(scope=Scope.REQUEST)
    def get_agent_action_proposal_acceptance_service(
        self,
        store: AgentActionProposalStore,
        action_service: ActionService,
        catalog_service: ActionCatalogService,
        task_service: AgentTaskService,
    ) -> AgentActionProposalAcceptanceService:
        return AgentActionProposalAcceptanceService(
            store=store,
            action_service=action_service,
            catalog_service=catalog_service,
            task_thread=task_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_agent_action_proposal_review_service(
        self,
        store: AgentActionProposalStore,
        task_service: AgentTaskService,
    ) -> AgentActionProposalReviewService:
        return AgentActionProposalReviewService(store=store, task_thread=task_service)

    @provide(scope=Scope.REQUEST)
    def get_action_experience_proposal_acceptance_service(
        self,
        store: ActionExperienceProposalStore,
        action_service: ActionService,
        catalog_service: ActionCatalogService,
    ) -> ActionExperienceProposalAcceptanceService:
        return ActionExperienceProposalAcceptanceService(
            store=store,
            action_service=action_service,
            catalog_service=catalog_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_action_experience_proposal_review_service(
        self,
        store: ActionExperienceProposalStore,
    ) -> ActionExperienceProposalReviewService:
        return ActionExperienceProposalReviewService(store=store)

    @provide(scope=Scope.REQUEST)
    def get_agent_task_service(self, store: AgentTaskStore) -> AgentTaskService:
        return AgentTaskService(store)

    @provide(scope=Scope.REQUEST)
    def get_agent_task_runtime_result_ingest_service(
        self,
        task_service: AgentTaskService,
        proposal_service: AgentActionProposalService,
        agent_protocol_store: AgentProtocolStore,
    ) -> AgentTaskRuntimeResultIngestService:
        return AgentTaskRuntimeResultIngestService(
            task_service=task_service,
            proposal_writer=proposal_service,
            ack_store=agent_protocol_store,
        )

    @provide(scope=Scope.APP)
    def get_agent_task_runtime(
        self,
        settings: Settings,
        session_factory: async_sessionmaker,
    ) -> AgentTaskRuntime:
        return AgentTaskRuntimeFactory(
            runtime_name=settings.AGENT_TASK_RUNTIME,
            default_budget_mode=settings.AGENT_TASK_RUNTIME_DEFAULT_MODE,
            allow_deep_budget_mode=settings.AGENT_TASK_RUNTIME_ALLOW_DEEP,
            require_deep_confirmation=settings.AGENT_TASK_RUNTIME_REQUIRE_DEEP_CONFIRMATION,
            deep_allowed_actors=settings.AGENT_TASK_RUNTIME_DEEP_ALLOWED_ACTORS,
            langgraph_checkpoint_ns=settings.AGENT_TASK_LANGGRAPH_CHECKPOINT_NS,
            context_reader=PostgresAgentTaskContextReader(
                session_factory=session_factory,
                max_request_context_refs=settings.AGENT_TASK_CONTEXT_REF_LIMIT,
                max_thread_messages=settings.AGENT_TASK_CONTEXT_THREAD_MESSAGE_LIMIT,
                max_recent_outcomes=settings.AGENT_TASK_CONTEXT_RECENT_OUTCOME_LIMIT,
                max_pending_proposals=settings.AGENT_TASK_CONTEXT_PENDING_PROPOSAL_LIMIT,
                max_surface_samples=settings.AGENT_TASK_CONTEXT_SURFACE_SAMPLE_LIMIT,
            ),
        ).create()
