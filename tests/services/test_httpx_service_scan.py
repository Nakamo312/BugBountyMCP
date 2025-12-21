"""Tests for HTTPXScanService with updated repository methods"""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from sqlalchemy import select, func

from api.infrastructure.database.models import (
    HostModel, 
    IPAddressModel, 
    ServiceModel, 
    EndpointModel, 
    InputParameterModel,
    HostIPModel
)
from api.application.services.httpx import HTTPXScanService
from api.infrastructure.repositories.host import HostRepository
from api.infrastructure.repositories.ip_address import IPAddressRepository
from api.infrastructure.repositories.host_ip import HostIPRepository
from api.infrastructure.repositories.service import ServiceRepository
from api.infrastructure.repositories.endpoint import EndpointRepository
from api.infrastructure.repositories.input_parameters import InputParameterRepository
from api.config import Settings
from api.application.dto import HTTPXScanInputDTO


@pytest.fixture
def httpx_service(session):
    """Create HTTPXScanService with all repositories"""
    settings = Settings()
    
    return HTTPXScanService(
        host_repository=HostRepository(session),
        ip_repository=IPAddressRepository(session),
        host_ip_repository=HostIPRepository(session),
        service_repository=ServiceRepository(session),
        endpoint_repository=EndpointRepository(session),
        input_param_repository=InputParameterRepository(session),
        settings=settings
    )


