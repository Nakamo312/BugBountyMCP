from typing import AsyncIterable

from dishka import AsyncContainer, Provider, Scope, provide
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.agent_wait_conditions import (
    AgentWaitConditionEngine,
    AgentWaitConditionProcessor,
    CampaignLifecycleReader,
    CampaignLifecycleReconciler,
)
from api.application.cypher_gateway import CypherGateway
from api.application.hypotheses import HypothesisBuilderWorkflow
from api.application.hypothesis_critic import HypothesisCriticWorkflow, ProgramBoundaryScopeReader
from api.application.langgraph_approval import LangGraphApprovalNode
from api.application.langgraph_context_tools import LangGraphContextTools
from api.application.langgraph_tool_action import LangGraphToolActionTool
from api.application.langgraph_workflows import LangGraphWorkflowRuntime
from api.application.report_drafts import ReportDraftBuilderWorkflow
from api.application.research_control_graph import ResearchControlGraph
from api.application.research_inbox_processor import ResearchInboxProcessor
from api.application.research_pass import ResearchPass
from api.application.research_readiness import ResearchReadinessGate
from api.application.services.action import ActionService
from api.config import Settings
from api.infrastructure.agent_coordination import AgentProtocolStore, AgentWaitConditionStore, LangGraphWorkflowStore
from api.infrastructure.agent_wait_state import AgentExecutionStateReader
from api.infrastructure.artifacts.postgres_reader import PostgresArtifactReader
from api.infrastructure.artifacts.raw_artifact_repository import RawArtifactRepository
from api.infrastructure.cypher_gateway import CypherGatewayAuditStore, Neo4jReadExecutor
from api.infrastructure.hypotheses import HypothesisStore
from api.infrastructure.langgraph_context import (
    ArtifactPreviewAdapter,
    ArtifactProgramContextAdapter,
    OpenSearchSanitizedSearchReader,
    SafeGraphTemplateRenderer,
)
from api.infrastructure.langgraph_resume import ResearchWaitResumer
from api.infrastructure.orchestration.campaign_state_store import CampaignStateStore
from api.infrastructure.projections import ProjectionStateStore


