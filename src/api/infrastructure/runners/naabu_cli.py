"""Naabu CLI Runner"""

import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor, ProcessEvent
from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser

logger = logging.getLogger(__name__)


class NaabuCliRunner:
    """
    Runs naabu CLI tool for port scanning.

    Naabu features:
    - Fast SYN/CONNECT probe scanning
    - Top ports scanning
    - JSON output support
    - Rate limiting
    - IPv4/IPv6 support
    """

    def __init__(self, naabu_path: str, timeout: int = 600):
        self.naabu_path = naabu_path
        self.timeout = timeout

    async def run(
        self,
        hosts: list[str] | str,
        ports: str | None = None,
        top_ports: str = "1000",
        rate: int = 1000,
        scan_mode: str = "active",
        scan_type: str = "c",
        exclude_cdn: bool = True,
        timeout: int | float | None = None,
        concurrency: int | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Default run method for pipeline compatibility.

        Args:
            hosts: Single host/IP or list of hosts/IPs to scan

        Yields:
            ProcessEvent with type="result" and payload=dict with naabu JSON output
        """
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(
            self.run_raw(
                hosts,
                ports=ports,
                top_ports=top_ports,
                rate=rate,
                scan_mode=scan_mode,
                scan_type=scan_type,
                exclude_cdn=exclude_cdn,
                timeout=timeout,
                concurrency=concurrency,
            )
        ):
            yield event

    async def run_raw(
        self,
        hosts: list[str] | str,
        ports: str | None = None,
        top_ports: str = "1000",
        rate: int = 1000,
        scan_mode: str = "active",
        scan_type: str = "c",
        exclude_cdn: bool = True,
        timeout: int | float | None = None,
        concurrency: int | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        if scan_mode == "passive":
            async for event in self.passive_scan_raw(hosts, timeout=timeout):
                yield event
            return
        if scan_mode != "active":
            raise ValueError(f"Unsupported naabu scan_mode: {scan_mode}")
        async for event in self.scan_raw(
            hosts,
            ports=ports,
            top_ports=top_ports,
            rate=rate,
            scan_type=scan_type,
            exclude_cdn=exclude_cdn,
            timeout=timeout,
            concurrency=concurrency,
        ):
            yield event

    async def scan_raw(
        self,
        hosts: list[str] | str,
        ports: str | None = None,
        top_ports: str = "1000",
        rate: int = 1000,
        scan_type: str = "c",
        exclude_cdn: bool = True,
        timeout: int | float | None = None,
        concurrency: int | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Port scan hosts with naabu.

        Args:
            hosts: Single host/IP or list of hosts/IPs to scan
            ports: Port specification (e.g., "80,443,8080-8090") or None for top-ports
            top_ports: Top ports preset - "100", "1000", "full" (default: "1000")
            rate: Packets per second (default: 1000)
            scan_type: Scan type - "s" (SYN) or "c" (CONNECT) (default: "c")
            exclude_cdn: Skip full port scans for CDN/WAF, only scan 80,443 (default: True)

        Yields:
            Raw ProcessEvent objects from CommandExecutor.

        Naabu JSON output format:
        {
            "host": "8.8.8.8",
            "ip": "8.8.8.8",
            "port": 53,
            "protocol": "tcp"
        }
        """
        if isinstance(hosts, str):
            hosts = [hosts]

        command = [
            self.naabu_path,
            "-json",
            "-silent",
            "-s", scan_type,
            "-rate", _number_arg(rate),
        ]
        if concurrency is not None:
            command.extend(["-c", str(concurrency)])

        if ports:
            command.extend(["-p", ports])
        else:
            command.extend(["-top-ports", top_ports])

        if exclude_cdn:
            command.append("-exclude-cdn")

        stdin = "\n".join(hosts)

        logger.info(
            f"Starting naabu scan: hosts={len(hosts)} ports={ports or f'top-{top_ports}'} "
            f"rate={rate} type={scan_type} exclude_cdn={exclude_cdn}"
        )

        executor = CommandExecutor(command_invocation(command, stdin=stdin, timeout=self.timeout if timeout is None else timeout))

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"naabu stderr: {event.payload}")
            yield event

        logger.info("naabu scan completed")

    async def scan(
        self,
        hosts: list[str] | str,
        ports: str | None = None,
        top_ports: str = "1000",
        rate: int = 1000,
        scan_type: str = "c",
        exclude_cdn: bool = True,
        timeout: int | float | None = None,
        concurrency: int | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(
            self.scan_raw(
                hosts,
                ports=ports,
                top_ports=top_ports,
                rate=rate,
                scan_type=scan_type,
                exclude_cdn=exclude_cdn,
                timeout=timeout,
                concurrency=concurrency,
            )
        ):
            yield event

    async def passive_scan_raw(
        self,
        hosts: list[str] | str,
        timeout: int | float | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Passive port enumeration using Shodan InternetDB API.

        Args:
            hosts: Single host/IP or list of hosts/IPs

        Yields:
            ProcessEvent with passive port discovery results
        """
        if isinstance(hosts, str):
            hosts = [hosts]

        command = [
            self.naabu_path,
            "-json",
            "-silent",
            "-passive",
        ]

        stdin = "\n".join(hosts)

        logger.info(f"Starting naabu passive scan: hosts={len(hosts)}")

        executor = CommandExecutor(command_invocation(command, stdin=stdin, timeout=self.timeout if timeout is None else timeout))

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"naabu stderr: {event.payload}")
            yield event

        logger.info("naabu passive scan completed")

    async def passive_scan(
        self,
        hosts: list[str] | str
    ) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.passive_scan_raw(hosts)):
            yield event


def _number_arg(value: int | float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)
