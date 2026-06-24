# api/application/container_base.py
import os
from typing import AsyncIterable
from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config import Settings
from api.infrastructure.database.connection import DatabaseConnection
from api.application.services.action import ActionService
from api.application.execution_limits import system_execution_budget
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.policy import PolicyService
from api.application.services.program import ProgramService
from api.application.services.mapcidr import MapCIDRService
from api.application.services.host import HostService
from api.application.services.analysis import AnalysisService
from api.application.services.infrastructure import InfrastructureService
from api.application.cypher_gateway import CypherGateway
from api.application.agent_wait_conditions import (
    AgentWaitConditionEngine,
    AgentWaitConditionProcessor,
)
from api.application.hypothesis_critic import (
    HypothesisCriticWorkflow,
    ProgramBoundaryScopeReader,
)
from api.application.hypotheses import HypothesisBuilderWorkflow
from api.application.langgraph_approval import LangGraphApprovalNode
from api.application.langgraph_context_tools import LangGraphContextTools
from api.application.langgraph_tool_action import LangGraphToolActionTool
from api.application.langgraph_workflows import LangGraphWorkflowRuntime
from api.application.mvp_research_workflow import MvpResearchWorkflow
from api.application.mvp_research_state_graph import MvpResearchStateGraph
from api.application.mvp_research_readiness import MvpResearchReadinessGate
from api.application.report_drafts import ReportDraftBuilderWorkflow
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from api.application.services.batch_processor import (
    AmassBatchProcessor,
    FFUFBatchProcessor,
    HTTPXBatchProcessor,
    LinkFinderBatchProcessor,
    MantraBatchProcessor,
    SubfinderBatchProcessor,
    WaymoreBatchProcessor,
    KatanaBatchProcessor,
    DNSxBatchProcessor,
    SubjackBatchProcessor,
    ASNMapBatchProcessor,
    NaabuBatchProcessor,
    TLSxBatchProcessor,
    MapCIDRBatchProcessor,
    SmapBatchProcessor,
    Hakip2HostBatchProcessor,
    PlaywrightBatchProcessor,
)
from api.infrastructure.unit_of_work.adapters.httpx import SQLAlchemyHTTPXUnitOfWork
from api.infrastructure.unit_of_work.adapters.program import SQLAlchemyProgramUnitOfWork
from api.infrastructure.unit_of_work.adapters.katana import SQLAlchemyKatanaUnitOfWork
from api.infrastructure.unit_of_work.adapters.linkfinder import SQLAlchemyLinkFinderUnitOfWork
from api.infrastructure.unit_of_work.adapters.mantra import SQLAlchemyMantraUnitOfWork
from api.infrastructure.unit_of_work.adapters.dnsx import SQLAlchemyDNSxUnitOfWork
from api.infrastructure.unit_of_work.adapters.asnmap import SQLAlchemyASNMapUnitOfWork
from api.infrastructure.unit_of_work.adapters.naabu import SQLAlchemyNaabuUnitOfWork
from api.infrastructure.unit_of_work.adapters.infrastructure import SQLAlchemyInfrastructureUnitOfWork
from api.infrastructure.repositories.adapters.scope_rule import SQLAlchemyScopeRuleRepository
from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
from api.infrastructure.ingestors.linkfinder_ingestor import LinkFinderResultIngestor
from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor
from api.infrastructure.ingestors.ffuf_ingestor import FFUFResultIngestor
from api.infrastructure.ingestors.dnsx_ingestor import DNSxDiscoveryResultIngestor, DNSxResultIngestor
from api.infrastructure.ingestors.subjack_ingestor import SubjackResultIngestor
from api.infrastructure.ingestors.asnmap_ingestor import ASNMapResultIngestor
from api.infrastructure.ingestors.naabu_ingestor import NaabuResultIngestor
from api.infrastructure.ingestors.smap_ingestor import SmapResultIngestor
from api.infrastructure.ingestors.host_ingestor import HostIngestor
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner
from api.infrastructure.runners.subfinder_cli import SubfinderCliRunner
from api.infrastructure.runners.waymore_cli import WaymoreCliRunner
from api.infrastructure.runners.katana_cli import KatanaCliRunner
from api.infrastructure.runners.linkfinder_cli import LinkFinderCliRunner
from api.infrastructure.runners.mantra_cli import MantraCliRunner
from api.infrastructure.runners.ffuf_cli import FFUFCliRunner
from api.infrastructure.runners.amass_cli import AmassCliRunner
from api.infrastructure.runners.dnsx_cli import DNSxCliRunner
from api.infrastructure.runners.subjack_cli import SubjackCliRunner
from api.infrastructure.runners.asnmap_cli import ASNMapCliRunner
from api.infrastructure.runners.mapcidr_cli import MapCIDRCliRunner
from api.infrastructure.runners.naabu_cli import NaabuCliRunner
from api.infrastructure.runners.tlsx_cli import TLSxCliRunner
from api.infrastructure.runners.smap_cli import SmapCliRunner
from api.infrastructure.runners.hakip2host_cli import Hakip2HostCliRunner
from api.infrastructure.runners.playwright_cli import PlaywrightCliRunner
from api.infrastructure.agent_coordination import (
    AgentEventRouter,
    AgentInboxStore,
    AgentProtocolStore,
    AgentWaitConditionStore,
    LangGraphWorkflowStore,
)
from api.infrastructure.events.dispatcher import EventDispatcher
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.orchestration.store import OrchestrationStore
from api.infrastructure.tool_catalog.store import SqlActionCatalogStore
from api.infrastructure.runtime_manifest import ManifestActivator
from api.infrastructure.artifacts.raw_artifact_repository import RawArtifactRepository
from api.infrastructure.artifacts.postgres_reader import PostgresArtifactReader
from api.infrastructure.langgraph_context import (
    ArtifactPreviewAdapter,
    ArtifactProgramContextAdapter,
    OpenSearchSanitizedSearchReader,
    SafeGraphTemplateRenderer,
)
from api.infrastructure.cypher_gateway import CypherGatewayAuditStore, Neo4jReadExecutor
from api.infrastructure.hypotheses import HypothesisStore
from api.infrastructure.projections import ProjectionStateStore
from api.infrastructure.langgraph_resume import MvpResearchAutoResumer
from api.infrastructure.agent_wait_state import AgentExecutionStateReader
from dishka import AsyncContainer

