"""Fixtures for service layer tests"""
import pytest

from api.application.services.httpx import HTTPXScanService
from api.infrastructure.repositories.host import HostRepository
from api.infrastructure.repositories.ip_address import IPAddressRepository
from api.infrastructure.repositories.host_ip import HostIPRepository
from api.infrastructure.repositories.service import ServiceRepository
from api.infrastructure.repositories.endpoint import EndpointRepository
from api.infrastructure.repositories.input_parameters import InputParameterRepository
from api.config import Settings


@pytest.fixture
def host_repository(session):
    """Host repository instance"""
    return HostRepository(session)

@pytest.fixture
def settings():
    """Settings instance"""
    return Settings()

@pytest.fixture
def ip_repository(session):
    """IP address repository instance"""
    return IPAddressRepository(session)


@pytest.fixture
def host_ip_repository(session):
    """Host-IP link repository instance"""
    return HostIPRepository(session)


@pytest.fixture
def service_repository(session):
    """Service repository instance"""
    return ServiceRepository(session)


@pytest.fixture
def endpoint_repository(session):
    """Endpoint repository instance"""
    return EndpointRepository(session)


@pytest.fixture
def input_param_repository(session):
    """Input parameter repository instance"""
    return InputParameterRepository(session)


@pytest.fixture
def httpx_service(
    session,
    host_repository,
    ip_repository,
    host_ip_repository,
    service_repository,
    endpoint_repository,
    input_param_repository
):
    """HTTPXScanService instance with all dependencies"""
    return HTTPXScanService(
        host_repository=host_repository,
        ip_repository=ip_repository,
        host_ip_repository=host_ip_repository,
        service_repository=service_repository,
        endpoint_repository=endpoint_repository,
        input_param_repository=input_param_repository,
    )