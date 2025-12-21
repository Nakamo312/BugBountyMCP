import pytest
from unittest.mock import AsyncMock

from api.infrastructure.repositories.base_repo import UniqueConstraintViolation
from api.infrastructure.repositories.endpoint import EndpointRepository
from api.infrastructure.repositories.host import HostRepository
from api.infrastructure.repositories.ip_address import IPAddressRepository
from api.infrastructure.repositories.service import ServiceRepository
from sqlalchemy.exc import IntegrityError

@pytest.mark.asyncio
class TestEndpointRepository:
    
    async def test_create_endpoint(self, session, program):
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        endpoint_repo = EndpointRepository(session)
        
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
        await session.commit()
        
        endpoint = await endpoint_repo.create({
            'service_id': service.id,
            'host_id': host.id,
            'path': '/api/users',
            'normalized_path': '/api/users',
            'methods': ['GET', 'POST']
        })
        
        assert endpoint.id is not None
        assert 'GET' in endpoint.methods
        assert 'POST' in endpoint.methods
    
    async def test_duplicate_endpoint_same_host_path(self, session, program):
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        endpoint_repo = EndpointRepository(session)
        
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
        await session.commit()
        
        await endpoint_repo.create({
            'service_id': service.id,
            'host_id': host.id,
            'path': '/api/users',
            'normalized_path': '/api/users',
            'methods': ['GET']
        })
        await session.commit()
        
        # Same path should fail
        with pytest.raises((IntegrityError, UniqueConstraintViolation)):
            await endpoint_repo.create({
                'service_id': service.id,
                'host_id': host.id,
                'path': '/api/users',
                'normalized_path': '/api/users',
                'methods': ['POST']
            })
            await session.commit()
    
    async def test_add_method_to_endpoint(self, session, program):

        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        endpoint_repo = EndpointRepository(session)
        
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
        
        # Add new method
        updated = await endpoint_repo.add_method(endpoint.id, 'POST')
        await session.commit()
        
        assert 'GET' in updated.methods
        assert 'POST' in updated.methods
        
        # Adding same method again should not duplicate
        updated2 = await endpoint_repo.add_method(endpoint.id, 'POST')
        assert updated2.methods.count('POST') == 1
