import logging
from typing import AsyncIterator, List
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class MantraCliRunner:
    def __init__(self, mantra_path: str = "mantra", timeout: int = 300):
        self.mantra_path = mantra_path
        self.timeout = timeout

    async def run(self, js_urls: List[str]) -> AsyncIterator[ProcessEvent]:
        """
        Run Mantra on batch of JS URLs via stdin.

        Args:
            js_urls: List of JS file URLs

        Yields:
            ProcessEvent with stdout lines from mantra
        """
        if not js_urls:
            return

        stdin_data = "\n".join(js_urls)

        command = [
            self.mantra_path,
            "-s",  # Silent mode (no banner)
        ]

        logger.info(f"Running Mantra on {len(js_urls)} JS files")

        executor = CommandExecutor(
            command=command,
            stdin=stdin_data,
            timeout=self.timeout
        )

        try:
            async for event in executor.run():
                if event.type == "stdout" and event.payload:
                    yield event
        except Exception as e:
            logger.error(f"Mantra execution error: {e}")