@pytest.mark.asyncio
class TestHTTPXScanServiceModel:

    async def test_execute_stores_data_in_db(
        self,
        httpx_service,
        program,
        session
    ):
        """Test that HTTPX scan results are properly stored in database"""
        
        # Mock scan data - УБЕРИТЕ title если нет такого поля
        fake_scan_data = [{
            "host": "example.com",
            "host_ip": "1.2.3.4",
            "scheme": "https",
            "port": 443,
            "method": "GET",
            "path": "/",
            "status_code": 200,
            "tech": ["nginx", "php"],
            "cname": ["cdn.example.com"],
            "a": ["1.2.3.4", "1.2.3.5"]
        }]

        async def mock_execute_scan(*args, **kwargs):
            for line in fake_scan_data:
                yield line

        # Мокаем execute_scan, а не _execute_scan
        httpx_service.execute_scan = mock_execute_scan

        # Create input DTO
        input_dto = HTTPXScanInputDTO(
            program_id=program.id,
            targets=["example.com"],
            timeout=600
        )

        # Execute scan
        result = await httpx_service.execute(input_dto)
        await session.commit()

        # Verify hosts
        hosts_result = await session.execute(
            select(HostModel).where(
                HostModel.program_id == program.id,
                HostModel.host == "example.com"
            )
        )
        hosts = hosts_result.scalars().all()
        
        assert len(hosts) == 1
        assert hosts[0].host == "example.com"
        assert "cdn.example.com" in hosts[0].cname
        assert hosts[0].in_scope is True

        # Verify IPs
        ips_result = await session.execute(
            select(IPAddressModel).where(
                IPAddressModel.program_id == program.id
            )
        )
        ips = ips_result.scalars().all()
        
        # Может быть только 1 IP, так как 1.2.3.4 дублируется в host_ip и a
        assert len(ips) >= 1
        ip_addresses = {ip.address for ip in ips}
        assert "1.2.3.4" in ip_addresses

        # Verify service
        services_result = await session.execute(
            select(ServiceModel).where(
                ServiceModel.ip_id.in_([ip.id for ip in ips])
            )
        )
        services = services_result.scalars().all()
        
        assert len(services) >= 1
        service = services[0]
        assert service.port == 443
        assert service.scheme == "https"
        assert service.technologies.get("nginx") is True
        assert service.technologies.get("php") is True

        # Verify endpoint
        endpoints_result = await session.execute(
            select(EndpointModel).where(
                EndpointModel.host_id == hosts[0].id
            )
        )
        endpoints = endpoints_result.scalars().all()
        
        assert len(endpoints) == 1
        assert endpoints[0].path == "/"
        assert "GET" in endpoints[0].methods
        assert endpoints[0].status_code == 200

        # Verify result summary
        assert result.hosts == 1
        assert result.endpoints == 1

    async def test_parameter_deduplication_in_db(
        self,
        httpx_service,
        program,
        session
    ):
        """Test that parameters are properly deduplicated"""
        
        # Вместо создания напрямую через репозитории, лучше через сервис
        
        # Mock scan data БЕЗ title
        fake_scan_data = [{
            "host": "example.com",
            "host_ip": "1.2.3.4",
            "scheme": "https",
            "port": 443,
            "method": "GET",
            "path": "/api?x=new_value&z=123",
            "status_code": 200,
            "tech": [],
            "cname": [],
            "a": ["1.2.3.4"]
        }]

        async def mock_execute_scan(*args, **kwargs):
            for line in fake_scan_data:
                yield line

        httpx_service.execute_scan = mock_execute_scan

        # Create input DTO
        input_dto = HTTPXScanInputDTO(
            program_id=program.id,
            targets=["example.com"],
            timeout=600
        )

        # Первый запуск сканирования
        await httpx_service.execute(input_dto)
        await session.commit()

        # Проверяем создание эндпоинта
        endpoints_result = await session.execute(
            select(EndpointModel).where(
                EndpointModel.path == "/api"
            )
        )
        endpoint = endpoints_result.scalar_one()
        
        # Проверяем параметры
        params_result = await session.execute(
            select(InputParameterModel).where(
                InputParameterModel.endpoint_id == endpoint.id
            )
        )
        params = params_result.scalars().all()
        
        # Должны быть 2 параметра: x и z
        assert len(params) == 2
        param_names = {p.name for p in params}
        assert "x" in param_names
        assert "z" in param_names

        # Теперь второй запуск с тем же параметром x
        fake_scan_data_2 = [{
            "host": "example.com",
            "host_ip": "1.2.3.4",
            "scheme": "https",
            "port": 443,
            "method": "GET",
            "path": "/api?x=different_value&z=123",  # x уже есть
            "status_code": 200,
            "tech": [],
            "cname": [],
            "a": ["1.2.3.4"]
        }]

        async def mock_execute_scan_2(*args, **kwargs):
            for line in fake_scan_data_2:
                yield line

        httpx_service.execute_scan = mock_execute_scan_2

        await httpx_service.execute(input_dto)
        await session.commit()

        # Проверяем что параметры не дублируются
        params_result_2 = await session.execute(
            select(InputParameterModel).where(
                InputParameterModel.endpoint_id == endpoint.id
            )
        )
        params_2 = params_result_2.scalars().all()
        
        # Все еще должно быть 2 параметра
        assert len(params_2) == 2

    async def test_method_merging_in_endpoints(
        self,
        httpx_service,
        program,
        session
    ):
        """Test that methods are properly merged into endpoint methods array"""
        
        # First scan with GET method
        fake_scan_data_1 = [{
            "host": "api.example.com",
            "host_ip": "1.2.3.4",
            "scheme": "https",
            "port": 443,
            "method": "GET",
            "path": "/api/users",
            "status_code": 200,
            "tech": [],
            "cname": [],
            "a": ["1.2.3.4"]
        }]

        async def mock_execute_scan_1(*args, **kwargs):
            for line in fake_scan_data_1:
                yield line

        httpx_service.execute_scan = mock_execute_scan_1
        
        # Create first DTO
        input_dto_1 = HTTPXScanInputDTO(
            program_id=program.id,
            targets=["api.example.com"],
            timeout=600
        )
        
        await httpx_service.execute(input_dto_1)
        await session.commit()

        endpoint_result = await session.execute(
            select(EndpointModel).where(EndpointModel.path == "/api/users")
        )
        endpoint = endpoint_result.scalar_one()
        assert "GET" in endpoint.methods
        assert len(endpoint.methods) == 1

        # Second scan with POST method
        fake_scan_data_2 = [{
            "host": "api.example.com",
            "host_ip": "1.2.3.4",
            "scheme": "https",
            "port": 443,
            "method": "POST",
            "path": "/api/users",
            "status_code": 201,
            "tech": [],
            "cname": [],
            "a": ["1.2.3.4"]
        }]

        async def mock_execute_scan_2(*args, **kwargs):
            for line in fake_scan_data_2:
                yield line

        httpx_service.execute_scan = mock_execute_scan_2
        
        # Create second DTO
        input_dto_2 = HTTPXScanInputDTO(
            program_id=program.id,
            targets=["api.example.com"],
            timeout=600
        )
        
        await httpx_service.execute(input_dto_2)
        await session.commit()

        # Verify endpoint now has both methods
        endpoint_result = await session.execute(
            select(EndpointModel).where(EndpointModel.path == "/api/users")
        )
        endpoint = endpoint_result.scalar_one()
        assert "GET" in endpoint.methods
        assert "POST" in endpoint.methods
        assert len(endpoint.methods) == 2

    async def test_technology_merging_in_services(
        self,
        httpx_service,
        program,
        session
    ):
        """Test that technologies are properly merged in services"""
        
        program_uuid = program.id
        
        # First scan with nginx
        fake_scan_data_1 = [{
            "host": "example.com",
            "host_ip": "1.2.3.4",
            "scheme": "https",
            "port": 443,
            "method": "GET",
            "path": "/",
            "status_code": 200,
            "tech": ["nginx"],
            "cname": [],
            "a": ["1.2.3.4"]
        }]

        async def mock_execute_scan_1(*args, **kwargs):
            for line in fake_scan_data_1:
                yield line

        httpx_service.execute_scan = mock_execute_scan_1
        
        input_dto_1 = HTTPXScanInputDTO(
            program_id=program_uuid,
            targets=["example.com"],
            timeout=600
        )
        
        await httpx_service.execute(input_dto_1)
        await session.commit()

        # Get the created service
        service_result = await session.execute(
            select(ServiceModel).where(ServiceModel.port == 443)
        )
        service = service_result.scalar_one()
        assert service.technologies.get("nginx") is True

        # Second scan adds php
        fake_scan_data_2 = [{
            "host": "example.com",
            "host_ip": "1.2.3.4",
            "scheme": "https",
            "port": 443,
            "method": "GET",
            "path": "/index.php",
            "status_code": 200,
            "tech": ["php"],
            "cname": [],
            "a": ["1.2.3.4"]
        }]

        async def mock_execute_scan_2(*args, **kwargs):
            for line in fake_scan_data_2:
                yield line

        httpx_service.execute_scan = mock_execute_scan_2
        
        input_dto_2 = HTTPXScanInputDTO(
            program_id=program_uuid,
            targets=["example.com"],
            timeout=600
        )
        
        await httpx_service.execute(input_dto_2)
        await session.commit()

        # Verify service now has both technologies
        await session.refresh(service)
        assert service.technologies.get("nginx") is True
        assert service.technologies.get("php") is True

    async def test_cname_merging(
        self,
        httpx_service,
        program,
        session
    ):
        """Test that CNAMEs are properly merged"""
        
        program_uuid = program.id
        
        # First scan with one CNAME
        fake_scan_data_1 = [{
            "host": "example.com",
            "host_ip": "1.2.3.4",
            "scheme": "https",
            "port": 443,
            "method": "GET",
            "path": "/",
            "status_code": 200,
            "tech": [],
            "cname": ["cdn1.example.com"],
            "a": ["1.2.3.4"]
        }]

        async def mock_execute_scan_1(*args, **kwargs):
            for line in fake_scan_data_1:
                yield line

        httpx_service.execute_scan = mock_execute_scan_1
        
        input_dto_1 = HTTPXScanInputDTO(
            program_id=program_uuid,
            targets=["example.com"],
            timeout=600
        )
        
        await httpx_service.execute(input_dto_1)
        await session.commit()

        # Get the host
        host_result = await session.execute(
            select(HostModel).where(
                HostModel.program_id == program_uuid,
                HostModel.host == "example.com"
            )
        )
        host = host_result.scalar_one()
        assert "cdn1.example.com" in host.cname

        # Second scan adds another CNAME
        fake_scan_data_2 = [{
            "host": "example.com",
            "host_ip": "1.2.3.4",
            "scheme": "https",
            "port": 443,
            "method": "GET",
            "path": "/",
            "status_code": 200,
            "tech": [],
            "cname": ["cdn2.example.com"],
            "a": ["1.2.3.4"]
        }]

        async def mock_execute_scan_2(*args, **kwargs):
            for line in fake_scan_data_2:
                yield line

        httpx_service.execute_scan = mock_execute_scan_2
        
        input_dto_2 = HTTPXScanInputDTO(
            program_id=program_uuid,
            targets=["example.com"],
            timeout=600
        )
        
        await httpx_service.execute(input_dto_2)
        await session.commit()

        # Verify both CNAMEs are present
        await session.refresh(host)
        assert "cdn1.example.com" in host.cname
        assert "cdn2.example.com" in host.cname
        assert len(host.cname) == 2