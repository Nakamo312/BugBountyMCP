import pytest
from unittest.mock import AsyncMock

from api.infrastructure.repositories.base_repo import UniqueConstraintViolation
from api.infrastructure.repositories.ip_address import IPAddressRepository
from api.infrastructure.repositories.service import ServiceRepository
from sqlalchemy.exc import IntegrityError

@pytest.mark.asyncio
class TestServiceRepository:
    
    async def test_create_service(self, session, program):
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        
        ip = await ip_repo.create({
            'program_id': program.id,
            'address': '1.2.3.4'
        })
        await session.commit()
        
        service = await service_repo.create({
            'ip_id': ip.id,
            'scheme': 'https',
            'port': 443,
            'technologies': {'server': 'nginx'}
        })
        
        assert service.id is not None
        assert service.port == 443
    
    async def test_duplicate_service_same_ip_port(self, session, program):
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        
        ip = await ip_repo.create({
            'program_id': program.id,
            'address': '1.2.3.4'
        })
        await session.commit()
        
        await service_repo.create({
            'ip_id': ip.id,
            'scheme': 'https',
            'port': 443
        })
        await session.commit()
        
        with pytest.raises((IntegrityError, UniqueConstraintViolation)):
            await service_repo.create({
                'ip_id': ip.id,
                'scheme': 'http',
                'port': 443
            })
            await session.commit()
    
    async def test_get_or_create_with_tech_merge(self, session, program):
        ip_repo = IPAddressRepository(session)
        service_repo = ServiceRepository(session)
        
        ip = await ip_repo.create({
            'program_id': program.id,
            'address': '1.2.3.4'
        })
        await session.commit()
        
        # Create with initial technology
        service1 = await service_repo.get_or_create_with_tech(
            ip_id=ip.id,
            scheme='https',
            port=443,
            technologies={'server': 'nginx'}
        )
        await session.commit()
        
        # Get same service and add new technology
        service2 = await service_repo.get_or_create_with_tech(
            ip_id=ip.id,
            scheme='https',
            port=443,
            technologies={'language': 'python'}
        )
        await session.commit()
        
        assert service1.id == service2.id
        assert 'server' in service2.technologies
        assert 'language' in service2.technologies