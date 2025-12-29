# api/application/container_base.py
from typing import AsyncIterable
from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config import Settings
from api.infrastructure.database.connection import DatabaseConnection
from api.application.services.httpx import HTTPXScanService
from api.application.services.program import ProgramService
from api.application.services.subfinder import SubfinderScanService
from api.application.services.gau import GAUScanService
from api.application.services.katana import KatanaScanService
from api.application.services.batch_processor import (
    HTTPXBatchProcessor,
    SubfinderBatchProcessor,
    GAUBatchProcessor,
    KatanaBatchProcessor,
)
from api.infrastructure.unit_of_work.adapters.httpx import SQLAlchemyHTTPXUnitOfWork
from api.infrastructure.unit_of_work.adapters.program import SQLAlchemyProgramUnitOfWork
from api.infrastructure.unit_of_work.adapters.katana import SQLAlchemyKatanaUnitOfWork
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner
from api.infrastructure.runners.subfinder_cli import SubfinderCliRunner
from api.infrastructure.runners.gau_cli import GAUCliRunner
from api.infrastructure.runners.katana_cli import KatanaCliRunner
from api.infrastructure.events.event_bus import EventBus
from dishka import AsyncContainer

from api.application.services.orchestrator import Orchestrator

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

    @provide(scope=Scope.REQUEST)
    def get_program_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyProgramUnitOfWork:
        return SQLAlchemyProgramUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_scan_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyHTTPXUnitOfWork:
        return SQLAlchemyHTTPXUnitOfWork(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_katana_uow(self, session_factory: async_sessionmaker) -> SQLAlchemyKatanaUnitOfWork:
        return SQLAlchemyKatanaUnitOfWork(session_factory)


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
    def get_katana_processor(self, settings: Settings) -> KatanaBatchProcessor:
        return KatanaBatchProcessor(settings)


class IngestorProvider(Provider):
    scope = Scope.REQUEST
    settings = from_context(provides=Settings)

    @provide(scope=Scope.REQUEST)
    def get_httpx_ingestor(
        self,
        scan_uow: SQLAlchemyHTTPXUnitOfWork,
        event_bus: EventBus,
        settings: Settings
    ) -> HTTPXResultIngestor:
        return HTTPXResultIngestor(uow=scan_uow, bus=event_bus, settings=settings)

    @provide(scope=Scope.REQUEST)
    def get_katana_ingestor(self, katana_uow: SQLAlchemyKatanaUnitOfWork, settings: Settings) -> KatanaResultIngestor:
        return KatanaResultIngestor(uow=katana_uow, settings=settings)


class ServiceProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.REQUEST)
    def get_program_service(self, program_uow: SQLAlchemyProgramUnitOfWork) -> ProgramService:
        return ProgramService(program_uow)

    @provide(scope=Scope.REQUEST)
    def get_httpx_service(
        self,
        httpx_runner: HTTPXCliRunner,
        httpx_processor: HTTPXBatchProcessor,
        event_bus: EventBus
    ) -> HTTPXScanService:
        return HTTPXScanService(
            runner=httpx_runner,
            processor=httpx_processor,
            bus=event_bus
        )

    @provide(scope=Scope.REQUEST)
    def get_subfinder_service(
        self,
        subfinder_runner: SubfinderCliRunner,
        subfinder_processor: SubfinderBatchProcessor,
        event_bus: EventBus
    ) -> SubfinderScanService:
        return SubfinderScanService(
            runner=subfinder_runner,
            processor=subfinder_processor,
            bus=event_bus
        )

    @provide(scope=Scope.REQUEST)
    def get_gau_service(
        self,
        gau_runner: GAUCliRunner,
        gau_processor: GAUBatchProcessor,
        event_bus: EventBus
    ) -> GAUScanService:
        return GAUScanService(
            runner=gau_runner,
            processor=gau_processor,
            bus=event_bus
        )

    @provide(scope=Scope.REQUEST)
    def get_katana_service(
        self,
        katana_runner: KatanaCliRunner,
        katana_processor: KatanaBatchProcessor,
        event_bus: EventBus
    ) -> KatanaScanService:
        return KatanaScanService(
            runner=katana_runner,
            processor=katana_processor,
            bus=event_bus
        )


class OrchestratorProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_orchestrator(
        self,
        bus: EventBus,
        container: AsyncContainer,
        settings: Settings,
    ) -> Orchestrator:
        return Orchestrator(
            bus=bus,
            container=container,
            settings=settings
        )