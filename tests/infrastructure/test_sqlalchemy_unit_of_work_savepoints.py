from __future__ import annotations

import pytest

from api.infrastructure.unit_of_work.adapters.base import SQLAlchemyAbstractUnitOfWork


class FakeTransaction:
    def __init__(self, events: list[str], index: int) -> None:
        self.events = events
        self.index = index

    async def start(self) -> None:
        self.events.append(f"start:{self.index}")

    async def rollback(self) -> None:
        self.events.append(f"rollback:{self.index}")

    async def commit(self) -> None:
        self.events.append(f"commit:{self.index}")


class FakeSession:
    def __init__(self) -> None:
        self.events: list[str] = []
        self._next_index = 0

    def begin_nested(self) -> FakeTransaction:
        self._next_index += 1
        return FakeTransaction(self.events, self._next_index)

    async def commit(self) -> None:
        self.events.append("session:commit")

    async def rollback(self) -> None:
        self.events.append("session:rollback")

    async def close(self) -> None:
        self.events.append("session:close")


class FakeSessionFactory:
    def __init__(self) -> None:
        self.session = FakeSession()

    def __call__(self) -> FakeSession:
        return self.session


@pytest.mark.asyncio
async def test_unit_of_work_savepoints_use_sqlalchemy_nested_transactions() -> None:
    factory = FakeSessionFactory()
    async with SQLAlchemyAbstractUnitOfWork(factory) as uow:
        await uow.create_savepoint("batch_0")
        await uow.release_savepoint("batch_0")

    assert factory.session.events == ["start:1", "commit:1", "session:close"]


@pytest.mark.asyncio
async def test_unit_of_work_rollback_to_savepoint_rolls_back_nested_stack() -> None:
    factory = FakeSessionFactory()
    async with SQLAlchemyAbstractUnitOfWork(factory) as uow:
        await uow.create_savepoint("batch_0")
        await uow.create_savepoint("batch_1")
        await uow.rollback_to_savepoint("batch_0")

    assert factory.session.events == [
        "start:1",
        "start:2",
        "rollback:2",
        "rollback:1",
        "session:close",
    ]


@pytest.mark.asyncio
async def test_unit_of_work_rejects_unsafe_savepoint_names() -> None:
    factory = FakeSessionFactory()
    async with SQLAlchemyAbstractUnitOfWork(factory) as uow:
        with pytest.raises(ValueError, match="safe identifier"):
            await uow.create_savepoint("batch_0; DROP TABLE programs")


@pytest.mark.asyncio
async def test_unit_of_work_rejects_duplicate_savepoint_names() -> None:
    factory = FakeSessionFactory()
    async with SQLAlchemyAbstractUnitOfWork(factory) as uow:
        await uow.create_savepoint("batch_0")
        with pytest.raises(ValueError, match="already exists"):
            await uow.create_savepoint("batch_0")
