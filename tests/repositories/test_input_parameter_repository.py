import pytest
from unittest.mock import AsyncMock, MagicMock

from api.infrastructure.repositories.base_repo import UniqueConstraintViolation
from api.infrastructure.repositories.endpoint import EndpointRepository
from api.infrastructure.repositories.host import HostRepository
from api.infrastructure.repositories.input_parameters import (
    InputParameterRepository
)
from api.infrastructure.repositories.ip_address import IPAddressRepository
from api.infrastructure.repositories.service import ServiceRepository
from sqlalchemy.exc import IntegrityError

@pytest.mark.asyncio
class TestInputParameterRepository:
    
    async def test_create_parameter(self, session, program):
        # Setup
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        endpoint_repo = EndpointRepository(session)
        param_repo = InputParameterRepository(session)
        
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
        
        # Create parameter
        param = await param_repo.create({
            'endpoint_id': endpoint.id,
            'name': 'user_id',
            'location': 'query',
            'param_type': 'string'
        })
        
        assert param.id is not None
        assert param.name == 'user_id'
    
    async def test_duplicate_param_same_endpoint_location_name(self, session, program):

        # Setup (similar to above)
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        endpoint_repo = EndpointRepository(session)
        param_repo = InputParameterRepository(session)
        
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
        
        await param_repo.create({
            'endpoint_id': endpoint.id,
            'name': 'id',
            'location': 'query',
            'param_type': 'string'
        })
        await session.commit()
        
        # Same endpoint, location, and name should fail
        with pytest.raises((IntegrityError, UniqueConstraintViolation)):
            await param_repo.create({
                'endpoint_id': endpoint.id,
                'name': 'id',
                'location': 'query',
                'param_type': 'integer'
            })
            await session.commit()
    
    async def test_same_name_different_locations(self, session, program):

        # Setup
        host_repo = HostRepository(session)
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        endpoint_repo = EndpointRepository(session)
        param_repo = InputParameterRepository(session)
        
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
            'methods': ['GET', 'POST']
        })
        await session.commit()
        
        # Same name but different locations should work
        param1 = await param_repo.create({
            'endpoint_id': endpoint.id,
            'name': 'id',
            'location': 'query',
            'param_type': 'string'
        })
        param2 = await param_repo.create({
            'endpoint_id': endpoint.id,
            'name': 'id',
            'location': 'body',
            'param_type': 'string'
        })
        await session.commit()
        
        assert param1.id != param2.id