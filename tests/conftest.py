import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from api.domain.models import (
    HostModel,
    IPAddressModel,
    ServiceModel,
    EndpointModel,
    InputParameterModel,
    ProgramModel,
    ScopeRuleModel
)
from api.domain.enums import HttpMethod, ParamLocation, RuleType
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork


@pytest.fixture
def mock_uow():
    uow = AsyncMock(spec=HTTPXUnitOfWork)

    uow.hosts = AsyncMock()
    uow.ips = AsyncMock()
    uow.host_ips = AsyncMock()
    uow.services = AsyncMock()
    uow.endpoints = AsyncMock()
    uow.input_parameters = AsyncMock()

    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.create_savepoint = AsyncMock()
    uow.rollback_to_savepoint = AsyncMock()
    uow.release_savepoint = AsyncMock()

    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)

    return uow


@pytest.fixture
def sample_program():
    return ProgramModel(
        id=uuid4(),
        name="hackerone"
    )


@pytest.fixture
def sample_host():
    return HostModel(
        id=uuid4(),
        host="example.com",
        program_id=uuid4()
    )


@pytest.fixture
def sample_ip():
    return IPAddressModel(
        id=uuid4(),
        address="1.2.3.4",
        program_id=uuid4()
    )


@pytest.fixture
def sample_service():
    return ServiceModel(
        id=uuid4(),
        ip_id=uuid4(),
        port=443,
        scheme="https"
    )


@pytest.fixture
def sample_endpoint():
    return EndpointModel(
        id=uuid4(),
        host_id=uuid4(),
        service_id=uuid4(),
        path="/api/users",
        normalized_path="/api/users",
        methods=[HttpMethod.GET]
    )


@pytest.fixture
def sample_input_parameter():
    return InputParameterModel(
        id=uuid4(),
        endpoint_id=uuid4(),
        service_id=uuid4(),
        name="user_id",
        location=ParamLocation.QUERY,
        param_type="string",
        example_value="123"
    )


@pytest.fixture
def sample_scope_rule():
    return ScopeRuleModel(
        id=uuid4(),
        program_id=uuid4(),
        rule_type=RuleType.DOMAIN,
        pattern="example.com"
    )
