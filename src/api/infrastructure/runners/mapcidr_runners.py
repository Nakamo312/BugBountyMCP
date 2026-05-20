"""Wrapper runners for MapCIDR different operations"""

from typing import AsyncIterator, List

from api.infrastructure.runners.mapcidr_cli import MapCIDRCliRunner
from api.infrastructure.parsers.line_process_event_parsers import StdoutLineResultParser
from api.infrastructure.commands.command_executor import ProcessEvent


class MapCIDRExpandRunner:
    """Wrapper for MapCIDR expand operation"""

    def __init__(self, mapcidr_runner: MapCIDRCliRunner):
        self.mapcidr_runner = mapcidr_runner

    async def run_raw(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Expand CIDRs to IPs and yield raw process events."""
        async for event in self.mapcidr_runner.expand_raw(targets):
            yield event

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Expand CIDRs to IPs"""
        parser = StdoutLineResultParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event


class MapCIDRAggregateRunner:
    """Wrapper for MapCIDR aggregate operation"""

    def __init__(self, mapcidr_runner: MapCIDRCliRunner):
        self.mapcidr_runner = mapcidr_runner

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Aggregate IPs to CIDRs"""
        async for event in self.mapcidr_runner.aggregate(targets):
            yield event
