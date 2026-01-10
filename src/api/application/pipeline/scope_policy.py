"""Scope filtering policy - separates scope logic from pipeline nodes"""

from typing import List, Tuple
from uuid import UUID
import logging

from dishka import AsyncContainer
from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork
from api.application.services.base_service import ScopeCheckMixin


logger = logging.getLogger(__name__)


class ScopePolicy:
    """
    Centralized scope filtering policy.

    Architectural principle:
    - Scope applies ONLY to domains (DNS Track)
    - Scope does NOT apply to IPs (ASN Track independence)
    - Nodes delegate scope decisions here instead of implementing themselves
    """

    def __init__(self, container: AsyncContainer):
        self.container = container

    async def filter_domains(
        self, program_id: UUID, domains: List[str]
    ) -> Tuple[List[str], List[str]]:
        """
        Filter domains by program scope rules.

        Args:
            program_id: Program UUID
            domains: List of domains to filter

        Returns:
            Tuple of (in_scope_domains, out_of_scope_domains)
        """
        async with self.container() as request_container:
            program_uow = await request_container.get(ProgramUnitOfWork)
            async with program_uow:
                scope_rules = await program_uow.scope_rules.find_by_program(program_id)
                in_scope, out_scope = ScopeCheckMixin.filter_in_scope(domains, scope_rules)

                if out_scope:
                    logger.debug(
                        f"Filtered domains: program={program_id} "
                        f"in_scope={len(in_scope)} out_of_scope={len(out_scope)}"
                    )

                return in_scope, out_scope

    async def filter_urls(
        self, program_id: UUID, urls: List[str]
    ) -> Tuple[List[str], List[str]]:
        """
        Filter URLs by program scope rules.

        Args:
            program_id: Program UUID
            urls: List of URLs to filter

        Returns:
            Tuple of (in_scope_urls, out_of_scope_urls)
        """
        async with self.container() as request_container:
            program_uow = await request_container.get(ProgramUnitOfWork)
            async with program_uow:
                scope_rules = await program_uow.scope_rules.find_by_program(program_id)
                in_scope, out_scope = ScopeCheckMixin.filter_in_scope(urls, scope_rules)

                if out_scope:
                    logger.debug(
                        f"Filtered URLs: program={program_id} "
                        f"in_scope={len(in_scope)} out_of_scope={len(out_scope)}"
                    )

                return in_scope, out_scope

    async def check_domain_in_scope(self, program_id: UUID, domain: str) -> bool:
        """
        Check if a single domain is in scope.

        Args:
            program_id: Program UUID
            domain: Domain to check

        Returns:
            True if domain is in scope, False otherwise
        """
        in_scope, _ = await self.filter_domains(program_id, [domain])
        return len(in_scope) > 0
