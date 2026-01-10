"""MapCIDR Service for CIDR operations"""

import logging
from typing import AsyncIterator
from uuid import UUID

from api.infrastructure.runners.mapcidr_cli import MapCIDRCliRunner

logger = logging.getLogger(__name__)


class MapCIDRService:
    """
    Service for MapCIDR operations.
    Streams results for pipeline node processing.

    Supports:
    - CIDR expansion to IP lists
    - CIDR slicing by count or host count
    - IP aggregation
    - Host counting
    """

    def __init__(self, runner: MapCIDRCliRunner):
        self.runner = runner

    async def expand(
        self,
        program_id: UUID,
        cidrs: list[str],
        skip_base: bool = False,
        skip_broadcast: bool = False,
        shuffle: bool = False
    ) -> AsyncIterator[str]:
        """
        Expand CIDR blocks to IP addresses.

        Args:
            program_id: Program UUID
            cidrs: List of CIDR blocks to expand
            skip_base: Skip base IPs (ending in .0)
            skip_broadcast: Skip broadcast IPs (ending in .255)
            shuffle: Shuffle IPs in random order

        Yields:
            Individual IP addresses
        """
        logger.info(
            f"Starting mapcidr expand: program={program_id} cidrs={len(cidrs)} "
            f"skip_base={skip_base} skip_broadcast={skip_broadcast} shuffle={shuffle}"
        )

        ips_yielded = 0

        async for event in self.runner.expand(
            cidrs=cidrs,
            skip_base=skip_base,
            skip_broadcast=skip_broadcast,
            shuffle=shuffle
        ):
            if event.type == "result":
                ips_yielded += 1
                yield event.payload

        logger.info(
            f"MapCIDR expand completed: program={program_id} "
            f"input_cidrs={len(cidrs)} output_ips={ips_yielded}"
        )

    async def slice_by_count(
        self,
        program_id: UUID,
        cidrs: list[str],
        count: int
    ) -> AsyncIterator[str]:
        """
        Slice CIDR blocks into smaller subnets by count.

        Args:
            program_id: Program UUID
            cidrs: List of CIDR blocks to slice
            count: Number of subnets to create

        Yields:
            Individual CIDR blocks
        """
        logger.info(
            f"Starting mapcidr slice by count: program={program_id} "
            f"cidrs={len(cidrs)} count={count}"
        )

        cidrs_yielded = 0

        async for event in self.runner.slice_by_count(cidrs=cidrs, count=count):
            if event.type == "result":
                cidrs_yielded += 1
                yield event.payload

        logger.info(
            f"MapCIDR slice by count completed: program={program_id} "
            f"input={len(cidrs)} output={cidrs_yielded}"
        )

    async def slice_by_host_count(
        self,
        program_id: UUID,
        cidrs: list[str],
        host_count: int
    ) -> AsyncIterator[str]:
        """
        Slice CIDR blocks into subnets with specified host count.

        Args:
            program_id: Program UUID
            cidrs: List of CIDR blocks to slice
            host_count: Target number of hosts per subnet

        Yields:
            Individual CIDR blocks
        """
        logger.info(
            f"Starting mapcidr slice by host count: program={program_id} "
            f"cidrs={len(cidrs)} host_count={host_count}"
        )

        cidrs_yielded = 0

        async for event in self.runner.slice_by_host_count(cidrs=cidrs, host_count=host_count):
            if event.type == "result":
                cidrs_yielded += 1
                yield event.payload

        logger.info(
            f"MapCIDR slice by host count completed: program={program_id} "
            f"input={len(cidrs)} output={cidrs_yielded}"
        )

    async def aggregate(
        self,
        program_id: UUID,
        ips: list[str]
    ) -> AsyncIterator[str]:
        """
        Aggregate IPs/CIDRs into minimum subnet.

        Args:
            program_id: Program UUID
            ips: List of IPs/CIDRs to aggregate

        Yields:
            Individual aggregated CIDR blocks
        """
        logger.info(
            f"Starting mapcidr aggregate: program={program_id} ips={len(ips)}"
        )

        cidrs_yielded = 0

        async for event in self.runner.aggregate(ips=ips):
            if event.type == "result":
                cidrs_yielded += 1
                yield event.payload

        logger.info(
            f"MapCIDR aggregate completed: program={program_id} "
            f"input={len(ips)} output={cidrs_yielded}"
        )
