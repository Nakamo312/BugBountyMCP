import logging
import re
from typing import List, Dict, Any, AsyncIterator
from uuid import UUID

from api.infrastructure.runners.mantra_cli import MantraCliRunner

logger = logging.getLogger(__name__)


class MantraScanService:
    """
    Service for Mantra secret scanning.
    Analyzes JavaScript files for leaked secrets and credentials.
    """

    def __init__(self, runner: MantraCliRunner):
        self.runner = runner

    async def execute(self, program_id: UUID, targets: List[str]) -> AsyncIterator[List[Dict[str, Any]]]:
        """
        Execute Mantra scan on JS files.

        Args:
            program_id: Target program ID
            targets: List of JS URLs to scan

        Yields:
            Lists of discovered secrets
        """
        logger.info(f"Starting Mantra scan: program={program_id} targets={len(targets)}")

        results = []

        async for event in self.runner.run(targets):
            if event.type == "stdout" and event.payload:
                parsed = self._parse_mantra_output(event.payload)
                if parsed:
                    results.append(parsed)

        if results:
            logger.info(
                f"Mantra scan completed: program={program_id} targets={len(targets)} "
                f"secrets_found={len(results)}"
            )
            yield results
        else:
            logger.info(
                f"Mantra scan completed: program={program_id} targets={len(targets)} "
                f"secrets_found=0"
            )

    def _parse_mantra_output(self, line: str) -> Dict[str, Any] | None:
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
