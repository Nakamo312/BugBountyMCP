import pytest
from api.infrastructure.repositories.endpoint import EndpointRepository
from api.infrastructure.repositories.header import HeaderRepository
from api.infrastructure.repositories.host import HostRepository
from api.infrastructure.repositories.ip_address import IPAddressRepository
from api.infrastructure.repositories.service import ServiceRepository


@pytest.mark.asyncio
class TestHeaderRepository:
    
    async def test_create_header(self, session, program):
        # Setup
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        endpoint_repo = EndpointRepository(session)
        header_repo = HeaderRepository(session)
        
        host = await host_repo.create({
            'program_id': program.id,
            'host': 'api.example.com'
        })
        ip = await ip_repo.create({
            'program_id': program.id,
            'address': '1.2.3.4'
        })
        service = await service_repo.create({
            'ip_id': ip.id,
            'scheme': 'https',
            'port': 443
        })
        endpoint = await endpoint_repo.create({
            'service_id': service.id,
            'host_id': host.id,
            'path': '/api/users',
            'normalized_path': '/api/users',
            'methods': ['GET']
        })
        await session.commit()
        
        # Create request header
        header = await header_repo.create({
            'endpoint_id': endpoint.id,
            'name': 'Content-Type',
            'value': 'application/json',
            'header_type': 'request'
        })
        
        assert header.id is not None
        assert header.header_type == 'request'
    
    async def test_same_header_request_and_response(self, session, program):
        # Setup
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        endpoint_repo = EndpointRepository(session)
        header_repo = HeaderRepository(session)
        
        host = await host_repo.create({
            'program_id': program.id,
            'host': 'api.example.com'
        })
        ip = await ip_repo.create({
            'program_id': program.id,
            'address': '1.2.3.4'
        })
        service = await service_repo.create({
            'ip_id': ip.id,
            'scheme': 'https',
            'port': 443
        })
        endpoint = await endpoint_repo.create({
            'service_id': service.id,
            'host_id': host.id,
            'path': '/api/users',
            'normalized_path': '/api/users',
            'methods': ['GET']
        })
        await session.commit()
        
        # Same header name but different types should work
        req_header = await header_repo.create({
            'endpoint_id': endpoint.id,
            'name': 'Content-Type',
            'value': 'application/json',
            'header_type': 'request'
        })
        resp_header = await header_repo.create({
            'endpoint_id': endpoint.id,
            'name': 'Content-Type',
            'value': 'application/json',
            'header_type': 'response'
        })
        await session.commit()
        
        assert req_header.id != resp_header.id
    
    async def test_get_headers_by_type(self, session, program):
        # Setup
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        endpoint_repo = EndpointRepository(session)
        header_repo = HeaderRepository(session)
        
        host = await host_repo.create({
            'program_id': program.id,
            'host': 'api.example.com'
        })
        ip = await ip_repo.create({
            'program_id': program.id,
            'address': '1.2.3.4'
        })
        service = await service_repo.create({
            'ip_id': ip.id,
            'scheme': 'https',
            'port': 443
        })
        endpoint = await endpoint_repo.create({
            'service_id': service.id,
            'host_id': host.id,
            'path': '/api/users',
            'normalized_path': '/api/users',
            'methods': ['GET']
        })
        
        await header_repo.create({
            'endpoint_id': endpoint.id,
            'name': 'Authorization',
            'value': 'Bearer token',
            'header_type': 'request'
        })
        await header_repo.create({
            'endpoint_id': endpoint.id,
            'name': 'Server',
            'value': 'nginx',
            'header_type': 'response'
        })
        await session.commit()
        
        request_headers = await header_repo.get_request_headers(endpoint.id)
        response_headers = await header_repo.get_response_headers(endpoint.id)
        
        assert len(request_headers) == 1
        assert len(response_headers) == 1
        assert request_headers[0].name == 'Authorization'
        assert response_headers[0].name == 'Server'