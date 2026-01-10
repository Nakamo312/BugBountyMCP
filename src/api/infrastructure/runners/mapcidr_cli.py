"""MapCIDR CLI Runner"""

import json
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor, ProcessEvent

logger = logging.getLogger(__name__)


class MapCIDRCliRunner:
    """
    Runs mapcidr CLI tool for CIDR operations.

    mapcidr supports:
    - CIDR expansion to IP lists
    - CIDR slicing by count or host count
    - IP aggregation
    - IP filtering and matching
    """

    def __init__(self, mapcidr_path: str, timeout: int = 300):
        self.mapcidr_path = mapcidr_path
        self.timeout = timeout

    async def expand(
        self,
        cidrs: list[str] | str,
        skip_base: bool = False,
        skip_broadcast: bool = False,
        shuffle: bool = False
    ) -> AsyncIterator[ProcessEvent]:
        """
        Expand CIDR blocks to IP addresses.

        Args:
            cidrs: Single CIDR or list of CIDRs to expand
            skip_base: Skip base IPs (ending in .0)
            skip_broadcast: Skip broadcast IPs (ending in .255)
            shuffle: Shuffle IPs in random order

        Yields:
            ProcessEvent with type="result" and payload=IP address string
        """
        if isinstance(cidrs, str):
            cidrs = [cidrs]

        command = [self.mapcidr_path, "-silent"]

        if skip_base:
            command.append("-skip-base")
        if skip_broadcast:
            command.append("-skip-broadcast")
        if shuffle:
            command.append("-si")

        stdin = "\n".join(cidrs)

        logger.info(
            f"Starting mapcidr expand: cidrs={len(cidrs)} "
            f"skip_base={skip_base} skip_broadcast={skip_broadcast} shuffle={shuffle} "
            f"input={cidrs}"
        )

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"mapcidr stderr: {event.payload}")
            if event.type != "stdout" or not event.payload:
                continue

            ip = event.payload.strip()
            if ip:
                result_count += 1
                yield ProcessEvent(type="result", payload=ip)

        logger.info(f"mapcidr expand completed: ips={result_count}")

    async def slice_by_count(
        self,
        cidrs: list[str] | str,
        count: int
    ) -> AsyncIterator[ProcessEvent]:
        """
        Slice CIDR blocks into smaller subnets by count.

        Args:
            cidrs: Single CIDR or list of CIDRs to slice
            count: Number of subnets to create

        Yields:
            ProcessEvent with type="result" and payload=CIDR string
        """
        if isinstance(cidrs, str):
            cidrs = [cidrs]

        command = [
            self.mapcidr_path,
            "-silent",
            "-sbc", str(count)
        ]

        stdin = "\n".join(cidrs)

        logger.info(f"Starting mapcidr slice by count: cidrs={len(cidrs)} count={count}")

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"mapcidr stderr: {event.payload}")
            if event.type != "stdout" or not event.payload:
                continue

            cidr = event.payload.strip()
            if cidr:
                result_count += 1
                yield ProcessEvent(type="result", payload=cidr)

        logger.info(f"mapcidr slice by count completed: subnets={result_count}")

    async def slice_by_host_count(
        self,
        cidrs: list[str] | str,
        host_count: int
    ) -> AsyncIterator[ProcessEvent]:
        """
        Slice CIDR blocks into subnets with specified host count.

        Args:
            cidrs: Single CIDR or list of CIDRs to slice
            host_count: Target number of hosts per subnet

        Yields:
            ProcessEvent with type="result" and payload=CIDR string
        """
        if isinstance(cidrs, str):
            cidrs = [cidrs]

        command = [
            self.mapcidr_path,
            "-silent",
            "-sbh", str(host_count)
        ]

        stdin = "\n".join(cidrs)

        logger.info(f"Starting mapcidr slice by host count: cidrs={len(cidrs)} host_count={host_count}")

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"mapcidr stderr: {event.payload}")
            if event.type != "stdout" or not event.payload:
                continue

            cidr = event.payload.strip()
            if cidr:
                result_count += 1
                yield ProcessEvent(type="result", payload=cidr)

        logger.info(f"mapcidr slice by host count completed: subnets={result_count}")

    async def count_hosts(self, cidrs: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Count number of hosts in CIDR blocks.

        Args:
            cidrs: Single CIDR or list of CIDRs

        Yields:
            ProcessEvent with type="result" and payload=count (int)
        """
        if isinstance(cidrs, str):
            cidrs = [cidrs]

        command = [
            self.mapcidr_path,
            "-silent",
            "-count"
        ]

        stdin = "\n".join(cidrs)

        logger.info(f"Starting mapcidr count: cidrs={len(cidrs)}")

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"mapcidr stderr: {event.payload}")
            if event.type != "stdout" or not event.payload:
                continue

            try:
                count = int(event.payload.strip())
                yield ProcessEvent(type="result", payload=count)
            except ValueError:
                logger.debug(f"Non-numeric count output: {event.payload}")
                continue

        logger.info("mapcidr count completed")

    async def aggregate(self, ips: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Aggregate IPs/CIDRs into minimum subnet.

        Args:
            ips: Single IP/CIDR or list of IPs/CIDRs

        Yields:
            ProcessEvent with type="result" and payload=CIDR string
        """
        if isinstance(ips, str):
            ips = [ips]

        command = [
            self.mapcidr_path,
            "-silent",
            "-aggregate"
        ]

        stdin = "\n".join(ips)

        logger.info(f"Starting mapcidr aggregate: ips={len(ips)}")

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"mapcidr stderr: {event.payload}")
            if event.type != "stdout" or not event.payload:
                continue

            cidr = event.payload.strip()
            if cidr:
                result_count += 1
                yield ProcessEvent(type="result", payload=cidr)

        logger.info(f"mapcidr aggregate completed: cidrs={result_count}")
