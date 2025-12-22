# api/application/container_base.py
from typing import AsyncIterable, Callable
from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config import Settings
from api.infrastructure.database.connection import DatabaseConnection
from api.application.services.httpx import HTTPXScanService
from api.application.services.program import ProgramService
from api.application.services.subfinder import SubfinderScanService
from api.infrastructure.unit_of_work.adapters.httpx import SQLAlchemyHTTPXUnitOfWork
from api.infrastructure.unit_of_work.adapters.program import SQLAlchemyProgramUnitOfWork


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
    """Provider for Unit of Work instances"""
    
    @provide(scope=Scope.REQUEST)
    def get_program_uow(
        self,
        session_factory: async_sessionmaker
    ) -> SQLAlchemyProgramUnitOfWork:
        """Create Program Unit of Work"""
        return SQLAlchemyProgramUnitOfWork(session_factory)
    
    @provide(scope=Scope.REQUEST)
    def get_scan_uow(
        self,
        session_factory: async_sessionmaker
    ) -> SQLAlchemyHTTPXUnitOfWork:
        """Create Scan Unit of Work"""
        return SQLAlchemyHTTPXUnitOfWork(session_factory)


class ServiceProvider(Provider):
    """Provider for application services"""
    
    @provide(scope=Scope.REQUEST)
    def get_program_service(
        self,
        program_uow: SQLAlchemyProgramUnitOfWork
    ) -> ProgramService:
        """Create ProgramService with Program UoW"""
        return ProgramService(program_uow)
    
class ServiceProvider(Provider):
    """Provider for application services"""
    
    @provide(scope=Scope.REQUEST)
    def get_httpx_service(
        self,
        session_factory: async_sessionmaker,
        settings: Settings
    ) -> HTTPXScanService:
        """Create HTTPXScanService with UoW factory"""
        return HTTPXScanService(
            uow_factory=lambda: SQLAlchemyHTTPXUnitOfWork(session_factory),
            settings=settings
        )
    
    @provide(scope=Scope.REQUEST)
    def get_subfinder_service(
        self,
        httpx_service: HTTPXScanService,
        settings: Settings
    ) -> SubfinderScanService:
        """Create SubfinderScanService - depends on HTTPXScanService"""
        return SubfinderScanService(
            httpx_service=httpx_service,
            settings=settings
        )