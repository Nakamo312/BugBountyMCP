from abc import ABC
from api.infrastructure.repositories.interfaces.repository import AbstractRepository
from sqlalchemy.ext.asyncio import AsyncSession

class SQLAlchemyAbstractRepository(AbstractRepository, ABC):
    """
    Repository interface for SQLAlchemy, from which should be inherited all other repositories,
    which would be based on SQLAlchemy logics.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session: AsyncSession = session