"""Wrapper runners for DNSx different modes"""

from typing import AsyncIterator, List

from api.infrastructure.runners.dnsx_cli import DNSxCliRunner
from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser
from api.infrastructure.commands.command_executor import ProcessEvent


class DNSxDeepRunner:
    """Wrapper for DNSx deep mode (all records)"""

    def __init__(self, dnsx_runner: DNSxCliRunner):
        self.dnsx_runner = dnsx_runner

    async def run_raw(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Run DNSx in deep mode and yield raw process events."""
        async for event in self.dnsx_runner.run_deep_raw(targets):
            yield event

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Run DNSx in deep mode"""
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event


class DNSxPtrRunner:
    """Wrapper for DNSx PTR mode (reverse DNS)"""

    def __init__(self, dnsx_runner: DNSxCliRunner):
        self.dnsx_runner = dnsx_runner

    async def run_raw(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Run DNSx in PTR mode and yield raw process events."""
        async for event in self.dnsx_runner.run_ptr_raw(targets):
            yield event

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Run DNSx in PTR mode"""
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event
