# api/infrastructure/unit_of_work/adapters/base.py
from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction, async_sessionmaker

from api.infrastructure.unit_of_work.interfaces.base import AbstractUnitOfWork

_SAFE_SAVEPOINT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _validate_savepoint_name(name: str) -> str:
    if not _SAFE_SAVEPOINT_NAME_RE.fullmatch(name):
        raise ValueError(
            "Savepoint name must be a safe identifier: start with a letter or '_' "
            "and contain only letters, digits, and '_'"
        )
    return name


class SQLAlchemyAbstractUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory
        self._session: AsyncSession | None = None
        self._savepoints: list[str] = []
        self._savepoint_transactions: dict[str, AsyncSessionTransaction] = {}

    async def __aenter__(self):
        self._session = self.session_factory()
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await super().__aexit__(exc_type, exc_val, exc_tb)
        if self._session:
            await self._session.close()

    async def commit(self):
        if self._session:
            await self._session.commit()

    async def rollback(self):
        """Full rollback"""
        if self._session:
            await self._session.rollback()
            self._savepoints.clear()
            self._savepoint_transactions.clear()

    async def create_savepoint(self, name: str):
        if not self._session:
            raise RuntimeError("Session not initialized")
        savepoint_name = _validate_savepoint_name(name)
        if savepoint_name in self._savepoint_transactions:
            raise ValueError(f"Savepoint {savepoint_name} already exists")

        transaction = self._session.begin_nested()
        await transaction.start()
        self._savepoints.append(savepoint_name)
        self._savepoint_transactions[savepoint_name] = transaction

    async def rollback_to_savepoint(self, name: str):
        if not self._session:
            return
        savepoint_name = _validate_savepoint_name(name)
        if savepoint_name not in self._savepoint_transactions:
            raise ValueError(f"Savepoint {savepoint_name} does not exist")

        idx = self._savepoints.index(savepoint_name)
        for rollback_name in reversed(self._savepoints[idx:]):
            transaction = self._savepoint_transactions.pop(rollback_name)
            await transaction.rollback()
        self._savepoints = self._savepoints[:idx]

    async def release_savepoint(self, name: str):
        if not self._session:
            return
        savepoint_name = _validate_savepoint_name(name)
        if savepoint_name not in self._savepoint_transactions:
            raise ValueError(f"Savepoint {savepoint_name} does not exist")

        idx = self._savepoints.index(savepoint_name)
        for release_name in reversed(self._savepoints[idx:]):
            transaction = self._savepoint_transactions.pop(release_name)
            await transaction.commit()
        self._savepoints = self._savepoints[:idx]
