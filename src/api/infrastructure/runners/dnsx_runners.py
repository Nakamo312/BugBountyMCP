"""Wrapper runners for DNSx different modes"""

from typing import AsyncIterator, List

from api.infrastructure.runners.dnsx_cli import DNSxCliRunner
from api.infrastructure.commands.command_executor import ProcessEvent


class DNSxBasicRunner:
    """Wrapper for DNSx basic mode (A/AAAA/CNAME)"""

    def __init__(self, dnsx_runner: DNSxCliRunner):
        self.dnsx_runner = dnsx_runner

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Run DNSx in basic mode"""
        async for event in self.dnsx_runner.run_basic(targets):
            yield event


class DNSxDeepRunner:
    """Wrapper for DNSx deep mode (all records)"""

    def __init__(self, dnsx_runner: DNSxCliRunner):
        self.dnsx_runner = dnsx_runner

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Run DNSx in deep mode"""
        async for event in self.dnsx_runner.run_deep(targets):
            yield event


class DNSxPtrRunner:
    """Wrapper for DNSx PTR mode (reverse DNS)"""

    def __init__(self, dnsx_runner: DNSxCliRunner):
        self.dnsx_runner = dnsx_runner

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Run DNSx in PTR mode"""
        async for event in self.dnsx_runner.run_ptr(targets):
            yield event
