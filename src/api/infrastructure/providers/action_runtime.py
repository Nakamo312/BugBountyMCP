from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.application.execution_limits import system_execution_budget
from api.application.ports.action import (
    ActionApprovalPort,
    ActionCommandPort,
    ActionQueryPort,
    ActionResultPort,
)
from api.application.ports.orchestration import (
    EventDispatchStorePort,
    EventRecorderPort,
    PipelineOrchestrationStorePort,
    PipelineRunStatePort,
)
from api.application.services.action import ActionService
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.policy import PolicyService
from api.config import Settings
from api.application.action_outcomes import ActionOutcomeRecorder
from api.infrastructure.action_outcomes import ActionOutcomeStore
from api.infrastructure.orchestration.action_command_store import ActionCommandStore
from api.infrastructure.orchestration.action_read_store import ActionReadStore
from api.infrastructure.orchestration.approval_store import ApprovalStore
from api.infrastructure.orchestration.campaign_state_store import CampaignStateStore
from api.infrastructure.orchestration.dispatch_store import DispatchStore
from api.infrastructure.orchestration.event_store import EventStore
from api.infrastructure.orchestration.pipeline_store import PipelineOrchestrationStore
from api.infrastructure.orchestration.run_claim_store import RunClaimStore
from api.infrastructure.orchestration.run_state_store import RunStateStore
from api.infrastructure.orchestration.scheduled_work_store import ScheduledWorkStore
from api.infrastructure.repositories.adapters.scope_rule import SQLAlchemyScopeRuleRepository
from api.infrastructure.runtime_manifest import ManifestActivator
from api.infrastructure.tool_catalog.store import SqlActionCatalogStore


class ActionRuntimeProvider(Provider):
    scope = Scope.APP

    @provide(scope=Scope.APP)
    def get_campaign_state_store(
        self,
        session_factory: async_sessionmaker,
        settings: Settings,
    ) -> CampaignStateStore:
        return CampaignStateStore(session_factory, settings)

    @provide(scope=Scope.APP)
    def get_dispatch_store(
        self,
        session_factory: async_sessionmaker,
        settings: Settings,
    ) -> DispatchStore:
        return DispatchStore(session_factory, settings)

    @provide(scope=Scope.APP)
    def get_scheduled_work_store(self, session_factory: async_sessionmaker) -> ScheduledWorkStore:
        return ScheduledWorkStore(session_factory)

    @provide(scope=Scope.APP)
    def get_event_store(self, session_factory: async_sessionmaker) -> EventStore:
        return EventStore(session_factory)

    @provide(scope=Scope.APP)
    def get_run_claim_store(self, session_factory: async_sessionmaker) -> RunClaimStore:
        return RunClaimStore(session_factory)

    @provide(scope=Scope.APP)
    def get_run_state_store(self, session_factory: async_sessionmaker) -> RunStateStore:
        return RunStateStore(session_factory)

    @provide(scope=Scope.APP)
    def get_action_read_store(self, session_factory: async_sessionmaker) -> ActionReadStore:
        return ActionReadStore(session_factory)

    @provide(scope=Scope.APP)
    def get_action_command_store(
        self,
        session_factory: async_sessionmaker,
        campaign_state_store: CampaignStateStore,
        dispatch_store: DispatchStore,
    ) -> ActionCommandStore:
        return ActionCommandStore(
            session_factory,
            campaigns=campaign_state_store,
            dispatches=dispatch_store,
        )

    @provide(scope=Scope.APP)
    def get_approval_store(
        self,
        session_factory: async_sessionmaker,
        campaign_state_store: CampaignStateStore,
        dispatch_store: DispatchStore,
    ) -> ApprovalStore:
        return ApprovalStore(
            session_factory,
            campaigns=campaign_state_store,
            dispatches=dispatch_store,
        )

    @provide(scope=Scope.APP)
    def get_action_command_port(
        self,
        action_command_store: ActionCommandStore,
    ) -> ActionCommandPort:
        return action_command_store

    @provide(scope=Scope.APP)
    def get_action_query_port(
        self,
        action_read_store: ActionReadStore,
    ) -> ActionQueryPort:
        return action_read_store

    @provide(scope=Scope.APP)
    def get_action_result_port(
        self,
        action_read_store: ActionReadStore,
    ) -> ActionResultPort:
        return action_read_store

    @provide(scope=Scope.APP)
    def get_action_approval_port(
        self,
        approval_store: ApprovalStore,
    ) -> ActionApprovalPort:
        return approval_store

    @provide(scope=Scope.APP)
    def get_pipeline_orchestration_store_port(
        self,
        run_claim_store: RunClaimStore,
        scheduled_work_store: ScheduledWorkStore,
        run_state_store: RunStateStore,
    ) -> PipelineOrchestrationStorePort:
        return PipelineOrchestrationStore(
            run_claims=run_claim_store,
            scheduled_work=scheduled_work_store,
            run_states=run_state_store,
        )

    @provide(scope=Scope.APP)
    def get_pipeline_run_state_port(
        self,
        run_state_store: RunStateStore,
    ) -> PipelineRunStatePort:
        return run_state_store

    @provide(scope=Scope.APP)
    def get_event_recorder_port(
        self,
        event_store: EventStore,
    ) -> EventRecorderPort:
        return event_store

    @provide(scope=Scope.APP)
    def get_event_dispatch_store_port(
        self,
        dispatch_store: DispatchStore,
    ) -> EventDispatchStorePort:
        return dispatch_store

    @provide(scope=Scope.APP)
    def get_action_outcome_store(
        self,
        session_factory: async_sessionmaker,
    ) -> ActionOutcomeStore:
        return ActionOutcomeStore(session_factory)

    @provide(scope=Scope.APP)
    def get_action_outcome_recorder(
        self,
        store: ActionOutcomeStore,
    ) -> ActionOutcomeRecorder:
        return ActionOutcomeRecorder(store)

    @provide(scope=Scope.APP)
    def get_manifest_activator(self, session_factory: async_sessionmaker) -> ManifestActivator:
        return ManifestActivator(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_action_catalog_store(self, session_factory: async_sessionmaker) -> SqlActionCatalogStore:
        return SqlActionCatalogStore(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_action_catalog_service(self, catalog_store: SqlActionCatalogStore) -> ActionCatalogService:
        return ActionCatalogService(catalog_store)

    @provide(scope=Scope.REQUEST)
    def get_policy_service(self) -> PolicyService:
        return PolicyService()

    @provide(scope=Scope.REQUEST)
    def get_scope_rule_repository(self, session: AsyncSession) -> SQLAlchemyScopeRuleRepository:
        return SQLAlchemyScopeRuleRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_action_service(
        self,
        settings: Settings,
        action_commands: ActionCommandPort,
        action_queries: ActionQueryPort,
        action_results: ActionResultPort,
        action_approvals: ActionApprovalPort,
        policy_service: PolicyService,
        catalog_service: ActionCatalogService,
        scope_rule_repository: SQLAlchemyScopeRuleRepository,
        action_outcome_recorder: ActionOutcomeRecorder,
    ) -> ActionService:
        return ActionService(
            commands=action_commands,
            queries=action_queries,
            results=action_results,
            approvals=action_approvals,
            policy=policy_service,
            catalog=catalog_service,
            scope_rules=scope_rule_repository,
            outcome_feedback=action_outcome_recorder,
            system_budget=system_execution_budget(settings),
        )
