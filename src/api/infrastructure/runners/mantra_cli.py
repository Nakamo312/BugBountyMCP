import logging
from typing import AsyncIterator, List
from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.line_process_event_parsers import MantraStdoutParser
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class MantraCliRunner:
    def __init__(self, mantra_path: str = "mantra", timeout: int = 300):
        self.mantra_path = mantra_path
        self.timeout = timeout

    async def run_raw(self, js_urls: List[str]) -> AsyncIterator[ProcessEvent]:
        """
        Run Mantra on batch of JS URLs via stdin.

        Args:
            js_urls: List of JS file URLs

        Yields:
            ProcessEvent with type="result" and payload={"url": str, "secret": str}
        """
        if not js_urls:
            return

        stdin_data = "\n".join(js_urls)

        command = [
            self.mantra_path,
            "-s",
        ]

        logger.info(f"Running Mantra on {len(js_urls)} JS files")

        executor = CommandExecutor(
            command_invocation(command, stdin=stdin_data, timeout=self.timeout)
        )

        try:
            async for event in executor.run():
                yield event
        except Exception as e:
            logger.error(f"Mantra execution error: {e}")

    async def run(self, js_urls: List[str]) -> AsyncIterator[ProcessEvent]:
        parser = MantraStdoutParser()
        async for event in parser.parse_stream(self.run_raw(js_urls)):
            yield event
