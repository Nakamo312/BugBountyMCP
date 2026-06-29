from typing import AsyncIterable

from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config import Settings
from api.infrastructure.database.connection import DatabaseConnection
from api.infrastructure.unit_of_work.adapters.asnmap import SQLAlchemyASNMapUnitOfWork
from api.infrastructure.unit_of_work.adapters.dnsx import SQLAlchemyDNSxUnitOfWork
from api.infrastructure.unit_of_work.adapters.httpx import SQLAlchemyHTTPXUnitOfWork
from api.infrastructure.unit_of_work.adapters.infrastructure import SQLAlchemyInfrastructureUnitOfWork
from api.infrastructure.unit_of_work.adapters.katana import SQLAlchemyKatanaUnitOfWork
from api.infrastructure.unit_of_work.adapters.mantra import SQLAlchemyMantraUnitOfWork
from api.infrastructure.unit_of_work.adapters.naabu import SQLAlchemyNaabuUnitOfWork
from api.infrastructure.unit_of_work.adapters.program import SQLAlchemyProgramUnitOfWork
from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork


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
    scope = Scope.APP

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
