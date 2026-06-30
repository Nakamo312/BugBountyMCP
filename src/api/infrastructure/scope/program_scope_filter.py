"""Program-backed pipeline scope filtering adapter."""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.pipeline.scope_policy import ScopePolicy
from api.application.ports.scope import ScopeFilterPort
from api.application.utils.scope_checker import ScopeChecker
from api.infrastructure.unit_of_work.adapters.program import SQLAlchemyProgramUnitOfWork

logger = logging.getLogger(__name__)


class ProgramScopeFilter(ScopeFilterPort):
    """Filter targets using persisted program scope rules."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def filter_by_scope(
        self,
        *,
        program_id: UUID,
        targets: list[str],
        policy: ScopePolicy,
    ) -> tuple[list[str], list[str]]:
        program_uow = SQLAlchemyProgramUnitOfWork(self.session_factory)
        async with program_uow:
            scope_rules = await program_uow.scope_rules.find_by_program(program_id)

        if not scope_rules:
            if policy == ScopePolicy.NONE:
                logger.warning(
                    "No scope rules for program=%s, all targets pass through",
                    program_id,
                )
                return targets, []

            logger.warning(
                "No scope rules for program=%s, blocking targets for policy=%s",
                program_id,
                policy.value,
            )
            return [], targets

        return ScopeChecker.filter_in_scope(targets, scope_rules)
