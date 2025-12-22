"""Dependency Injection providers using dishka"""
from typing import AsyncIterable
from dishka import Provider, Scope, provide, from_context
from sqlalchemy.ext.asyncio import AsyncSession

from api.infrastructure.repositories.adapters.endpoint import SQLAlchemyEndpointRepository
from api.infrastructure.repositories.adapters.host import SQLAlchemyHostRepository
from api.infrastructure.repositories.adapters.host_ip import SQLAlchemyHostIPRepository
from api.infrastructure.repositories.adapters.input_parameters import SQLAlchemyInputParameterRepository
from api.infrastructure.repositories.adapters.ip_address import SQLAlchemyIPAddressRepository
from api.infrastructure.repositories.adapters.service import SQLAlchemyServiceRepository
from api.infrastructure.repositories.interfaces.endpoint import EndpointRepository
from api.infrastructure.repositories.interfaces.host_ip import HostIPRepository
from api.infrastructure.repositories.interfaces.service import ServiceRepository

from ..config import Settings
from ..infrastructure.database.connection import DatabaseConnection
from ..infrastructure.repositories.interfaces.host import HostRepository
from ..infrastructure.repositories.interfaces.ip_address import IPAddressRepository
from ..infrastructure.repositories.interfaces.input_parameters import InputParameterRepository
from .services.httpx import HTTPXScanService
from .services.subfinder import SubfinderScanService


class DatabaseProvider(Provider):
    scope = Scope.APP
    
    settings = from_context(provides=Settings) 

    @provide(scope=Scope.APP)
    def get_database_connection(self, settings: Settings) -> DatabaseConnection:
        return DatabaseConnection(settings.postgres_dsn)

    @provide(scope=Scope.REQUEST)
    async def get_session(self, db: DatabaseConnection) -> AsyncIterable[AsyncSession]:
        async with db.session() as session:
            yield session


class RepositoryProvider(Provider):
    """Provider for repositories"""
    
    @provide(scope=Scope.REQUEST)
    def get_host_repository(
        self,
        session: AsyncSession,
    ) -> HostRepository:
        """Create HostRepository"""
        return SQLAlchemyHostRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_ip_repository(
        self,
        session: AsyncSession,
    ) -> IPAddressRepository:
        """Create IPAddressRepository"""
        return SQLAlchemyIPAddressRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_host_ip_repository(
        self,
        session: AsyncSession,
    ) -> HostIPRepository:
        """Create HostIPRepository"""
        return SQLAlchemyHostIPRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_service_repository(
        self,
        session: AsyncSession,
    ) -> ServiceRepository:
        """Create ServiceRepository"""
        return SQLAlchemyServiceRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_endpoint_repository(
        self,
        session: AsyncSession,
    ) -> EndpointRepository:
        """Create EndpointRepository"""
        return SQLAlchemyEndpointRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_input_param_repository(
        self,
        session: AsyncSession,
    ) -> InputParameterRepository:
        """Create InputParameterRepository"""
        return SQLAlchemyInputParameterRepository(session)


class ServiceProvider(Provider):
    """Provider for application services"""
    
    @provide(scope=Scope.REQUEST)
    def get_httpx_service(
        self,
        host_repository: HostRepository,
        ip_repository: IPAddressRepository,
        host_ip_repository: HostIPRepository,
        service_repository: ServiceRepository,
        endpoint_repository: EndpointRepository,
        input_param_repository: InputParameterRepository,
        settings: Settings
    ) -> HTTPXScanService:
        """Create HTTPXScanService with all dependencies"""
        return HTTPXScanService(
            host_repository=host_repository,
            ip_repository=ip_repository,
            host_ip_repository=host_ip_repository,
            service_repository=service_repository,
            endpoint_repository=endpoint_repository,
            input_param_repository=input_param_repository,
            settings=settings
        )
    
    @provide(scope=Scope.REQUEST)
    def get_subfinder_service(
        self,
        httpx_service: HTTPXScanService,
        settings: Settings
    ) -> SubfinderScanService:
        """Create SubfinderScanService - depends only on HTTPXScanService"""
        return SubfinderScanService(httpx_service=httpx_service, settings=settings)

