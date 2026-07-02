from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.application.execution_limits import system_execution_budget
from api.application.ports.action import (
    ActionControlPort,
    ActionPolicyResultWriter,
    ActionQueryPort,
    ActionResultPort,
    AllowedActionQueueWriter,
    ApprovalDecisionWriter,
    ApprovalRequestReader,
)
from api.application.ports.orchestration import (
    EventDispatchLeasePort,
    EventRecorderPort,
    NodeRunClaimPort,
    PipelineRunStatePort,
    ScheduledLeasePort,
    ScheduledRecoveryPort,
    ScheduledRetryPort,
)
from api.application.services.action import ActionService
from api.application.services.action_composition import build_action_service
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.policy import PolicyService
from api.config import Settings
from api.application.action_outcomes import ActionOutcomeRecorder
from api.infrastructure.action_outcomes import ActionOutcomeStore
from api.infrastructure.orchestration.action_control_store import ActionControlStore
from api.infrastructure.orchestration.action_policy_result_store import ActionPolicyResultStore
from api.infrastructure.orchestration.allowed_action_queue_store import AllowedActionQueueStore
from api.infrastructure.orchestration.action_read_store import ActionReadStore
from api.infrastructure.orchestration.approval_decision_store import ApprovalDecisionStore
from api.infrastructure.orchestration.approval_request_store import ApprovalRequestStore
from api.infrastructure.orchestration.campaign_write_store import CampaignWriteStore
from api.infrastructure.orchestration.dispatch_leasing import DispatchLeaseStore
from api.infrastructure.orchestration.dispatch_writer import DispatchWriterStore
from api.infrastructure.orchestration.event_store import EventStore
from api.infrastructure.orchestration.run_claim_store import RunClaimStore
from api.infrastructure.orchestration.run_state_store import RunStateStore
from api.infrastructure.orchestration.scheduled_leasing import ScheduledLeaseStore
from api.infrastructure.orchestration.scheduled_recovery import ScheduledRecoveryStore
from api.infrastructure.orchestration.scheduled_retry import ScheduledRetryStore
from api.infrastructure.repositories.adapters.scope_rule import SQLAlchemyScopeRuleRepository
from api.infrastructure.runtime_manifest import ManifestActivator
from api.infrastructure.tool_catalog.store import SqlActionCatalogStore