class ResearchRuntimeProvider(Provider):
    scope = Scope.APP

    @provide(scope=Scope.APP)
    def get_projection_state_store(
        self,
        session_factory: async_sessionmaker,
    ) -> ProjectionStateStore:
        return ProjectionStateStore(session_factory)

    @provide(scope=Scope.APP)
    def get_campaign_lifecycle_reader(
        self,
        campaign_state_store: CampaignStateStore,
    ) -> CampaignLifecycleReader:
        return campaign_state_store

    @provide(scope=Scope.APP)
    def get_campaign_lifecycle_reconciler(
        self,
        campaign_state_store: CampaignStateStore,
    ) -> CampaignLifecycleReconciler:
        return campaign_state_store

    @provide(scope=Scope.APP)
    def get_agent_wait_condition_engine(
        self,
        settings: Settings,
        projection_reader: ProjectionStateStore,
        result_set_reader: AgentProtocolStore,
        execution_state_reader: AgentExecutionStateReader,
        campaign_lifecycle_reader: CampaignLifecycleReader,
    ) -> AgentWaitConditionEngine:
        return AgentWaitConditionEngine(
            projection_reader=projection_reader,
            result_set_reader=result_set_reader,
            execution_state_reader=execution_state_reader,
            campaign_lifecycle_reader=campaign_lifecycle_reader,
            campaign_quiet_window_seconds=(
                settings.CAMPAIGN_QUIESCENCE_WINDOW_SECONDS
            ),
        )

    @provide(scope=Scope.APP)
    def get_agent_execution_state_reader(
        self,
        session_factory: async_sessionmaker,
    ) -> AgentExecutionStateReader:
        return AgentExecutionStateReader(session_factory)

    @provide(scope=Scope.APP)
    def get_agent_wait_condition_store(
        self,
        session_factory: async_sessionmaker,
    ) -> AgentWaitConditionStore:
        return AgentWaitConditionStore(session_factory)

    @provide(scope=Scope.APP)
    def get_research_wait_resumer(
        self,
        container: AsyncContainer,
        protocol_store: AgentProtocolStore,
    ) -> ResearchWaitResumer:
        return ResearchWaitResumer(
            container=container,
            workflow_status_reader=protocol_store,
        )

    @provide(scope=Scope.APP)
    def get_agent_wait_condition_processor(
        self,
        settings: Settings,
        store: AgentWaitConditionStore,
        engine: AgentWaitConditionEngine,
        workflow_resumer: ResearchWaitResumer,
        campaign_lifecycle_reconciler: CampaignLifecycleReconciler,
    ) -> AgentWaitConditionProcessor:
        return AgentWaitConditionProcessor(
            store=store,
            engine=engine,
            workflow_resumer=workflow_resumer,
            campaign_lifecycle_reconciler=campaign_lifecycle_reconciler,
            campaign_quiet_window_seconds=(
                settings.CAMPAIGN_QUIESCENCE_WINDOW_SECONDS
            ),
            sweep_interval_seconds=settings.AGENT_WAIT_SWEEP_INTERVAL_SECONDS,
        )

    @provide(scope=Scope.APP)
    def get_research_inbox_processor(
        self,
        settings: Settings,
        container: AsyncContainer,
        protocol_store: AgentProtocolStore,
    ) -> ResearchInboxProcessor:
        return ResearchInboxProcessor(
            container=container,
            inbox_store=protocol_store,
            consumer_id=settings.AGENT_INBOX_CONSUMER_ID,
            inbox_key=settings.AGENT_INBOX_KEY,
            claim_limit=settings.AGENT_INBOX_CLAIM_LIMIT,
            lease_seconds=settings.AGENT_INBOX_LEASE_SECONDS,
            sweep_interval_seconds=settings.AGENT_INBOX_SWEEP_INTERVAL_SECONDS,
        )

    @provide(scope=Scope.REQUEST)
    def get_research_readiness_gate(
        self,
        wait_engine: AgentWaitConditionEngine,
        protocol_store: AgentProtocolStore,
        workflow_runtime: LangGraphWorkflowRuntime,
    ) -> ResearchReadinessGate:
        return ResearchReadinessGate(
            wait_engine=wait_engine,
            protocol_store=protocol_store,
            workflow_runtime=workflow_runtime,
        )

    @provide(scope=Scope.REQUEST)
    def get_langgraph_workflow_store(self, session_factory: async_sessionmaker) -> LangGraphWorkflowStore:
        return LangGraphWorkflowStore(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_langgraph_workflow_runtime(
        self,
        store: LangGraphWorkflowStore,
    ) -> LangGraphWorkflowRuntime:
        return LangGraphWorkflowRuntime(store)

    @provide(scope=Scope.APP)
    async def get_langgraph_checkpointer(
        self,
        settings: Settings,
    ) -> AsyncIterable[AsyncPostgresSaver]:
        serializer = JsonPlusSerializer(allowed_msgpack_modules=())
        async with AsyncPostgresSaver.from_conn_string(
            settings.postgres_asyncpg_dsn,
            serde=serializer,
        ) as checkpointer:
            yield checkpointer

    @provide(scope=Scope.REQUEST)
    def get_langgraph_tool_action_tool(
        self,
        action_service: ActionService,
    ) -> LangGraphToolActionTool:
        return LangGraphToolActionTool(action_service=action_service)

    @provide(scope=Scope.REQUEST)
    def get_langgraph_approval_node(
        self,
        tool: LangGraphToolActionTool,
        action_service: ActionService,
        workflow_runtime: LangGraphWorkflowRuntime,
    ) -> LangGraphApprovalNode:
        return LangGraphApprovalNode(
            tool=tool,
            approval_service=action_service,
            workflow_runtime=workflow_runtime,
        )

    @provide(scope=Scope.REQUEST)
    def get_raw_artifact_repository(self, session_factory: async_sessionmaker) -> RawArtifactRepository:
        return RawArtifactRepository(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_postgres_artifact_reader(self, session_factory: async_sessionmaker) -> PostgresArtifactReader:
        return PostgresArtifactReader(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_langgraph_context_tools(
        self,
        settings: Settings,
        artifact_reader: PostgresArtifactReader,
        agent_protocol_store: AgentProtocolStore,
    ) -> LangGraphContextTools:
        return LangGraphContextTools(
            program_reader=ArtifactProgramContextAdapter(artifact_reader),
            result_set_reader=agent_protocol_store,
            artifact_preview_reader=ArtifactPreviewAdapter(artifact_reader),
            search_reader=OpenSearchSanitizedSearchReader(settings),
            graph_renderer=SafeGraphTemplateRenderer(),
        )

    @provide(scope=Scope.REQUEST)
    def get_hypothesis_store(self, session_factory: async_sessionmaker) -> HypothesisStore:
        return HypothesisStore(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_hypothesis_builder_workflow(
        self,
        context_tools: LangGraphContextTools,
        hypothesis_store: HypothesisStore,
    ) -> HypothesisBuilderWorkflow:
        return HypothesisBuilderWorkflow(
            context_tools=context_tools,
            hypothesis_store=hypothesis_store,
        )

    @provide(scope=Scope.REQUEST)
    def get_program_boundary_scope_reader(self) -> ProgramBoundaryScopeReader:
        return ProgramBoundaryScopeReader()

    @provide(scope=Scope.REQUEST)
    def get_hypothesis_critic_workflow(
        self,
        scope_reader: ProgramBoundaryScopeReader,
    ) -> HypothesisCriticWorkflow:
        return HypothesisCriticWorkflow(scope_reader=scope_reader)

    @provide(scope=Scope.REQUEST)
    def get_report_draft_builder_workflow(self) -> ReportDraftBuilderWorkflow:
        return ReportDraftBuilderWorkflow()

    @provide(scope=Scope.REQUEST)
    def get_research_pass(
        self,
        hypothesis_builder: HypothesisBuilderWorkflow,
        hypothesis_critic: HypothesisCriticWorkflow,
        report_builder: ReportDraftBuilderWorkflow,
    ) -> ResearchPass:
        return ResearchPass(
            hypothesis_builder=hypothesis_builder,
            hypothesis_critic=hypothesis_critic,
            report_builder=report_builder,
        )

    @provide(scope=Scope.REQUEST)
    def get_research_control_graph(
        self,
        research_workflow: ResearchPass,
        readiness_gate: ResearchReadinessGate,
        context_tools: LangGraphContextTools,
        checkpointer: AsyncPostgresSaver,
    ) -> ResearchControlGraph:
        return ResearchControlGraph(
            research_workflow=research_workflow,
            readiness_gate=readiness_gate,
            hypothesis_selector=context_tools,
            checkpointer=checkpointer,
        )

    @provide(scope=Scope.REQUEST)
    def get_cypher_gateway_audit_store(self, session_factory: async_sessionmaker) -> CypherGatewayAuditStore:
        return CypherGatewayAuditStore(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_neo4j_read_executor(self, settings: Settings) -> Neo4jReadExecutor:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        return Neo4jReadExecutor(driver)

    @provide(scope=Scope.REQUEST)
    def get_cypher_gateway(
        self,
        executor: Neo4jReadExecutor,
        audit_store: CypherGatewayAuditStore,
    ) -> CypherGateway:
        return CypherGateway(executor=executor, audit_store=audit_store)
