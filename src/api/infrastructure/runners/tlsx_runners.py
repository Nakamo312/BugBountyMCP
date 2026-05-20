"""Wrapper runners for TLSx different modes"""

from typing import AsyncIterator, List

from api.infrastructure.runners.tlsx_cli import TLSxCliRunner
from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser
from api.infrastructure.commands.command_executor import ProcessEvent


class TLSxDefaultRunner:
    """Wrapper for TLSx default certificate scanning mode"""

    def __init__(self, tlsx_runner: TLSxCliRunner):
        self.tlsx_runner = tlsx_runner

    async def run_raw(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Run TLSx in default certificate scanning mode and yield raw events."""
        async for event in self.tlsx_runner.scan_default_certs_raw(targets):
            yield event

    async def run(self, targets: List[str]) -> AsyncIterator[ProcessEvent]:
        """Run TLSx in default certificate scanning mode"""
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event
