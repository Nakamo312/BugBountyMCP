# api/application/container_base.py
import os
from typing import AsyncIterable
from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config import Settings
from api.infrastructure.database.connection import DatabaseConnection
from api.application.services.program import ProgramService
from api.application.services.mapcidr import MapCIDRService
from api.application.services.host import HostService
from api.application.services.analysis import AnalysisService
from api.application.services.infrastructure import InfrastructureService
from api.application.services.batch_processor import (
    HTTPXBatchProcessor,
    SubfinderBatchProcessor,
    GAUBatchProcessor,
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
from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
from api.infrastructure.ingestors.linkfinder_ingestor import LinkFinderResultIngestor
from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor
from api.infrastructure.ingestors.ffuf_ingestor import FFUFResultIngestor
from api.infrastructure.ingestors.dnsx_ingestor import DNSxResultIngestor
from api.infrastructure.ingestors.subjack_ingestor import SubjackResultIngestor
from api.infrastructure.ingestors.asnmap_ingestor import ASNMapResultIngestor
from api.infrastructure.ingestors.naabu_ingestor import NaabuResultIngestor
from api.infrastructure.ingestors.smap_ingestor import SmapResultIngestor
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner
from api.infrastructure.runners.subfinder_cli import SubfinderCliRunner
from api.infrastructure.runners.gau_cli import GAUCliRunner
from api.infrastructure.runners.waymore_cli import WaymoreCliRunner
from api.infrastructure.runners.katana_cli import KatanaCliRunner
from api.infrastructure.runners.linkfinder_cli import LinkFinderCliRunner
from api.infrastructure.runners.mantra_cli import MantraCliRunner
from api.infrastructure.runners.ffuf_cli import FFUFCliRunner
from api.infrastructure.runners.dnsx_cli import DNSxCliRunner
from api.infrastructure.runners.subjack_cli import SubjackCliRunner
from api.infrastructure.runners.asnmap_cli import ASNMapCliRunner
from api.infrastructure.runners.mapcidr_cli import MapCIDRCliRunner
from api.infrastructure.runners.naabu_cli import NaabuCliRunner
from api.infrastructure.runners.tlsx_cli import TLSxCliRunner
from api.infrastructure.runners.smap_cli import SmapCliRunner
from api.infrastructure.runners.hakip2host_cli import Hakip2HostCliRunner
from api.infrastructure.runners.playwright_cli import PlaywrightCliRunner
from api.infrastructure.events.event_bus import EventBus
from dishka import AsyncContainer

from api.application.pipeline.registry import NodeRegistry
from api.infrastructure.runners.dnsx_runners import DNSxBasicRunner, DNSxDeepRunner, DNSxPtrRunner
from api.infrastructure.runners.mapcidr_runners import MapCIDRExpandRunner
from api.infrastructure.runners.tlsx_runners import TLSxDefaultRunner
from api.infrastructure.ingestors.tlsx_ingestor import TLSxResultIngestor
from api.application.pipeline.nodes.hakip2host_node import Hakip2HostNode
from api.application.pipeline.nodes.ffuf_node import FFUFNode
from api.application.pipeline.scope_policy import ScopePolicy

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
    def get_gau_runner(self, settings: Settings) -> GAUCliRunner:
        return GAUCliRunner(
            gau_path=settings.get_tool_path("gau"),
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
    def get_dnsx_basic_runner(self, dnsx_runner: DNSxCliRunner) -> DNSxBasicRunner:
        return DNSxBasicRunner(dnsx_runner)

    @provide(scope=Scope.APP)
    def get_dnsx_deep_runner(self, dnsx_runner: DNSxCliRunner) -> DNSxDeepRunner:
        return DNSxDeepRunner(dnsx_runner)

    @provide(scope=Scope.APP)
    def get_dnsx_ptr_runner(self, dnsx_runner: DNSxCliRunner) -> DNSxPtrRunner:
        return DNSxPtrRunner(dnsx_runner)

    @provide(scope=Scope.APP)
    def get_event_bus(self, settings: Settings) -> EventBus:
        return EventBus(settings)


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
    def get_gau_processor(self, settings: Settings) -> GAUBatchProcessor:
        return GAUBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_waymore_processor(self, settings: Settings) -> WaymoreBatchProcessor:
        return WaymoreBatchProcessor(settings)

    @provide(scope=Scope.APP)
    def get_katana_processor(self, settings: Settings) -> KatanaBatchProcessor:
        return KatanaBatchProcessor(settings)

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
        program_uow: ProgramUnitOfWork,
        settings: Settings
    ) -> TLSxResultIngestor:
        return TLSxResultIngestor(uow=program_uow, settings=settings)


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
        from api.application.pipeline.factory import NodeFactory
        from api.infrastructure.events.event_types import EventType

        registry = NodeRegistry(bus, settings, container)

        if not settings.USE_NODE_PIPELINE:
            return registry

        httpx_node = NodeFactory.create_scan_node(
            node_id="httpx",
            event_in={
                EventType.SUBDOMAIN_DISCOVERED,
                EventType.GAU_DISCOVERED,
                EventType.DNSX_FILTERED_HOSTS,
                EventType.HTTPX_SCAN_REQUESTED,
            },
            event_out={
                EventType.HOST_DISCOVERED: "new_hosts",
                EventType.JS_FILES_DISCOVERED: "js_files",
            },
            runner_type=HTTPXCliRunner,
            processor_type=HTTPXBatchProcessor,
            ingestor_type=HTTPXResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT,
            scope_policy=ScopePolicy.CONFIDENCE
        )
        registry.register(httpx_node)

        # KatanaNode - dependencies resolved from DI on each execution
        katana_node = NodeFactory.create_scan_node(
            node_id="katana",
            event_in={
                EventType.KATANA_SCAN_REQUESTED,
                EventType.HOST_DISCOVERED,
            },
            event_out={
                EventType.JS_FILES_DISCOVERED: "js_files",
            },
            runner_type=KatanaCliRunner,
            processor_type=KatanaBatchProcessor,
            ingestor_type=KatanaResultIngestor,
            max_parallelism=2,
            execution_delay=settings.ORCHESTRATOR_SCAN_DELAY,
            scope_policy=ScopePolicy.CONFIDENCE
        )
        registry.register(katana_node)

        # Playwright - interactive crawler with network interception
        playwright_node = NodeFactory.create_scan_node(
            node_id="playwright",
            event_in={EventType.PLAYWRIGHT_SCAN_REQUESTED, EventType.HOST_DISCOVERED},
            event_out={
                EventType.JS_FILES_DISCOVERED: "js_files",
            },
            runner_type=PlaywrightCliRunner,
            processor_type=PlaywrightBatchProcessor,
            ingestor_type=KatanaResultIngestor,
            max_parallelism=1,
            execution_delay=settings.ORCHESTRATOR_SCAN_DELAY,
            scope_policy=ScopePolicy.STRICT
        )
        registry.register(playwright_node)

        linkfinder_node = NodeFactory.create_scan_node(
            node_id="linkfinder",
            event_in={
                EventType.LINKFINDER_SCAN_REQUESTED,
                EventType.JS_FILES_DISCOVERED,
            },
            event_out={
                EventType.GAU_DISCOVERED: "urls",
            },
            runner_type=LinkFinderCliRunner,
            processor_type=None,
            ingestor_type=LinkFinderResultIngestor,
            max_parallelism=3,
            scope_policy=ScopePolicy.CONFIDENCE
        )
        registry.register(linkfinder_node)

        mantra_node = NodeFactory.create_scan_node(
            node_id="mantra",
            event_in={
                EventType.MANTRA_SCAN_REQUESTED,
                EventType.JS_FILES_DISCOVERED,
            },
            event_out={},
            runner_type=MantraCliRunner,
            processor_type=None,
            ingestor_type=MantraResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT
        )
        registry.register(mantra_node)

        subfinder_node = NodeFactory.create_scan_node(
            node_id="subfinder",
            event_in={
                EventType.SUBFINDER_SCAN_REQUESTED,
            },
            event_out={
                EventType.SUBDOMAIN_DISCOVERED: "subdomains",
            },
            runner_type=SubfinderCliRunner,
            processor_type=SubfinderBatchProcessor,
            ingestor_type=None,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT,
            scope_policy=ScopePolicy.NONE
        )
        registry.register(subfinder_node)

        gau_node = NodeFactory.create_scan_node(
            node_id="gau",
            event_in={
                EventType.GAU_SCAN_REQUESTED,
            },
            event_out={
                EventType.GAU_DISCOVERED: "urls",
            },
            runner_type=GAUCliRunner,
            processor_type=GAUBatchProcessor,
            ingestor_type=None,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT,
            scope_policy=ScopePolicy.STRICT
        )
        registry.register(gau_node)

        waymore_node = NodeFactory.create_scan_node(
            node_id="waymore",
            event_in={
                EventType.SUBDOMAIN_DISCOVERED,
            },
            event_out={
                EventType.GAU_DISCOVERED: "urls",
            },
            runner_type=WaymoreCliRunner,
            processor_type=WaymoreBatchProcessor,
            ingestor_type=None,
            max_parallelism=2,
            scope_policy=ScopePolicy.STRICT
        )
        registry.register(waymore_node)

        subjack_node = NodeFactory.create_scan_node(
            node_id="subjack",
            event_in={
                EventType.SUBJACK_SCAN_REQUESTED,
                EventType.SUBDOMAIN_DISCOVERED,
            },
            event_out={},
            runner_type=SubjackCliRunner,
            processor_type=SubjackBatchProcessor,
            ingestor_type=SubjackResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT
        )
        registry.register(subjack_node)

        ffuf_node = FFUFNode(
            node_id="ffuf",
            event_in={
                EventType.FFUF_SCAN_REQUESTED,
                EventType.HOST_DISCOVERED,
            },
            max_parallelism=3,
            max_concurrent_scans=5
        )
        ffuf_node.set_context_factory(bus, container, settings)
        registry.register(ffuf_node)

        asnmap_node = NodeFactory.create_scan_node(
            node_id="asnmap",
            event_in={
                EventType.ASNMAP_SCAN_REQUESTED,
            },
            event_out={
                EventType.ASN_DISCOVERED: "asns",
                EventType.CIDR_DISCOVERED: "cidrs",
            },
            runner_type=ASNMapCliRunner,
            processor_type=ASNMapBatchProcessor,
            ingestor_type=ASNMapResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT
        )
        registry.register(asnmap_node)

        naabu_node = NodeFactory.create_scan_node(
            node_id="naabu",
            event_in={
                EventType.NAABU_SCAN_REQUESTED,
            },
            event_out={},
            runner_type=NaabuCliRunner,
            processor_type=NaabuBatchProcessor,
            ingestor_type=NaabuResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT
        )
        registry.register(naabu_node)

        mapcidr_expand_node = NodeFactory.create_scan_node(
            node_id="mapcidr_expand",
            event_in={
                EventType.CIDR_DISCOVERED,
                EventType.MAPCIDR_SCAN_REQUESTED,
            },
            event_out={
                EventType.IPS_EXPANDED: "ips",
            },
            runner_type=MapCIDRExpandRunner,
            processor_type=MapCIDRBatchProcessor,
            ingestor_type=None,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT
        )
        registry.register(mapcidr_expand_node)

        tlsx_default_node = NodeFactory.create_scan_node(
            node_id="tlsx_default",
            event_in={
                EventType.IPS_EXPANDED,
                EventType.TLSX_SCAN_REQUESTED,
            },
            event_out={
                EventType.HOST_DISCOVERED: "urls",
                EventType.CERT_SAN_DISCOVERED: "new_hosts",
            },
            runner_type=TLSxDefaultRunner,
            processor_type=TLSxBatchProcessor,
            ingestor_type=TLSxResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT,
            scope_policy=ScopePolicy.STRICT
        )
        registry.register(tlsx_default_node)

        dnsx_basic_node = NodeFactory.create_scan_node(
            node_id="dnsx_basic",
            event_in={
                EventType.HOST_DISCOVERED,
                EventType.DNSX_BASIC_SCAN_REQUESTED,
            },
            event_out={
                EventType.DNSX_FILTERED_HOSTS: "hosts",
            },
            runner_type=DNSxBasicRunner,
            processor_type=DNSxBatchProcessor,
            ingestor_type=DNSxResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT,
            scope_policy=ScopePolicy.STRICT
        )
        registry.register(dnsx_basic_node)

        dnsx_deep_node = NodeFactory.create_scan_node(
            node_id="dnsx_deep",
            event_in={
                EventType.HOST_DISCOVERED,
                EventType.DNSX_DEEP_SCAN_REQUESTED,
            },
            event_out={},
            runner_type=DNSxDeepRunner,
            processor_type=DNSxBatchProcessor,
            ingestor_type=DNSxResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT
        )
        registry.register(dnsx_deep_node)

        dnsx_ptr_node = NodeFactory.create_scan_node(
            node_id="dnsx_ptr",
            event_in={
                EventType.DNSX_PTR_SCAN_REQUESTED,
            },
            event_out={},
            runner_type=DNSxPtrRunner,
            processor_type=DNSxBatchProcessor,
            ingestor_type=DNSxResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT
        )
        registry.register(dnsx_ptr_node)

        smap_node = NodeFactory.create_scan_node(
            node_id="smap",
            event_in={
                EventType.SMAP_SCAN_REQUESTED,
                EventType.CIDR_DISCOVERED,
            },
            event_out={
                EventType.IPS_EXPANDED: "ips",
                EventType.SUBDOMAIN_DISCOVERED: "hostnames",
            },
            runner_type=SmapCliRunner,
            processor_type=SmapBatchProcessor,
            ingestor_type=SmapResultIngestor,
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT
        )
        registry.register(smap_node)

        hakip2host_node = Hakip2HostNode(
            node_id="hakip2host",
            event_in={
                EventType.HAKIP2HOST_SCAN_REQUESTED,
                EventType.IPS_EXPANDED,
            },
            max_parallelism=settings.ORCHESTRATOR_MAX_CONCURRENT,
            scope_policy=ScopePolicy.CONFIDENCE
        )
        registry.register(hakip2host_node)

        return registry