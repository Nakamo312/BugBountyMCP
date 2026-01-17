import logging
import re
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
            command=command,
            stdin=stdin_data,
            timeout=self.timeout
        )

        try:
            async for event in executor.run():
                if event.type == "stdout" and event.payload:
                    parsed = self._parse_mantra_output(event.payload)
                    if parsed:
                        yield ProcessEvent(type="result", payload=parsed)
        except Exception as e:
            logger.error(f"Mantra execution error: {e}")

    def _parse_mantra_output(self, line: str) -> dict | None:
        """
        Parse Mantra output line.

        Format: [+] https://example.com/app.js [secret_value]

        Returns:
            Dict with url and secret, or None if not a valid secret line
        """
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
        clean_line = ansi_escape.sub('', line).strip()

        match = re.match(r'^\[\+\]\s+(https?://[^\s]+)\s+\[(.+)\]$', clean_line)
        if match:
            return {
                "url": match.group(1),
                "secret": match.group(2),
            }
        return None
