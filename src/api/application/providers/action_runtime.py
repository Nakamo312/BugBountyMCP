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
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.orchestration.store import OrchestrationStore
from api.infrastructure.repositories.adapters.scope_rule import SQLAlchemyScopeRuleRepository
from api.infrastructure.runtime_manifest import ManifestActivator
from api.infrastructure.tool_catalog.store import SqlActionCatalogStore


class ActionRuntimeProvider(Provider):
    scope = Scope.APP

    @provide(scope=Scope.APP)
    def get_orchestration_store(
        self,
        session_factory: async_sessionmaker,
        settings: Settings,
    ) -> OrchestrationStore:
        return OrchestrationStore(session_factory, settings)

    @provide(scope=Scope.APP)
    def get_action_command_port(
        self,
        orchestration_store: OrchestrationStore,
    ) -> ActionCommandPort:
        return orchestration_store

    @provide(scope=Scope.APP)
    def get_action_query_port(
        self,
        orchestration_store: OrchestrationStore,
    ) -> ActionQueryPort:
        return orchestration_store

    @provide(scope=Scope.APP)
    def get_action_result_port(
        self,
        orchestration_store: OrchestrationStore,
    ) -> ActionResultPort:
        return orchestration_store

    @provide(scope=Scope.APP)
    def get_action_approval_port(
        self,
        orchestration_store: OrchestrationStore,
    ) -> ActionApprovalPort:
        return orchestration_store

    @provide(scope=Scope.APP)
    def get_pipeline_orchestration_store_port(
        self,
        orchestration_store: OrchestrationStore,
    ) -> PipelineOrchestrationStorePort:
        return orchestration_store

    @provide(scope=Scope.APP)
    def get_pipeline_run_state_port(
        self,
        orchestration_store: OrchestrationStore,
    ) -> PipelineRunStatePort:
        return orchestration_store

    @provide(scope=Scope.APP)
    def get_event_recorder_port(
        self,
        orchestration_store: OrchestrationStore,
    ) -> EventRecorderPort:
        return orchestration_store

    @provide(scope=Scope.APP)
    def get_event_dispatch_store_port(
        self,
        orchestration_store: OrchestrationStore,
    ) -> EventDispatchStorePort:
        return orchestration_store

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
