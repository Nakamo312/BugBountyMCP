import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.infrastructure.database.models import IPAddressModel
from api.infrastructure.repositories.base_repo import UniqueConstraintViolation
from api.infrastructure.repositories.ip_address import IPAddressRepository
from sqlalchemy.exc import IntegrityError

@pytest.mark.asyncio
class TestIPAddressRepository:
    
    async def test_create_ip(self, session, program):
        
        repo = IPAddressRepository(session)
        ip = await repo.create({
            'program_id': program.id,
            'address': '192.168.1.1',
            'in_scope': True
        })
        
        assert ip.id is not None
        assert ip.address == '192.168.1.1'
    
    async def test_duplicate_ip_in_program(self, session, program):
        
        repo = IPAddressRepository(session)
        await repo.create({
            'program_id': program.id,
            'address': '10.0.0.1'
        })
        await session.commit()
        
        with pytest.raises((IntegrityError, UniqueConstraintViolation)):
            await repo.create({
                'program_id': program.id,
                'address': '10.0.0.1'
            })
            await session.commit()
    
    async def test_find_by_address(self, session, program):
        
        repo = IPAddressRepository(session)
        created_ip = await repo.create({
            'program_id': program.id,
            'address': '1.1.1.1'
        })
        await session.commit()
        
        found = await repo.find_by_address(program.id, '1.1.1.1')
        assert found is not None
        assert found.id == created_ip.id