from api.application.pipeline.registry import NodeRegistry
from api.infrastructure.runners.dnsx_runners import DNSxDeepRunner, DNSxPtrRunner
from api.infrastructure.runners.mapcidr_runners import MapCIDRExpandRunner
from api.infrastructure.runners.tlsx_runners import TLSxDefaultRunner
from api.infrastructure.ingestors.tlsx_ingestor import TLSxResultIngestor
from api.infrastructure.ingestors.amass_ingestor import AmassResultIngestor

class DatabaseProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_database_connection(self, settings: Settings) -> DatabaseConnection:
        return DatabaseConnection(settings.postgres_dsn)

    @provide(scope=Scope.APP)
    def get_session_factory(self, db: DatabaseConnection) -> async_sessionmaker:
        return db.session_factory

    @provide(scope=Scope.REQUEST)
    async def get_session(self, db: DatabaseConnection) -> AsyncIterable[AsyncSession]:
        async with db.session() as session:
            yield session


class UnitOfWorkProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.REQUEST, provides=ProgramUnitOfWork)
    def get_program_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyProgramUnitOfWork:
        return SQLAlchemyProgramUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_scan_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyHTTPXUnitOfWork:
        return SQLAlchemyHTTPXUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_katana_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyKatanaUnitOfWork:
        return SQLAlchemyKatanaUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_linkfinder_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyLinkFinderUnitOfWork:
        return SQLAlchemyLinkFinderUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_mantra_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyMantraUnitOfWork:
        return SQLAlchemyMantraUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_dnsx_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyDNSxUnitOfWork:
        return SQLAlchemyDNSxUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_asnmap_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyASNMapUnitOfWork:
        return SQLAlchemyASNMapUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_naabu_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyNaabuUnitOfWork:
        return SQLAlchemyNaabuUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_infrastructure_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyInfrastructureUnitOfWork:
        return SQLAlchemyInfrastructureUnitOfWork(session_factory)


