from api.infrastructure.repositories.adapters.program import \
    SQLAlchemyProgramRepository
from api.infrastructure.repositories.adapters.root_input import \
    SQLAlchemyRootInputRepository
from api.infrastructure.repositories.adapters.scope_rule import \
    SQLAlchemyScopeRuleRepository
from api.infrastructure.unit_of_work.adapters.base import \
    SQLAlchemyAbstractUnitOfWork
from api.infrastructure.unit_of_work.interfaces.program import \
    ProgramUnitOfWork


class SQLAlchemyProgramUnitOfWork(SQLAlchemyAbstractUnitOfWork, ProgramUnitOfWork):
    async def __aenter__(self):
        uow = await super().__aenter__()
        self.programs = SQLAlchemyProgramRepository(session=self._session)
        self.scope_rules = SQLAlchemyScopeRuleRepository(session=self._session)
        self.root_inputs = SQLAlchemyRootInputRepository(session=self._session)
        
        return uow