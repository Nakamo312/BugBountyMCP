# api/application/container_base.py
from typing import AsyncIterable
from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config import Settings
from api.infrastructure.database.connection import DatabaseConnection
from api.application.services.httpx import HTTPXScanService
from api.application.services.program import ProgramService
from api.application.services.subfinder import SubfinderScanService
from api.infrastructure.unit_of_work.adapters.httpx import SQLAlchemyHTTPXUnitOfWork
from api.infrastructure.unit_of_work.adapters.program import SQLAlchemyProgramUnitOfWork
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner
from api.infrastructure.events.event_bus import EventBus


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


class CLIRunnerProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_httpx_runner(self, settings: Settings) -> HTTPXCliRunner:
        return HTTPXCliRunner(settings=settings)

    @provide(scope=Scope.APP)
    def get_event_bus(self, settings: Settings) -> EventBus:
        return EventBus(settings)


class IngestorProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.REQUEST)
    def get_httpx_ingestor(self, scan_uow: SQLAlchemyHTTPXUnitOfWork) -> HTTPXResultIngestor:
        return HTTPXResultIngestor(uow=scan_uow)


class ServiceProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.REQUEST)
    def get_program_service(self, program_uow: SQLAlchemyProgramUnitOfWork) -> ProgramService:
        return ProgramService(program_uow)

    @provide(scope=Scope.REQUEST)
    def get_httpx_service(
        self,
        httpx_runner: HTTPXCliRunner,
        event_bus: EventBus
    ) -> HTTPXScanService:
        return HTTPXScanService(
            runner=httpx_runner,
            bus=event_bus
        )

    @provide(scope=Scope.REQUEST)
    def get_subfinder_service(
        self,
        httpx_service: HTTPXScanService,
        settings: Settings
    ) -> SubfinderScanService:
        return SubfinderScanService(
            httpx_service=httpx_service,
            settings=settings
        )
