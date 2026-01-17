from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from api.presentation.schemas import (
    HTTPXScanRequest,
    SubfinderScanRequest,
    GAUScanRequest,
    KatanaScanRequest,
    LinkFinderScanRequest,
    MantraScanRequest,
    FFUFScanRequest,
    DNSxScanRequest,
    SubjackScanRequest,
    ASNMapScanRequest,
    MapCIDRScanRequest,
    NaabuScanRequest,
    ScanResponse
)
from api.application.services.mapcidr import MapCIDRService
from api.infrastructure.events.event_bus import EventBus

router = APIRouter(route_class=DishkaRoute)


async def publish_scan_event(
    event_bus: EventBus,
    *,
    event: str,
    program_id: UUID,
    targets: list[str],
    extra: dict | None = None,
):
    if not targets:
        raise ValueError("targets list cannot be empty")

    payload = {
        "event": event,
        "source": "api",
        "confidence": 0.5,
        "program_id": program_id,
        "targets": targets,
        "target": targets[0],
    }
    if extra:
        payload.update(extra)

    await event_bus.publish(payload)


async def scan_endpoint(request, event_bus: FromDishka[EventBus], event_name: str, extra: dict | None = None):
    try:
        await publish_scan_event(
            event_bus,
            event=event_name,
            program_id=request.program_id,
            targets=request.targets,
            extra=extra
        )
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"{event_name.replace('_', ' ').title()} queued for {len(request.targets)} targets",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "ok", "service": "Bug Bounty Framework API"}


