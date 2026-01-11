"""REST API routes - Presentation layer"""
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


@router.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "ok", "service": "Bug Bounty Framework API"}


@router.post(
    "/scan/subfinder",
    response_model=ScanResponse,
    summary="Run Subfinder Scan",
    description="Starts Subfinder subdomain enumeration. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_subfinder(
    request: SubfinderScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start Subfinder scan to discover subdomains.

    - **program_id**: Program UUID
    - **domain**: Target domain to scan
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via SubfinderNode.
    """
    try:
        await event_bus.publish({
            "event": "subfinder_scan_requested",
            "target": request.domain,
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "domain": request.domain,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"Subfinder scan queued for domain {request.domain}",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/httpx",
    summary="Run HTTPX Scan",
    description="Starts HTTPX probing. Returns 202 Accepted immediately, scan runs asynchronously via node pipeline.",
    tags=["Scans"],
    status_code=202
)
async def scan_httpx(
    request: HTTPXScanRequest,
    event_bus: FromDishka[EventBus],
) -> JSONResponse:
    """
    Start HTTPX scan asynchronously via node pipeline.

    - **program_id**: Program UUID
    - **targets**: Single target or list of targets (URLs or domains)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via HTTPXNode.
    Results are ingested into database and trigger subsequent pipeline events.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        await event_bus.publish({
            "event": "httpx_scan_requested",
            "target": targets[0] if targets else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "targets": targets,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"HTTPX scan queued for {len(targets)} targets",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/gau",
    response_model=ScanResponse,
    summary="Run GAU Scan",
    description="Starts GAU URL discovery from web archives. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_gau(
    request: GAUScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start GAU (GetAllURLs) scan to discover historical URLs.

    - **program_id**: Program UUID
    - **domain**: Target domain to scan
    - **include_subs**: Include subdomains in discovery (default: true)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via GAUNode.
    """
    try:
        await event_bus.publish({
            "event": "gau_scan_requested",
            "target": request.domain,
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "domain": request.domain,
            "include_subs": request.include_subs,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"GAU scan queued for domain {request.domain}",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/katana",
    response_model=ScanResponse,
    summary="Run Katana Scan",
    description="Starts Katana web crawling. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_katana(
    request: KatanaScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start Katana crawl to discover URLs via active web crawling.

    - **program_id**: Program UUID
    - **targets**: Single target URL or list of target URLs to crawl
    - **depth**: Maximum crawl depth (default: 3)
    - **js_crawl**: Enable JavaScript endpoint parsing (default: true)
    - **headless**: Enable headless browser mode (default: false)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via KatanaNode.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        await event_bus.publish({
            "event": "katana_scan_requested",
            "target": targets[0] if targets else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "targets": targets,
            "depth": request.depth,
            "js_crawl": request.js_crawl,
            "headless": request.headless,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"Katana scan queued for {len(targets)} targets",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/linkfinder",
    response_model=ScanResponse,
    summary="Run LinkFinder Scan",
    description="Starts LinkFinder JS analysis to discover hidden endpoints. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_linkfinder(
    request: LinkFinderScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start LinkFinder scan to extract endpoints from JavaScript files.

    - **program_id**: Program UUID
    - **targets**: Single JS URL or list of JS URLs to analyze
    - **timeout**: Scan timeout per JS file in seconds (default: 15)

    Returns 202 Accepted immediately. Scan executes asynchronously via LinkFinderNode.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        await event_bus.publish({
            "event": "linkfinder_scan_requested",
            "target": targets[0] if targets else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "targets": targets,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"LinkFinder scan queued for {len(targets)} JS files",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/mantra",
    response_model=ScanResponse,
    summary="Run Mantra Scan",
    description="Starts Mantra secret scanning on JavaScript files. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_mantra(
    request: MantraScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start Mantra scan to discover leaked secrets and credentials in JavaScript files.

    - **program_id**: Program UUID
    - **targets**: Single JS URL or list of JS URLs to scan for secrets
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns 202 Accepted immediately. Scan executes asynchronously via MantraNode.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        await event_bus.publish({
            "event": "mantra_scan_requested",
            "target": targets[0] if targets else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "targets": targets,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"Mantra scan queued for {len(targets)} JS files",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/ffuf",
    response_model=ScanResponse,
    summary="Run FFUF Scan",
    description="Starts FFUF directory/file fuzzing. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_ffuf(
    request: FFUFScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start FFUF scan to discover hidden directories and files via fuzzing.

    - **program_id**: Program UUID
    - **targets**: Single base URL or list of URLs to fuzz
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via FFUFNode.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        await event_bus.publish({
            "event": "ffuf_scan_requested",
            "target": targets[0] if targets else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "targets": targets,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"FFUF scan queued for {len(targets)} targets",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/dnsx",
    response_model=ScanResponse,
    summary="Run DNSx Scan",
    description="Starts DNSx DNS enumeration (basic, deep, or ptr mode). Returns after scan completes.",
    tags=["Scans"]
)
async def scan_dnsx(
    request: DNSxScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start DNSx scan to enumerate DNS records for hosts or reverse lookup for IPs.

    - **program_id**: Program UUID
    - **targets**: Single domain/host or list of domains/hosts (for basic/deep), OR IP addresses (for ptr mode)
    - **mode**: Scan mode - 'basic' (A/AAAA/CNAME), 'deep' (all records including MX/TXT/NS/SOA), or 'ptr' (reverse DNS)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via DNSxNode (basic/deep/ptr).
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        event_name_map = {
            "basic": "dnsx_basic_scan_requested",
            "deep": "dnsx_deep_scan_requested",
            "ptr": "dnsx_ptr_scan_requested",
        }

        event_name = event_name_map.get(request.mode, "dnsx_basic_scan_requested")

        await event_bus.publish({
            "event": event_name,
            "target": targets[0] if targets else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "targets": targets,
            "mode": request.mode,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"DNSx {request.mode} scan queued for {len(targets)} targets",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/subjack",
    response_model=ScanResponse,
    summary="Run Subjack Scan",
    description="Starts Subjack subdomain takeover detection. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_subjack(
    request: SubjackScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start Subjack scan to detect subdomain takeover vulnerabilities.

    - **program_id**: Program UUID
    - **targets**: Single domain or list of domains to check for takeover
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns 202 Accepted immediately. Scan executes asynchronously via SubjackNode.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        await event_bus.publish({
            "event": "subjack_scan_requested",
            "target": targets[0] if targets else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "targets": targets,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"Subjack scan queued for {len(targets)} domains",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/asnmap",
    response_model=ScanResponse,
    summary="Run ASNMap Scan",
    description="Starts ASNMap ASN/CIDR enumeration. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_asnmap(
    request: ASNMapScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start ASNMap scan to enumerate ASN and CIDR ranges.

    - **program_id**: Program UUID
    - **targets**: Domains (mode=domain), ASN numbers (mode=asn), or organization names (mode=organization)
    - **mode**: Scan mode - 'domain', 'asn', or 'organization' (default: domain)
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns 202 Accepted immediately. Scan executes asynchronously via ASNMapNode.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        await event_bus.publish({
            "event": "asnmap_scan_requested",
            "target": targets[0] if targets else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "targets": targets,
            "mode": request.mode,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"ASNMap scan queued for {len(targets)} targets",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/mapcidr",
    response_model=ScanResponse,
    summary="Run MapCIDR Operation",
    description="Performs CIDR operations (expand, slice, aggregate). Returns immediately.",
    tags=["Scans"]
)
async def scan_mapcidr(
    request: MapCIDRScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Perform MapCIDR operations on CIDR blocks.

    - **program_id**: Program UUID
    - **cidrs**: Single CIDR or list of CIDRs to process
    - **operation**: Operation type - 'expand' (only expand supported via node pipeline)
    - **skip_base**: Skip base IPs ending in .0
    - **skip_broadcast**: Skip broadcast IPs ending in .255
    - **shuffle**: Shuffle IPs in random order
    - **timeout**: Scan timeout in seconds (default: 300)

    Returns 202 Accepted immediately. Scan executes asynchronously via MapCIDRNode.
    """
    try:
        cidrs = request.cidrs if isinstance(request.cidrs, list) else [request.cidrs]

        if request.operation != "expand":
            raise ValueError("Only 'expand' operation is supported via node pipeline")

        await event_bus.publish({
            "event": "mapcidr_scan_requested",
            "target": cidrs[0] if cidrs else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "cidrs": cidrs,
            "skip_base": request.skip_base,
            "skip_broadcast": request.skip_broadcast,
            "shuffle": request.shuffle,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"MapCIDR expand queued for {len(cidrs)} CIDRs",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/mapcidr/slice",
    response_model=ScanResponse,
    summary="Run MapCIDR Slice Operations (Legacy)",
    description="Legacy endpoint for slice/aggregate operations. Use with caution.",
    tags=["Scans"],
    deprecated=True
)
async def scan_mapcidr_legacy(
    request: MapCIDRScanRequest,
    mapcidr_service: FromDishka[MapCIDRService],
) -> ScanResponse:
    """
    Legacy MapCIDR endpoint for slice_count, slice_host, aggregate operations.
    This endpoint calls the service directly and is not part of the node pipeline.
    """
    try:
        cidrs = request.cidrs if isinstance(request.cidrs, list) else [request.cidrs]
        program_id = UUID(request.program_id)

        if request.operation == "slice_count":
            if not request.count:
                raise ValueError("count parameter required for slice_count operation")
            result = await mapcidr_service.slice_by_count(
                program_id=program_id,
                cidrs=cidrs,
                count=request.count
            )
        elif request.operation == "slice_host":
            if not request.host_count:
                raise ValueError("host_count parameter required for slice_host operation")
            result = await mapcidr_service.slice_by_host_count(
                program_id=program_id,
                cidrs=cidrs,
                host_count=request.host_count
            )
        elif request.operation == "aggregate":
            result = await mapcidr_service.aggregate(
                program_id=program_id,
                ips=cidrs
            )
        else:
            raise ValueError(f"Invalid operation: {request.operation}")

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/naabu",
    response_model=ScanResponse,
    summary="Run Naabu Port Scan",
    description="Starts Naabu port scanning (active, passive, or nmap mode). Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_naabu(
    request: NaabuScanRequest,
    event_bus: FromDishka[EventBus],
):
    """
    Start Naabu port scan to discover open ports and services.

    - **program_id**: Program UUID
    - **targets**: Single host/IP or list of hosts/IPs to scan
    - **scan_mode**: Scan mode - 'active' (default), 'passive', or 'nmap'
    - **ports**: Port specification (e.g., "80,443,8080-8090") or None for top-ports
    - **top_ports**: Top ports preset - "100", "1000" (default), "full"
    - **rate**: Packets per second (default: 1000)
    - **scan_type**: Scan type - "s" (SYN) or "c" (CONNECT, default)
    - **exclude_cdn**: Skip full port scans for CDN/WAF, only scan 80,443 (default: true)
    - **nmap_cli**: Nmap command for service detection (nmap mode only, default: "nmap -sV")
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns 202 Accepted immediately. Scan executes asynchronously via NaabuNode.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        await event_bus.publish({
            "event": "naabu_scan_requested",
            "target": targets[0] if targets else "",
            "source": "api",
            "confidence": 0.5,
            "program_id": request.program_id,
            "targets": targets,
            "scan_mode": request.scan_mode,
            "ports": request.ports,
            "top_ports": request.top_ports,
            "rate": request.rate,
            "scan_type": request.scan_type,
            "exclude_cdn": request.exclude_cdn,
            "nmap_cli": request.nmap_cli,
        })

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": f"Naabu {request.scan_mode} scan queued for {len(targets)} targets",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