class ActionRuntimeProvider(Provider):
    scope = Scope.APP

    @provide(scope=Scope.APP)
    def get_campaign_write_store(
        self,
        settings: Settings,
    ) -> CampaignWriteStore:
        return CampaignWriteStore(settings)

    @provide(scope=Scope.APP)
    def get_dispatch_writer_store(
        self,
        settings: Settings,
    ) -> DispatchWriterStore:
        return DispatchWriterStore(settings)

    @provide(scope=Scope.APP)
    def get_dispatch_lease_store(
        self,
        session_factory: async_sessionmaker,
    ) -> DispatchLeaseStore:
        return DispatchLeaseStore(session_factory)

    @provide(scope=Scope.APP)
    def get_scheduled_lease_store(
        self,
        session_factory: async_sessionmaker,
    ) -> ScheduledLeaseStore:
        return ScheduledLeaseStore(session_factory)

    @provide(scope=Scope.APP)
    def get_scheduled_recovery_store(
        self,
        session_factory: async_sessionmaker,
    ) -> ScheduledRecoveryStore:
        return ScheduledRecoveryStore(session_factory)

    @provide(scope=Scope.APP)
    def get_scheduled_retry_store(
        self,
        session_factory: async_sessionmaker,
    ) -> ScheduledRetryStore:
        return ScheduledRetryStore(session_factory)

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
    def get_action_control_store(self, session_factory: async_sessionmaker) -> ActionControlStore:
        return ActionControlStore(session_factory)

    @provide(scope=Scope.APP)
    def get_action_policy_result_store(
        self,
        session_factory: async_sessionmaker,
        campaign_write_store: CampaignWriteStore,
    ) -> ActionPolicyResultStore:
        return ActionPolicyResultStore(
            session_factory,
            campaigns=campaign_write_store,
        )

    @provide(scope=Scope.APP)
    def get_allowed_action_queue_store(
        self,
        session_factory: async_sessionmaker,
        campaign_write_store: CampaignWriteStore,
        dispatch_writer: DispatchWriterStore,
    ) -> AllowedActionQueueStore:
        return AllowedActionQueueStore(
            session_factory,
            campaigns=campaign_write_store,
            dispatches=dispatch_writer,
        )

    @provide(scope=Scope.APP)
    def get_action_control_port(
        self,
        action_control_store: ActionControlStore,
    ) -> ActionControlPort:
        return action_control_store

    @provide(scope=Scope.APP)
    def get_action_policy_result_writer(
        self,
        action_policy_result_store: ActionPolicyResultStore,
    ) -> ActionPolicyResultWriter:
        return action_policy_result_store

    @provide(scope=Scope.APP)
    def get_allowed_action_queue_writer(
        self,
        allowed_action_queue_store: AllowedActionQueueStore,
    ) -> AllowedActionQueueWriter:
        return allowed_action_queue_store

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
    def get_approval_request_store(
        self,
        session_factory: async_sessionmaker,
    ) -> ApprovalRequestStore:
        return ApprovalRequestStore(session_factory)

    @provide(scope=Scope.APP)
    def get_approval_decision_store(
        self,
        session_factory: async_sessionmaker,
        campaign_write_store: CampaignWriteStore,
        dispatch_writer: DispatchWriterStore,
    ) -> ApprovalDecisionStore:
        return ApprovalDecisionStore(
            session_factory,
            campaigns=campaign_write_store,
            dispatches=dispatch_writer,
        )

    @provide(scope=Scope.APP)
    def get_approval_request_reader(
        self,
        approval_request_store: ApprovalRequestStore,
    ) -> ApprovalRequestReader:
        return approval_request_store

    @provide(scope=Scope.APP)
    def get_approval_decision_writer(
        self,
        approval_decision_store: ApprovalDecisionStore,
    ) -> ApprovalDecisionWriter:
        return approval_decision_store

    @provide(scope=Scope.APP)
    def get_node_run_claim_port(
        self,
        run_claim_store: RunClaimStore,
    ) -> NodeRunClaimPort:
        return run_claim_store

    @provide(scope=Scope.APP)
    def get_scheduled_lease_port(
        self,
        scheduled_lease_store: ScheduledLeaseStore,
    ) -> ScheduledLeasePort:
        return scheduled_lease_store

    @provide(scope=Scope.APP)
    def get_scheduled_recovery_port(
        self,
        scheduled_recovery_store: ScheduledRecoveryStore,
    ) -> ScheduledRecoveryPort:
        return scheduled_recovery_store

    @provide(scope=Scope.APP)
    def get_scheduled_retry_port(
        self,
        scheduled_retry_store: ScheduledRetryStore,
    ) -> ScheduledRetryPort:
        return scheduled_retry_store

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
    def get_event_dispatch_lease_port(
        self,
        dispatch_lease_store: DispatchLeaseStore,
    ) -> EventDispatchLeasePort:
        return dispatch_lease_store

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
        action_policy_results: ActionPolicyResultWriter,
        allowed_action_queue: AllowedActionQueueWriter,
        action_queries: ActionQueryPort,
        action_results: ActionResultPort,
        action_controls: ActionControlPort,
        approval_requests: ApprovalRequestReader,
        approval_decisions: ApprovalDecisionWriter,
        policy_service: PolicyService,
        catalog_service: ActionCatalogService,
        scope_rule_repository: SQLAlchemyScopeRuleRepository,
        action_outcome_recorder: ActionOutcomeRecorder,
    ) -> ActionService:
        return build_action_service(
            policy_results=action_policy_results,
            allowed_actions=allowed_action_queue,
            queries=action_queries,
            results=action_results,
            controls=action_controls,
            approval_requests=approval_requests,
            approval_decisions=approval_decisions,
            policy=policy_service,
            catalog=catalog_service,
            scope_rules=scope_rule_repository,
            outcome_feedback=action_outcome_recorder,
            system_budget=system_execution_budget(settings),
        )