@router.post("/scan/subfinder", response_model=ScanResponse, summary="Run Subfinder Scan", description="Starts Subfinder subdomain enumeration. Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_subfinder(request: SubfinderScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start Subfinder scan to discover subdomains.

    - **program_id**: Program UUID
    - **targets**: List of target domains
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via SubfinderNode.
    """
    return await scan_endpoint(request, event_bus, "subfinder_scan_requested")


@router.post("/scan/httpx", summary="Run HTTPX Scan", description="Starts HTTPX probing. Returns 202 Accepted immediately, scan runs asynchronously via node pipeline.", tags=["Scans"], status_code=202)
async def scan_httpx(request: HTTPXScanRequest, event_bus: FromDishka[EventBus]) -> JSONResponse:
    """
    Start HTTPX scan asynchronously via node pipeline.

    - **program_id**: Program UUID
    - **targets**: List of targets (URLs or domains)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via HTTPXNode.
    """
    return await scan_endpoint(request, event_bus, "httpx_scan_requested")


@router.post("/scan/gau", response_model=ScanResponse, summary="Run GAU Scan", description="Starts GAU URL discovery from web archives. Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_gau(request: GAUScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start GAU (GetAllURLs) scan to discover historical URLs.

    - **program_id**: Program UUID
    - **targets**: List of target domains
    - **include_subs**: Include subdomains in discovery (default: true)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via GAUNode.
    """
    extra = {"include_subs": request.include_subs}
    return await scan_endpoint(request, event_bus, "gau_scan_requested", extra=extra)


@router.post("/scan/waymore", response_model=ScanResponse, summary="Run Waymore Scan", description="Starts Waymore URL discovery from multiple sources (Wayback, URLScan, AlienVault, VirusTotal). Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_waymore(request: SubfinderScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start Waymore scan to discover historical URLs from multiple sources.

    Sources: Wayback Machine, URLScan, Alien Vault OTX, Virus Total (Common Crawl excluded by default).

    - **program_id**: Program UUID
    - **targets**: List of target domains (subdomains will be automatically discovered)

    Returns 202 Accepted immediately. Scan executes asynchronously via WaymoreNode.
    URLs are sent to HTTPX for live probing.
    """
    return await scan_endpoint(request, event_bus, "subdomain_discovered")


@router.post("/scan/katana", response_model=ScanResponse, summary="Run Katana Scan", description="Starts Katana web crawling. Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_katana(request: KatanaScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start Katana crawl to discover URLs via active web crawling.

    - **program_id**: Program UUID
    - **targets**: List of target URLs to crawl
    - **depth**: Maximum crawl depth (default: 3)
    - **js_crawl**: Enable JavaScript endpoint parsing (default: true)
    - **headless**: Enable headless browser mode (default: false)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via KatanaNode.
    """
    extra = {
        "depth": request.depth,
        "js_crawl": request.js_crawl,
        "headless": request.headless
    }
    return await scan_endpoint(request, event_bus, "katana_scan_requested", extra=extra)


@router.post("/scan/linkfinder", response_model=ScanResponse, summary="Run LinkFinder Scan", description="Starts LinkFinder JS analysis to discover hidden endpoints. Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_linkfinder(request: LinkFinderScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start LinkFinder scan to extract endpoints from JavaScript files.

    - **program_id**: Program UUID
    - **targets**: List of JS URLs to analyze
    - **timeout**: Scan timeout per JS file in seconds (default: 15)

    Returns 202 Accepted immediately. Scan executes asynchronously via LinkFinderNode.
    """
    return await scan_endpoint(request, event_bus, "linkfinder_scan_requested")


@router.post("/scan/mantra", response_model=ScanResponse, summary="Run Mantra Scan", description="Starts Mantra secret scanning on JavaScript files. Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_mantra(request: MantraScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start Mantra scan to discover leaked secrets and credentials in JavaScript files.

    - **program_id**: Program UUID
    - **targets**: List of JS URLs to scan
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns 202 Accepted immediately. Scan executes asynchronously via MantraNode.
    """
    return await scan_endpoint(request, event_bus, "mantra_scan_requested")


@router.post("/scan/ffuf", response_model=ScanResponse, summary="Run FFUF Scan", description="Starts FFUF directory/file fuzzing. Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_ffuf(request: FFUFScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start FFUF scan to discover hidden directories and files via fuzzing.

    - **program_id**: Program UUID
    - **targets**: List of URLs to fuzz
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via FFUFNode.
    """
    return await scan_endpoint(request, event_bus, "ffuf_scan_requested")


DNSX_EVENT_MAP = {
    "basic": "dnsx_basic_scan_requested",
    "deep": "dnsx_deep_scan_requested",
    "ptr": "dnsx_ptr_scan_requested",
}

@router.post("/scan/dnsx", response_model=ScanResponse, summary="Run DNSx Scan", description="Starts DNSx DNS enumeration (basic, deep, or ptr mode). Returns immediately.", tags=["Scans"], status_code=202)
async def scan_dnsx(request: DNSxScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start DNSx scan to enumerate DNS records for hosts or reverse lookup for IPs.

    - **program_id**: Program UUID
    - **targets**: List of domains/hosts or IPs
    - **mode**: 'basic', 'deep', or 'ptr'
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via DNSxNode.
    """
    event_name = DNSX_EVENT_MAP.get(request.mode)
    if not event_name:
        raise HTTPException(status_code=400, detail=f"Invalid DNSx mode: {request.mode}")
    return await scan_endpoint(request, event_bus, event_name, extra={"mode": request.mode})


@router.post("/scan/subjack", response_model=ScanResponse, summary="Run Subjack Scan", description="Starts Subjack subdomain takeover detection. Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_subjack(request: SubjackScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start Subjack scan to detect subdomain takeover vulnerabilities.

    - **program_id**: Program UUID
    - **targets**: List of domains to check for takeover
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns 202 Accepted immediately. Scan executes asynchronously via SubjackNode.
    """
    return await scan_endpoint(request, event_bus, "subjack_scan_requested")


@router.post("/scan/asnmap", response_model=ScanResponse, summary="Run ASNMap Scan", description="Starts ASNMap ASN/CIDR enumeration. Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_asnmap(request: ASNMapScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start ASNMap scan to enumerate ASN and CIDR ranges.

    - **program_id**: Program UUID
    - **targets**: List of domains, ASNs, or organizations
    - **mode**: 'domain', 'asn', or 'organization'
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns 202 Accepted immediately. Scan executes asynchronously via ASNMapNode.
    """
    return await scan_endpoint(request, event_bus, "asnmap_scan_requested", extra={"mode": request.mode})


@router.post("/scan/mapcidr", response_model=ScanResponse, summary="Run MapCIDR Operation", description="Performs CIDR operations (expand, slice, aggregate). Returns immediately.", tags=["Scans"], status_code=202)
async def scan_mapcidr(request: MapCIDRScanRequest, event_bus: FromDishka[EventBus]):
    """
    Perform MapCIDR operations on CIDR blocks.

    - **program_id**: Program UUID
    - **targets**: List of CIDRs
    - **operation**: Only 'expand' supported via node pipeline
    - **skip_base**: Skip base IPs ending in .0
    - **skip_broadcast**: Skip broadcast IPs ending in .255
    - **shuffle**: Shuffle IPs randomly
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns 202 Accepted immediately. Scan executes asynchronously via MapCIDRNode.
    """
    if request.operation != "expand":
        raise HTTPException(status_code=400, detail="Only 'expand' operation is supported")
    extra = {
        "skip_base": request.skip_base,
        "skip_broadcast": request.skip_broadcast,
        "shuffle": request.shuffle
    }
    return await scan_endpoint(request, event_bus, "mapcidr_scan_requested", extra=extra)


@router.post("/scan/mapcidr/slice", response_model=ScanResponse, summary="Run MapCIDR Slice Operations (Legacy)", description="Legacy endpoint for slice/aggregate operations. Use with caution.", tags=["Scans"], deprecated=True)
async def scan_mapcidr_legacy(request: MapCIDRScanRequest, mapcidr_service: FromDishka[MapCIDRService]) -> ScanResponse:
    """
    Legacy MapCIDR endpoint for slice_count, slice_host, aggregate operations.
    This endpoint calls the service directly and is not part of the node pipeline.
    """
    try:
        targets = request.targets
        program_id = UUID(request.program_id)

        if request.operation == "slice_count":
            if not request.count:
                raise ValueError("count parameter required for slice_count operation")
            result = await mapcidr_service.slice_by_count(program_id=program_id, cidrs=targets, count=request.count)
        elif request.operation == "slice_host":
            if not request.host_count:
                raise ValueError("host_count parameter required for slice_host operation")
            result = await mapcidr_service.slice_by_host_count(program_id=program_id, cidrs=targets, host_count=request.host_count)
        elif request.operation == "aggregate":
            result = await mapcidr_service.aggregate(program_id=program_id, ips=targets)
        else:
            raise ValueError(f"Invalid operation: {request.operation}")

        return ScanResponse(status="success", message=result.message, results=result.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post("/scan/naabu", response_model=ScanResponse, summary="Run Naabu Port Scan", description="Starts Naabu port scanning (active, passive, or nmap mode). Returns immediately, scan runs in background.", tags=["Scans"], status_code=202)
async def scan_naabu(request: NaabuScanRequest, event_bus: FromDishka[EventBus]):
    """
    Start Naabu port scan to discover open ports and services.

    - **program_id**: Program UUID
    - **targets**: List of hosts/IPs to scan
    - **scan_mode**: 'active', 'passive', or 'nmap'
    - **ports**: Port specification or None
    - **top_ports**: Top ports preset
    - **rate**: Packets per second
    - **scan_type**: "s" (SYN) or "c" (CONNECT)
    - **exclude_cdn**: Skip full port scans for CDN/WAF
    - **nmap_cli**: Nmap command (nmap mode only)
    - **timeout**: Scan timeout in seconds

    Returns 202 Accepted immediately. Scan executes asynchronously via NaabuNode.
    """
    extra = {
        "scan_mode": request.scan_mode,
        "ports": request.ports,
        "top_ports": request.top_ports,
        "rate": request.rate,
        "scan_type": request.scan_type,
        "exclude_cdn": request.exclude_cdn,
        "nmap_cli": request.nmap_cli,
    }
    return await scan_endpoint(request, event_bus, "naabu_scan_requested", extra=extra)
