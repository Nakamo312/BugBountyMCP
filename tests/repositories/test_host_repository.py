import pytest
from unittest.mock import AsyncMock
from sqlalchemy.exc import IntegrityError
from api.infrastructure.repositories.base_repo import UniqueConstraintViolation
from api.infrastructure.repositories.host import HostRepository
from api.infrastructure.repositories.program import ProgramRepository


@pytest.mark.asyncio
class TestHostRepository:
    
    async def test_create_host(self, session, program):      
        repo = HostRepository(session)
        host = await repo.create({
            'program_id': program.id,
            'host': 'example.com',
            'in_scope': True
        })
        
        assert host.id is not None
        assert host.host == 'example.com'
    
    async def test_duplicate_host_in_program(self, session, program):    
        repo = HostRepository(session)
        await repo.create({
            'program_id': program.id,
            'host': 'duplicate.com'
        })
        await session.commit()
        
        with pytest.raises((IntegrityError, UniqueConstraintViolation)):
            await repo.create({
                'program_id': program.id,
                'host': 'duplicate.com'
            })
            await session.commit()
    
    async def test_same_host_different_programs(self, session):       
        prog_repo = ProgramRepository(session)
        host_repo = HostRepository(session)
        
        prog1 = await prog_repo.create({'name': 'prog1'})
        prog2 = await prog_repo.create({'name': 'prog2'})
        await session.commit()
        
        host1 = await host_repo.create({
            'program_id': prog1.id,
            'host': 'shared.com'
        })
        host2 = await host_repo.create({
            'program_id': prog2.id,
            'host': 'shared.com'
        })
        await session.commit()
        
        assert host1.id != host2.id
        assert host1.host == host2.host
    
    async def test_get_by_program(self, session, program):     
        repo = HostRepository(session)
        await repo.create({'program_id': program.id, 'host': 'host1.com'})
        await repo.create({'program_id': program.id, 'host': 'host2.com'})
        await session.commit()
        
        hosts = await repo.get_by_program(program.id)
        assert len(hosts) == 2
