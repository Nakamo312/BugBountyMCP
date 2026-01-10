from uuid import UUID
import asyncio
from fastapi import APIRouter, HTTPException
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from api.presentation.schemas import *
from api.application.services.subfinder import SubfinderScanService
from api.application.services.httpx import HTTPXScanService
from api.application.services.gau import GAUScanService
from api.application.services.katana import KatanaScanService
from api.application.services.linkfinder import LinkFinderScanService
from api.application.services.mantra import MantraScanService
from api.application.services.ffuf import FFUFScanService
from api.application.services.dnsx import DNSxScanService
from api.application.services.subjack import SubjackScanService
from api.application.services.asnmap import ASNMapScanService
from api.application.services.mapcidr import MapCIDRService
from api.application.services.naabu import NaabuScanService


router = APIRouter(route_class=DishkaRoute)


@router.post("/scan/subfinder", response_model=ScanResponse, tags=["Scans"])
async def scan_subfinder(
    request: SubfinderScanRequest,
    service: FromDishka[SubfinderScanService],
):
    async def run():
        await service.execute(
            program_id=UUID(request.program_id),
            domain=request.domain
        )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="Subfinder scan started", results=[])


@router.post("/scan/httpx", response_model=ScanResponse, tags=["Scans"])
async def scan_httpx(
    request: HTTPXScanRequest,
    service: FromDishka[HTTPXScanService],
):
    targets = request.targets if isinstance(request.targets, list) else [request.targets]

    async def run():
        await service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="HTTPX scan started", results=[])


@router.post("/scan/gau", response_model=ScanResponse, tags=["Scans"])
async def scan_gau(
    request: GAUScanRequest,
    service: FromDishka[GAUScanService],
):
    async def run():
        await service.execute(
            program_id=UUID(request.program_id),
            domain=request.domain,
            include_subs=request.include_subs
        )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="GAU scan started", results=[])


@router.post("/scan/katana", response_model=ScanResponse, tags=["Scans"])
async def scan_katana(
    request: KatanaScanRequest,
    service: FromDishka[KatanaScanService],
):
    targets = request.targets if isinstance(request.targets, list) else [request.targets]

    async def run():
        await service.execute(
            program_id=UUID(request.program_id),
            targets=targets,
            depth=request.depth,
            js_crawl=request.js_crawl,
            headless=request.headless
        )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="Katana scan started", results=[])


@router.post("/scan/linkfinder", response_model=ScanResponse, tags=["Scans"])
async def scan_linkfinder(
    request: LinkFinderScanRequest,
    service: FromDishka[LinkFinderScanService],
):
    targets = request.targets if isinstance(request.targets, list) else [request.targets]

    async def run():
        await service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="LinkFinder scan started", results=[])


@router.post("/scan/mantra", response_model=ScanResponse, tags=["Scans"])
async def scan_mantra(
    request: MantraScanRequest,
    service: FromDishka[MantraScanService],
):
    targets = request.targets if isinstance(request.targets, list) else [request.targets]

    async def run():
        await service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="Mantra scan started", results=[])


@router.post("/scan/ffuf", response_model=ScanResponse, tags=["Scans"])
async def scan_ffuf(
    request: FFUFScanRequest,
    service: FromDishka[FFUFScanService],
):
    targets = request.targets if isinstance(request.targets, list) else [request.targets]

    async def run():
        await service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="FFUF scan started", results=[])


@router.post("/scan/dnsx", response_model=ScanResponse, tags=["Scans"])
async def scan_dnsx(
    request: DNSxScanRequest,
    service: FromDishka[DNSxScanService],
):
    targets = request.targets if isinstance(request.targets, list) else [request.targets]

    async def run():
        await service.execute(
            program_id=UUID(request.program_id),
            targets=targets,
            mode=request.mode
        )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="DNSx scan started", results=[])


@router.post("/scan/subjack", response_model=ScanResponse, tags=["Scans"])
async def scan_subjack(
    request: SubjackScanRequest,
    service: FromDishka[SubjackScanService],
):
    targets = request.targets if isinstance(request.targets, list) else [request.targets]

    async def run():
        await service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="Subjack scan started", results=[])


@router.post("/scan/asnmap", response_model=ScanResponse, tags=["Scans"])
async def scan_asnmap(
    request: ASNMapScanRequest,
    service: FromDishka[ASNMapScanService],
):
    targets = request.targets if isinstance(request.targets, list) else [request.targets]

    async def run():
        async for _ in service.execute(
            program_id=UUID(request.program_id),
            targets=targets,
            mode=request.mode
        ):
            pass

    asyncio.create_task(run())
    return ScanResponse(status="success", message="ASNMap scan started", results=[])


@router.post("/scan/mapcidr", response_model=ScanResponse, tags=["Scans"])
async def scan_mapcidr(
    request: MapCIDRScanRequest,
    service: FromDishka[MapCIDRService],
):
    program_id = UUID(request.program_id)
    cidrs = request.cidrs if isinstance(request.cidrs, list) else [request.cidrs]

    async def run():
        if request.operation == "expand":
            await service.expand(program_id, cidrs, request.skip_base, request.skip_broadcast, request.shuffle)
        elif request.operation == "slice_count":
            await service.slice_by_count(program_id, cidrs, request.count)
        elif request.operation == "slice_host":
            await service.slice_by_host_count(program_id, cidrs, request.host_count)
        elif request.operation == "aggregate":
            await service.aggregate(program_id, cidrs)

    asyncio.create_task(run())
    return ScanResponse(status="success", message="MapCIDR operation started", results=[])


@router.post("/scan/naabu", response_model=ScanResponse, tags=["Scans"])
async def scan_naabu(
    request: NaabuScanRequest,
    service: FromDishka[NaabuScanService],
):
    program_id = UUID(request.program_id)
    targets = request.targets if isinstance(request.targets, list) else [request.targets]

    async def run():
        if request.scan_mode == "active":
            await service.execute(
                program_id,
                targets,
                request.ports,
                request.top_ports,
                request.rate,
                request.scan_type,
                request.exclude_cdn
            )
        elif request.scan_mode == "passive":
            await service.execute_passive(program_id, targets)
        elif request.scan_mode == "nmap":
            await service.execute_with_nmap(
                program_id,
                targets,
                request.nmap_cli,
                request.top_ports,
                request.rate
            )

    asyncio.create_task(run())
    return ScanResponse(status="success", message="Naabu scan started", results=[])
