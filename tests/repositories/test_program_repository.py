import pytest
from api.infrastructure.repositories.base_repo import UniqueConstraintViolation
from sqlalchemy.exc import IntegrityError
from api.infrastructure.repositories.program import ProgramRepository

@pytest.mark.asyncio
class TestProgramRepository:
    
    async def test_create_program(self, session):      
        repo = ProgramRepository(session)
        program = await repo.create({'name': 'my_program'})
        
        assert program.id is not None
        assert program.name == 'my_program'
    
    async def test_duplicate_program_name(self, session):      
        repo = ProgramRepository(session)
        await repo.create({'name': 'duplicate'})
        await session.commit()
        
        with pytest.raises((IntegrityError, UniqueConstraintViolation)):
            await repo.create({'name': 'duplicate'})
            await session.commit()
    
    async def test_get_by_name(self, session, program):
        repo = ProgramRepository(session)
        found = await repo.get_by_name('test_program')
        
        assert found is not None
        assert found.id == program.id
    
    async def test_get_or_create(self, session): 
        repo = ProgramRepository(session)
        
        # Create new
        prog1, created1 = await repo.get_or_create(name='new_prog')
        assert created1 is True
        await session.commit()
        
        # Get existing
        prog2, created2 = await repo.get_or_create(name='new_prog')
        assert created2 is False
        assert prog1.id == prog2.id