class OrchestrationProvider(Provider):
    scope = Scope.APP

    @provide(scope=Scope.APP)
    def get_orchestration_store(self, session_factory: async_sessionmaker) -> OrchestrationStore:
        return OrchestrationStore(session_factory)

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
    def get_projection_state_store(
        self,
        session_factory: async_sessionmaker,
    ) -> ProjectionStateStore:
        return ProjectionStateStore(session_factory)

    @provide(scope=Scope.APP)
    def get_agent_wait_condition_engine(
        self,
        projection_reader: ProjectionStateStore,
        result_set_reader: AgentProtocolStore,
        execution_state_reader: AgentExecutionStateReader,
    ) -> AgentWaitConditionEngine:
        return AgentWaitConditionEngine(
            projection_reader=projection_reader,
            result_set_reader=result_set_reader,
            execution_state_reader=execution_state_reader,
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
    def get_mvp_research_auto_resumer(
        self,
        container: AsyncContainer,
    ) -> MvpResearchAutoResumer:
        return MvpResearchAutoResumer(container=container)

    @provide(scope=Scope.APP)
    def get_agent_wait_condition_processor(
        self,
        settings: Settings,
        store: AgentWaitConditionStore,
        engine: AgentWaitConditionEngine,
        workflow_resumer: MvpResearchAutoResumer,
    ) -> AgentWaitConditionProcessor:
        return AgentWaitConditionProcessor(
            store=store,
            engine=engine,
            workflow_resumer=workflow_resumer,
            sweep_interval_seconds=settings.AGENT_WAIT_SWEEP_INTERVAL_SECONDS,
        )

    @provide(scope=Scope.REQUEST)
    def get_mvp_research_readiness_gate(
        self,
        wait_engine: AgentWaitConditionEngine,
        protocol_store: AgentProtocolStore,
        workflow_runtime: LangGraphWorkflowRuntime,
    ) -> MvpResearchReadinessGate:
        return MvpResearchReadinessGate(
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
    def get_mvp_research_workflow(
        self,
        hypothesis_builder: HypothesisBuilderWorkflow,
        hypothesis_critic: HypothesisCriticWorkflow,
        report_builder: ReportDraftBuilderWorkflow,
    ) -> MvpResearchWorkflow:
        return MvpResearchWorkflow(
            hypothesis_builder=hypothesis_builder,
            hypothesis_critic=hypothesis_critic,
            report_builder=report_builder,
        )

    @provide(scope=Scope.REQUEST)
    def get_mvp_research_state_graph(
        self,
        research_workflow: MvpResearchWorkflow,
        readiness_gate: MvpResearchReadinessGate,
        checkpointer: AsyncPostgresSaver,
    ) -> MvpResearchStateGraph:
        return MvpResearchStateGraph(
            research_workflow=research_workflow,
            readiness_gate=readiness_gate,
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
        event_bus: EventBus,
        orchestration_store: OrchestrationStore,
        policy_service: PolicyService,
        catalog_service: ActionCatalogService,
        scope_rule_repository: SQLAlchemyScopeRuleRepository,
    ) -> ActionService:
        return ActionService(
            event_bus=event_bus,
            store=orchestration_store,
            policy=policy_service,
            catalog=catalog_service,
            scope_rules=scope_rule_repository,
            system_budget=system_execution_budget(settings),
        )


class CLIRunnerProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_httpx_runner(self, settings: Settings) -> HTTPXCliRunner:
        return HTTPXCliRunner(
            httpx_path=settings.get_tool_path("httpx"),
            timeout=600,
        )

    @provide(scope=Scope.APP)
    def get_subfinder_runner(self, settings: Settings) -> SubfinderCliRunner:
        return SubfinderCliRunner(
            subfinder_path=settings.get_tool_path("subfinder"),
            timeout=600,
        )

    @provide(scope=Scope.APP)
    def get_katana_runner(self, settings: Settings) -> KatanaCliRunner:
        return KatanaCliRunner(
            katana_path=settings.get_tool_path("katana"),
            timeout=600,
        )

    @provide(scope=Scope.APP)
    def get_linkfinder_runner(self, settings: Settings) -> LinkFinderCliRunner:
        return LinkFinderCliRunner(
            linkfinder_path=settings.get_tool_path("linkfinder"),
            timeout=15,
        )

    @provide(scope=Scope.APP)
    def get_mantra_runner(self, settings: Settings) -> MantraCliRunner:
        return MantraCliRunner(
            mantra_path=settings.get_tool_path("mantra"),
            timeout=300,
        )

    @provide(scope=Scope.APP)
    def get_waymore_runner(self, settings: Settings) -> WaymoreCliRunner:
        return WaymoreCliRunner(
            waymore_path="waymore",
            timeout=1800,
        )

    @provide(scope=Scope.APP)
    def get_ffuf_runner(self, settings: Settings) -> FFUFCliRunner:
        return FFUFCliRunner(
            ffuf_path=settings.get_tool_path("ffuf"),
            wordlist=settings.FFUF_WORDLIST,
            rate_limit=settings.FFUF_RATE_LIMIT,
            timeout=600,
        )

    @provide(scope=Scope.APP)
    def get_amass_runner(self, settings: Settings) -> AmassCliRunner:
        return AmassCliRunner(
            amass_path=settings.get_tool_path("amass"),
            wordlist=settings.AMASS_WORDLIST,
            timeout=1800,
        )

    @provide(scope=Scope.APP)
    def get_dnsx_runner(self, settings: Settings) -> DNSxCliRunner:
        return DNSxCliRunner(
            dnsx_path=settings.get_tool_path("dnsx"),
            timeout=600,
        )

    @provide(scope=Scope.APP)
    def get_subjack_runner(self, settings: Settings) -> SubjackCliRunner:
        fingerprints = settings.SUBJACK_FINGERPRINTS if os.path.exists(settings.SUBJACK_FINGERPRINTS) else None
        return SubjackCliRunner(
            subjack_path=settings.get_tool_path("subjack"),
            fingerprints_path=fingerprints,
            timeout=300,
        )

    @provide(scope=Scope.APP)
    def get_asnmap_runner(self, settings: Settings) -> ASNMapCliRunner:
        return ASNMapCliRunner(
            asnmap_path=settings.get_tool_path("asnmap"),
            timeout=300,
        )

    @provide(scope=Scope.APP)
    def get_mapcidr_runner(self, settings: Settings) -> MapCIDRCliRunner:
        return MapCIDRCliRunner(
            mapcidr_path=settings.get_tool_path("mapcidr"),
            timeout=300,
        )

    @provide(scope=Scope.APP)
    def get_naabu_runner(self, settings: Settings) -> NaabuCliRunner:
        return NaabuCliRunner(
            naabu_path=settings.get_tool_path("naabu"),
            timeout=600,
        )

    @provide(scope=Scope.APP)
    def get_tlsx_runner(self, settings: Settings) -> TLSxCliRunner:
        return TLSxCliRunner(
            tlsx_path=settings.get_tool_path("tlsx"),
            timeout=300,
        )

    @provide(scope=Scope.APP)
    def get_smap_runner(self, settings: Settings) -> SmapCliRunner:
        return SmapCliRunner(
            smap_path=settings.get_tool_path("smap"),
            timeout=600,
        )

    @provide(scope=Scope.APP)
    def get_hakip2host_runner(self, settings: Settings) -> Hakip2HostCliRunner:
        return Hakip2HostCliRunner(
            hakip2host_path=settings.get_tool_path("hakip2host"),
            timeout=300,
        )

    @provide(scope=Scope.APP)
    def get_playwright_runner(self, settings: Settings) -> PlaywrightCliRunner:
        return PlaywrightCliRunner(timeout=600)

    @provide(scope=Scope.APP)
    def get_mapcidr_expand_runner(self, mapcidr_runner: MapCIDRCliRunner) -> MapCIDRExpandRunner:
        return MapCIDRExpandRunner(mapcidr_runner)

    @provide(scope=Scope.APP)
    def get_tlsx_default_runner(self, tlsx_runner: TLSxCliRunner) -> TLSxDefaultRunner:
        return TLSxDefaultRunner(tlsx_runner)

    @provide(scope=Scope.APP)
    def get_dnsx_deep_runner(self, dnsx_runner: DNSxCliRunner) -> DNSxDeepRunner:
        return DNSxDeepRunner(dnsx_runner)

    @provide(scope=Scope.APP)
    def get_dnsx_ptr_runner(self, dnsx_runner: DNSxCliRunner) -> DNSxPtrRunner:
        return DNSxPtrRunner(dnsx_runner)

    @provide(scope=Scope.APP)
    def get_event_bus(
        self,
        settings: Settings,
        orchestration_store: OrchestrationStore,
    ) -> EventBus:
        return EventBus(settings, event_recorder=orchestration_store)

    @provide(scope=Scope.APP)
    def get_event_dispatcher(
        self,
        settings: Settings,
        orchestration_store: OrchestrationStore,
        event_bus: EventBus,
        agent_router: AgentEventRouter,
    ) -> EventDispatcher:
        return EventDispatcher(
            store=orchestration_store,
            event_bus=event_bus,
            agent_router=agent_router,
            batch_size=settings.EVENT_DISPATCH_BATCH_SIZE,
            lease_ttl_seconds=settings.EVENT_DISPATCH_LEASE_TTL_SECONDS,
            max_attempts=settings.EVENT_DISPATCH_MAX_ATTEMPTS,
            retry_delay_seconds=settings.EVENT_DISPATCH_RETRY_DELAY_SECONDS,
            sweep_interval_seconds=settings.EVENT_DISPATCH_SWEEP_INTERVAL_SECONDS,
            notify_channel=settings.EVENT_DISPATCH_NOTIFY_CHANNEL,
            listen_dsn=settings.postgres_asyncpg_dsn,
        )


class BatchProcessorProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_httpx_processor(self, settings: Settings) -> HTTPXBatchProcessor:
        return HTTPXBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_subfinder_processor(self, settings: Settings) -> SubfinderBatchProcessor:
        return SubfinderBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_waymore_processor(self, settings: Settings) -> WaymoreBatchProcessor:
        return WaymoreBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_katana_processor(self, settings: Settings) -> KatanaBatchProcessor:
        return KatanaBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_linkfinder_processor(self, settings: Settings) -> LinkFinderBatchProcessor:
        return LinkFinderBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_mantra_processor(self, settings: Settings) -> MantraBatchProcessor:
        return MantraBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_dnsx_processor(self, settings: Settings) -> DNSxBatchProcessor:
        return DNSxBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_subjack_processor(self, settings: Settings) -> SubjackBatchProcessor:
        return SubjackBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_asnmap_processor(self, settings: Settings) -> ASNMapBatchProcessor:
        return ASNMapBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_amass_processor(self, settings: Settings) -> AmassBatchProcessor:
        return AmassBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_ffuf_processor(self, settings: Settings) -> FFUFBatchProcessor:
        return FFUFBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_naabu_processor(self, settings: Settings) -> NaabuBatchProcessor:
        return NaabuBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_tlsx_processor(self, settings: Settings) -> TLSxBatchProcessor:
        return TLSxBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_mapcidr_processor(self, settings: Settings) -> MapCIDRBatchProcessor:
        return MapCIDRBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_smap_processor(self, settings: Settings) -> SmapBatchProcessor:
        return SmapBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_hakip2host_processor(self, settings: Settings) -> Hakip2HostBatchProcessor:
        return Hakip2HostBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_playwright_processor(self, settings: Settings) -> PlaywrightBatchProcessor:
        return PlaywrightBatchProcessor(settings)


class IngestorProvider(Provider):
    scope = Scope.REQUEST
    settings = from_context(provides=Settings)

    @provide(scope=Scope.REQUEST)
    def get_httpx_ingestor(
        self,
        scan_uow: SQLAlchemyHTTPXUnitOfWork,
        settings: Settings
    ) -> HTTPXResultIngestor:
        return HTTPXResultIngestor(uow=scan_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_katana_ingestor(
        self,
        katana_uow: SQLAlchemyKatanaUnitOfWork,
        settings: Settings,
    ) -> KatanaResultIngestor:
        return KatanaResultIngestor(uow=katana_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_linkfinder_ingestor(
        self,
        linkfinder_uow: SQLAlchemyLinkFinderUnitOfWork,
        settings: Settings
    ) -> LinkFinderResultIngestor:
        return LinkFinderResultIngestor(uow=linkfinder_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_mantra_ingestor(
        self,
        mantra_uow: SQLAlchemyMantraUnitOfWork
    ) -> MantraResultIngestor:
        return MantraResultIngestor(uow=mantra_uow)

    @provide(scope=Scope.REQUEST)
    def get_ffuf_ingestor(
        self,
        scan_uow: SQLAlchemyHTTPXUnitOfWork
    ) -> FFUFResultIngestor:
        return FFUFResultIngestor(uow=scan_uow)

    @provide(scope=Scope.REQUEST)
    def get_dnsx_ingestor(
        self,
        dnsx_uow: SQLAlchemyDNSxUnitOfWork,
        settings: Settings
    ) -> DNSxResultIngestor:
        return DNSxResultIngestor(uow=dnsx_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_dnsx_discovery_ingestor(
        self,
        dnsx_uow: SQLAlchemyDNSxUnitOfWork,
        settings: Settings
    ) -> DNSxDiscoveryResultIngestor:
        return DNSxDiscoveryResultIngestor(uow=dnsx_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_subjack_ingestor(
        self,
        httpx_uow: SQLAlchemyHTTPXUnitOfWork,
        settings: Settings
    ) -> SubjackResultIngestor:
        return SubjackResultIngestor(uow=httpx_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_asnmap_ingestor(
        self,
        asnmap_uow: SQLAlchemyASNMapUnitOfWork,
        settings: Settings
    ) -> ASNMapResultIngestor:
        return ASNMapResultIngestor(uow=asnmap_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_naabu_ingestor(
        self,
        naabu_uow: SQLAlchemyNaabuUnitOfWork,
        settings: Settings
    ) -> NaabuResultIngestor:
        return NaabuResultIngestor(uow=naabu_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_smap_ingestor(
        self,
        naabu_uow: SQLAlchemyNaabuUnitOfWork,
        settings: Settings
    ) -> SmapResultIngestor:
        return SmapResultIngestor(uow=naabu_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_tlsx_ingestor(
        self,
        dnsx_uow: SQLAlchemyDNSxUnitOfWork,
        settings: Settings
    ) -> TLSxResultIngestor:
        return TLSxResultIngestor(uow=dnsx_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_amass_ingestor(
        self,
        infrastructure_uow: SQLAlchemyInfrastructureUnitOfWork,
        settings: Settings
    ) -> AmassResultIngestor:
        return AmassResultIngestor(uow=infrastructure_uow, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_host_ingestor(
        self,
        dnsx_uow: SQLAlchemyDNSxUnitOfWork,
        settings: Settings
    ) -> HostIngestor:
        return HostIngestor(uow=dnsx_uow, settings=settings)


class ServiceProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.REQUEST)
    def get_program_service(self, program_uow: ProgramUnitOfWork) -> ProgramService:
        return ProgramService(program_uow)

    @provide(scope=Scope.REQUEST)
    def get_mapcidr_service(
        self,
        mapcidr_runner: MapCIDRCliRunner,
        event_bus: EventBus
    ) -> MapCIDRService:
        return MapCIDRService(
            runner=mapcidr_runner,
            bus=event_bus
        )
    
    @provide(scope=Scope.REQUEST)
    def get_host_service(
        self,
        scan_uow: SQLAlchemyHTTPXUnitOfWork
    ) -> HostService:
        return HostService(scan_uow)

    @provide(scope=Scope.REQUEST)
    def get_analysis_service(
        self,
        scan_uow: SQLAlchemyHTTPXUnitOfWork
    ) -> AnalysisService:
        return AnalysisService(scan_uow)

    @provide(scope=Scope.REQUEST)
    def get_infrastructure_service(
        self,
        infrastructure_uow: SQLAlchemyInfrastructureUnitOfWork
    ) -> InfrastructureService:
        return InfrastructureService(infrastructure_uow)


class PipelineProvider(Provider):
    """Provider for node-based pipeline architecture"""
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_node_registry(
        self,
        bus: EventBus,
        settings: Settings,
        container: AsyncContainer,
    ) -> NodeRegistry:
        return NodeRegistry(bus, settings, container)
