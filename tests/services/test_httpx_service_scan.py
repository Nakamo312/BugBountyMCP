"""Tests for HTTPXScanService with updated repository methods"""
import pytest
from uuid import UUID
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


@pytest.fixture
def httpx_service(session):
    """Create HTTPXScanService with all repositories"""
    return HTTPXScanService(
        host_repository=HostRepository(session),
        ip_repository=IPAddressRepository(session),
        host_ip_repository=HostIPRepository(session),
        service_repository=ServiceRepository(session),
        endpoint_repository=EndpointRepository(session),
        input_param_repository=InputParameterRepository(session),
        settings=Settings()
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
        
        # Mock scan data
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

        async def fake_execute_scan(*args, **kwargs):
            for line in fake_scan_data:
                yield line

        httpx_service.execute_scan = fake_execute_scan

        # Execute scan
        result = await httpx_service.execute(str(program.id), ["example.com"])
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
        
        assert len(ips) == 2
        ip_addresses = {ip.address for ip in ips}
        assert "1.2.3.4" in ip_addresses
        assert "1.2.3.5" in ip_addresses

        # Verify host-IP links
        links_result = await session.execute(
            select(HostIPModel).where(HostIPModel.host_id == hosts[0].id)
        )
        links = links_result.scalars().all()
        assert len(links) == 2

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
        assert result["hosts"] == 1
        assert result["endpoints"] == 1

    async def test_parameter_deduplication_in_db(
        self,
        httpx_service,
        program,
        session
    ):
        """Test that parameters are properly deduplicated"""
        
        program_uuid = program.id
        
        # Create initial host
        host_repo = HostRepository(session)
        host, _ = await host_repo.get_or_create(
            program_id=program_uuid,
            host="example.com",
            defaults={"in_scope": True}
        )
        await session.commit()
        
        # Create IP and service
        ip_repo = IPAddressRepository(session)
        ip, _ = await ip_repo.get_or_create(
            program_id=program_uuid,
            address="1.2.3.4",
            defaults={"in_scope": True}
        )
        
        service_repo = ServiceRepository(session)
        service = await service_repo.get_or_create_with_tech(
            ip_id=ip.id,
            scheme="https",
            port=443
        )
        
        # Create initial endpoint with one parameter
        endpoint_repo = EndpointRepository(session)
        endpoint = await endpoint_repo.create({
            "service_id": service.id,
            "host_id": host.id,
            "path": "/api",
            "normalized_path": "/api",
            "methods": ["GET"],
            "status_code": 200
        })
        
        param_repo = InputParameterRepository(session)
        await param_repo.create({
            "endpoint_id": endpoint.id,
            "name": "x",
            "location": "query",
            "param_type": "string"
        })
        await session.commit()

        # Verify initial state
        params_before = await session.execute(
            select(InputParameterModel).where(
                InputParameterModel.endpoint_id == endpoint.id
            )
        )
        assert len(params_before.scalars().all()) == 1

        # Mock new scan with duplicate parameter "x" and new parameter "z"
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

        async def fake_execute_scan(*args, **kwargs):
            for line in fake_scan_data:
                yield line

        httpx_service.execute_scan = fake_execute_scan

        # Execute scan
        await httpx_service.execute(str(program_uuid), ["example.com"])
        await session.commit()

        # Verify parameters after scan
        params_after = await session.execute(
            select(InputParameterModel).where(
                InputParameterModel.endpoint_id == endpoint.id
            )
        )
        all_params = params_after.scalars().all()
        
        # Should have 2 unique parameters: x and z
        assert len(all_params) == 2
        param_names = {p.name for p in all_params}
        assert "x" in param_names
        assert "z" in param_names

    async def test_method_merging_in_endpoints(
        self,
        httpx_service,
        program,
        session
    ):
        """Test that methods are properly merged into endpoint methods array"""
        
        program_uuid = program.id
        
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

        async def fake_execute_scan_1(*args, **kwargs):
            for line in fake_scan_data_1:
                yield line

        httpx_service.execute_scan = fake_execute_scan_1
        await httpx_service.execute(str(program_uuid), ["api.example.com"])
        await session.commit()

        endpoint_result = await session.execute(
            select(EndpointModel).where(EndpointModel.path == "/api/users")
        )
        endpoint = endpoint_result.scalar_one()
        assert "GET" in endpoint.methods
        assert len(endpoint.methods) == 1

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

        async def fake_execute_scan_2(*args, **kwargs):
            for line in fake_scan_data_2:
                yield line

        httpx_service.execute_scan = fake_execute_scan_2
        await httpx_service.execute(str(program_uuid), ["api.example.com"])
        await session.commit()

        endpoint_result = await session.execute(
            select(EndpointModel).where(EndpointModel.path == "/api/users")
        )
        endpoint = endpoint_result.scalars().all()[0]
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

        async def fake_execute_scan_1(*args, **kwargs):
            for line in fake_scan_data_1:
                yield line

        httpx_service.execute_scan = fake_execute_scan_1
        await httpx_service.execute(str(program_uuid), ["example.com"])
        await session.commit()

        # Verify initial service has nginx
        service_result = await session.execute(
            select(ServiceModel).where(ServiceModel.port == 443)
        )
        service = service_result.scalar_one()
        assert service.technologies.get("nginx") is True

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

        async def fake_execute_scan_2(*args, **kwargs):
            for line in fake_scan_data_2:
                yield line

        httpx_service.execute_scan = fake_execute_scan_2
        await httpx_service.execute(str(program_uuid), ["example.com"])
        await session.commit()

        # Verify service now has both technologies
        await session.refresh(service)
        assert service.technologies.get("nginx") is True
        assert service.technologies.get("php") is True

    async def test_bulk_insert_performance(
        self,
        httpx_service,
        program,
        session
    ):
        """Test bulk insertion of many hosts and endpoints"""
        
        program_uuid = program.id
        
        # Generate 100 fake scan results
        fake_scan_data = [
            {
                "host": f"example{i}.com",
                "host_ip": f"1.2.3.{(i % 254) + 1}",
                "scheme": "https",
                "port": 443,
                "method": "GET",
                "path": f"/path{i}",
                "status_code": 200,
                "tech": [],
                "cname": [],
                "a": [f"1.2.3.{(i % 254) + 1}"]
            }
            for i in range(100)
        ]

        async def fake_execute_scan(*args, **kwargs):
            for line in fake_scan_data:
                yield line

        httpx_service.execute_scan = fake_execute_scan

        # Execute scan
        result = await httpx_service.execute(
            str(program_uuid),
            [f"example{i}.com" for i in range(100)]
        )
        await session.commit()

        # Verify results
        hosts_count = await session.execute(
            select(func.count()).select_from(HostModel).where(
                HostModel.program_id == program_uuid
            )
        )
        assert hosts_count.scalar() == 100
        
        endpoints_count = await session.execute(
            select(func.count()).select_from(EndpointModel)
        )
        assert endpoints_count.scalar() == 100
        
        assert result["hosts"] == 100
        assert result["endpoints"] == 100

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

        async def fake_execute_scan_1(*args, **kwargs):
            for line in fake_scan_data_1:
                yield line

        httpx_service.execute_scan = fake_execute_scan_1
        await httpx_service.execute(str(program_uuid), ["example.com"])
        await session.commit()

        # Verify initial CNAME
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

        async def fake_execute_scan_2(*args, **kwargs):
            for line in fake_scan_data_2:
                yield line

        httpx_service.execute_scan = fake_execute_scan_2
        await httpx_service.execute(str(program_uuid), ["example.com"])
        await session.commit()

        # Verify both CNAMEs are present
        await session.refresh(host)
        assert "cdn1.example.com" in host.cname
        assert "cdn2.example.com" in host.cname
        assert len(host.cname) == 2