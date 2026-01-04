"""Subjack CLI runner for subdomain takeover detection"""
import json
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class SubjackCliRunner:
    """
    Runner for Subjack CLI tool.
    Detects subdomain takeovers by analyzing CNAME records.
    """

    def __init__(self, subjack_path: str, fingerprints_path: str, timeout: int = 300):
        self.subjack_path = subjack_path
        self.fingerprints_path = fingerprints_path
        self.timeout = timeout

    async def run(self, targets: list[str] | str, output_json: bool = True) -> AsyncIterator[ProcessEvent]:
        """
        Execute subjack to detect subdomain takeovers.

        Args:
            targets: Single domain or list of domains to check
            output_json: Return results in JSON format (default: True)

        Yields:
            ProcessEvent with type="result" and payload=vulnerability_data
        """
        if isinstance(targets, str):
            targets = [targets]

        stdin_input = "\n".join(targets)
        output_file = "-" if not output_json else "/dev/stdout"

        if output_json:
            output_file = "-"

        command = [
            self.subjack_path,
            "-w", "-",
            "-t", "100",
            "-timeout", "30",
            "-ssl",
            "-a",
            "-c", self.fingerprints_path,
        ]

        if output_json:
            command.extend(["-o", "results.json"])
        else:
            command.extend(["-o", "-"])

        logger.info("Starting Subjack: targets=%d json=%s", len(targets), output_json)

        executor = CommandExecutor(command, stdin=stdin_input, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.debug("Subjack stderr: %s", event.payload)

            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            line = event.payload.strip()
            if not line:
                continue

            if output_json:
                try:
                    data = json.loads(line)
                    result_count += 1
                    yield ProcessEvent(type="result", payload=data)
                except json.JSONDecodeError:
                    logger.debug("Non-JSON line skipped: %r", line[:200])
            else:
                if line.startswith("["):
                    continue

                parts = line.split()
                if len(parts) < 2 or "[" not in line:
                    continue

                try:
                    subdomain = parts[0]
                    service = line[line.find("[")+1:line.find("]")]
                    vulnerable = "Takeover Possible" in line or "possible takeover" in line.lower()

                    if vulnerable:
                        result_count += 1
                        yield ProcessEvent(
                            type="result",
                            payload={
                                "subdomain": subdomain,
                                "service": service,
                                "vulnerable": vulnerable,
                                "cname": parts[1] if len(parts) > 1 else None
                            }
                        )
                except (IndexError, ValueError) as e:
                    logger.debug("Failed to parse Subjack line: %r - %s", line, e)

        logger.info("Subjack completed: vulnerabilities=%d", result_count)
