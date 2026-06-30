"""MapCIDR Service for CIDR operations"""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.dto.scan_dto import MapCIDRScanOutputDTO
from api.application.event_contracts import EventEnvelope, EventType
from api.application.ports.events import EventBusPort
from api.application.ports.runners import ToolRunnerFactoryPort

logger = logging.getLogger(__name__)


class MapCIDRService:
    """
    Event-driven service for MapCIDR operations.

    Supports:
    - CIDR expansion to IP lists
    - CIDR slicing by count or host count
    - IP aggregation
    - Host counting
    """

    def __init__(self, runner_factory: ToolRunnerFactoryPort, bus: EventBusPort):
        self.runner_factory = runner_factory
        self.bus = bus

    async def _collect(self, values: list[str], **options) -> list[str]:
        runner = self.runner_factory.create("mapcidr")
        results: list[str] = []
        async for event in runner.run(values, **options):
            if event.type == "result" and event.payload:
                results.append(str(event.payload))
        return results

    @staticmethod
    def _event_envelope(
        event_type: EventType,
        *,
        program_id: UUID,
        targets: list[str],
        payload: dict[str, object],
    ) -> EventEnvelope:
        return EventEnvelope(
            event=event_type.value,
            program_id=program_id,
            targets=targets,
            source="mapcidr",
            payload=payload,
        )

    async def expand(
        self,
        program_id: UUID,
        cidrs: list[str],
        skip_base: bool = False,
        skip_broadcast: bool = False,
        shuffle: bool = False
    ) -> MapCIDRScanOutputDTO:
        """
        Expand CIDR blocks to IP addresses and publish to EventBus.

        Args:
            program_id: Program UUID
            cidrs: List of CIDR blocks to expand
            skip_base: Skip base IPs (ending in .0)
            skip_broadcast: Skip broadcast IPs (ending in .255)
            shuffle: Shuffle IPs in random order

        Returns:
            MapCIDRScanOutputDTO with operation results
        """
        logger.info(
            f"Starting mapcidr expand: program={program_id} cidrs={len(cidrs)} "
            f"skip_base={skip_base} skip_broadcast={skip_broadcast} shuffle={shuffle}"
        )

        ips = await self._collect(
            cidrs,
            mode="expand",
            skip_base=skip_base,
            skip_broadcast=skip_broadcast,
            shuffle=shuffle,
        )

        if ips:
            await self.bus.publish(
                self._event_envelope(
                    EventType.IPS_EXPANDED,
                    program_id=program_id,
                    targets=ips,
                    payload={"ips": ips, "source_cidrs": cidrs},
                )
            )

        logger.info(
            f"MapCIDR expand completed: program={program_id} "
            f"input_cidrs={len(cidrs)} output_ips={len(ips)}"
        )

        return MapCIDRScanOutputDTO(
            status="completed",
            message=f"Expanded {len(cidrs)} CIDRs to {len(ips)} IPs",
            scanner="mapcidr",
            operation="expand",
            input_count=len(cidrs),
            output_count=len(ips)
        )

    async def slice_by_count(
        self,
        program_id: UUID,
        cidrs: list[str],
        count: int
    ) -> MapCIDRScanOutputDTO:
        """
        Slice CIDR blocks into smaller subnets by count.

        Args:
            program_id: Program UUID
            cidrs: List of CIDR blocks to slice
            count: Number of subnets to create

        Returns:
            MapCIDRScanOutputDTO with operation results
        """
        logger.info(
            f"Starting mapcidr slice by count: program={program_id} "
            f"cidrs={len(cidrs)} count={count}"
        )

        sliced_cidrs = await self._collect(cidrs, mode="slice_by_count", count=count)

        if sliced_cidrs:
            await self.bus.publish(
                self._event_envelope(
                    EventType.CIDR_SLICED,
                    program_id=program_id,
                    targets=sliced_cidrs,
                    payload={"cidrs": sliced_cidrs, "source_cidrs": cidrs},
                )
            )

        logger.info(
            f"MapCIDR slice by count completed: program={program_id} "
            f"input={len(cidrs)} output={len(sliced_cidrs)}"
        )

        return MapCIDRScanOutputDTO(
            status="completed",
            message=f"Sliced {len(cidrs)} CIDRs into {len(sliced_cidrs)} subnets",
            scanner="mapcidr",
            operation="slice_count",
            input_count=len(cidrs),
            output_count=len(sliced_cidrs)
        )

    async def slice_by_host_count(
        self,
        program_id: UUID,
        cidrs: list[str],
        host_count: int
    ) -> MapCIDRScanOutputDTO:
        """
        Slice CIDR blocks into subnets with specified host count.

        Args:
            program_id: Program UUID
            cidrs: List of CIDR blocks to slice
            host_count: Target number of hosts per subnet

        Returns:
            MapCIDRScanOutputDTO with operation results
        """
        logger.info(
            f"Starting mapcidr slice by host count: program={program_id} "
            f"cidrs={len(cidrs)} host_count={host_count}"
        )

        sliced_cidrs = await self._collect(
            cidrs,
            mode="slice_by_host_count",
            host_count=host_count,
        )

        if sliced_cidrs:
            await self.bus.publish(
                self._event_envelope(
                    EventType.CIDR_SLICED,
                    program_id=program_id,
                    targets=sliced_cidrs,
                    payload={"cidrs": sliced_cidrs, "source_cidrs": cidrs},
                )
            )

        logger.info(
            f"MapCIDR slice by host count completed: program={program_id} "
            f"input={len(cidrs)} output={len(sliced_cidrs)}"
        )

        return MapCIDRScanOutputDTO(
            status="completed",
            message=f"Sliced {len(cidrs)} CIDRs into {len(sliced_cidrs)} subnets with ~{host_count} hosts each",
            scanner="mapcidr",
            operation="slice_host",
            input_count=len(cidrs),
            output_count=len(sliced_cidrs)
        )

    async def aggregate(
        self,
        program_id: UUID,
        ips: list[str]
    ) -> MapCIDRScanOutputDTO:
        """
        Aggregate IPs/CIDRs into minimum subnet.

        Args:
            program_id: Program UUID
            ips: List of IPs/CIDRs to aggregate

        Returns:
            MapCIDRScanOutputDTO with operation results
        """
        logger.info(
            f"Starting mapcidr aggregate: program={program_id} ips={len(ips)}"
        )

        aggregated_cidrs = await self._collect(ips, mode="aggregate")

        if aggregated_cidrs:
            await self.bus.publish(
                self._event_envelope(
                    EventType.IPS_AGGREGATED,
                    program_id=program_id,
                    targets=aggregated_cidrs,
                    payload={"cidrs": aggregated_cidrs, "source_ips": ips},
                )
            )

        logger.info(
            f"MapCIDR aggregate completed: program={program_id} "
            f"input={len(ips)} output={len(aggregated_cidrs)}"
        )

        return MapCIDRScanOutputDTO(
            status="completed",
            message=f"Aggregated {len(ips)} IPs into {len(aggregated_cidrs)} CIDRs",
            scanner="mapcidr",
            operation="aggregate",
            input_count=len(ips),
            output_count=len(aggregated_cidrs)
        )
