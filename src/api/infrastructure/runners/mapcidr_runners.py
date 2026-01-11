"""Wrapper runners for MapCIDR different operations"""

from typing import AsyncIterator, List

from api.infrastructure.runners.mapcidr_cli import MapCIDRCliRunner
from api.infrastructure.commands.command_executor import ProcessEvent


class MapCIDRExpandRunner:
    """Wrapper for MapCIDR expand operation"""

    def __init__(self, mapcidr_runner: MapCIDRCliRunner):
        self.mapcidr_runner = mapcidr_runner

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Expand CIDRs to IPs"""
        async for event in self.mapcidr_runner.expand(targets):
            yield event


class MapCIDRAggregateRunner:
    """Wrapper for MapCIDR aggregate operation"""

    def __init__(self, mapcidr_runner: MapCIDRCliRunner):
        self.mapcidr_runner = mapcidr_runner

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Aggregate IPs to CIDRs"""
        async for event in self.mapcidr_runner.aggregate(targets):
            yield event
