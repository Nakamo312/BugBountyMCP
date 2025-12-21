"""Dependency Injection providers using dishka"""
from dishka import Provider, Scope, provide, from_context
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..infrastructure.database.connection import DatabaseConnection
from ..infrastructure.repositories.host import HostRepository
from ..infrastructure.repositories.ip_address import IPAddressRepository
from ..infrastructure.repositories.host_ip import HostIPRepository
from ..infrastructure.repositories.service import ServiceRepository
from ..infrastructure.repositories.endpoint import EndpointRepository
from ..infrastructure.repositories.input_parameters import InputParameterRepository
from .services.httpx import HTTPXScanService
from .services.subfinder import SubfinderScanService


class DatabaseProvider(Provider):
    """Provider for database connections"""
    
    settings = from_context(provides=Settings, scope=Scope.APP)
    session = from_context(provides=AsyncSession, scope=Scope.REQUEST)
    
    @provide(scope=Scope.APP)
    def get_database_connection(
        self,
        settings: Settings,
    ) -> DatabaseConnection:
        """Create database connection"""
        return DatabaseConnection(settings.postgres_dsn)


class RepositoryProvider(Provider):
    """Provider for repositories"""
    
    @provide(scope=Scope.REQUEST)
    def get_host_repository(
        self,
        session: AsyncSession,
    ) -> HostRepository:
        """Create HostRepository"""
        return HostRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_ip_repository(
        self,
        session: AsyncSession,
    ) -> IPAddressRepository:
        """Create IPAddressRepository"""
        return IPAddressRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_host_ip_repository(
        self,
        session: AsyncSession,
    ) -> HostIPRepository:
        """Create HostIPRepository"""
        return HostIPRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_service_repository(
        self,
        session: AsyncSession,
    ) -> ServiceRepository:
        """Create ServiceRepository"""
        return ServiceRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_endpoint_repository(
        self,
        session: AsyncSession,
    ) -> EndpointRepository:
        """Create EndpointRepository"""
        return EndpointRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_input_param_repository(
        self,
        session: AsyncSession,
    ) -> InputParameterRepository:
        """Create InputParameterRepository"""
        return InputParameterRepository(session)


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
    ) -> HTTPXScanService:
        """Create HTTPXScanService with all dependencies"""
        return HTTPXScanService(
            host_repository=host_repository,
            ip_repository=ip_repository,
            host_ip_repository=host_ip_repository,
            service_repository=service_repository,
            endpoint_repository=endpoint_repository,
            input_param_repository=input_param_repository,
        )
    
    @provide(scope=Scope.REQUEST)
    def get_subfinder_service(
        self,
        httpx_service: HTTPXScanService,
    ) -> SubfinderScanService:
        """Create SubfinderScanService - depends only on HTTPXScanService"""
        return SubfinderScanService(httpx_service=httpx_service)

