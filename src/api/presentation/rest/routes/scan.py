"""REST API routes - Presentation layer"""
from uuid import UUID
from fastapi import APIRouter, HTTPException
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from api.presentation.schemas import (
    HTTPXScanRequest,
    SubfinderScanRequest,
    GAUScanRequest,
    ScanResponse
)
from api.application.services.subfinder import SubfinderScanService
from api.application.services.httpx import HTTPXScanService
from api.application.services.gau import GAUScanService


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
    subfinder_service: FromDishka[SubfinderScanService],
) -> ScanResponse:
    """
    Start Subfinder scan to discover subdomains.

    - **program_id**: Program UUID
    - **domain**: Target domain to scan
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns immediately. Discovered subdomains are published to EventBus for HTTPX processing.
    """
    try:
        result = await subfinder_service.execute(
            program_id=UUID(request.program_id),
            domain=request.domain
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")


@router.post(
    "/scan/httpx",
    response_model=ScanResponse,
    summary="Run HTTPX Scan",
    description="Starts HTTPX probing. Returns immediately, scan runs in background.",
    tags=["Scans"]
)
async def scan_httpx(
    request: HTTPXScanRequest,
    httpx_service: FromDishka[HTTPXScanService],
) -> ScanResponse:
    """
    Start HTTPX scan.

    - **program_id**: Program UUID
    - **targets**: Single target or list of targets (URLs or domains)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns immediately. Results are published to EventBus for ingestion.
    """
    try:
        targets = request.targets if isinstance(request.targets, list) else [request.targets]

        result = await httpx_service.execute(
            program_id=UUID(request.program_id),
            targets=targets
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
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
    gau_service: FromDishka[GAUScanService],
) -> ScanResponse:
    """
    Start GAU (GetAllURLs) scan to discover historical URLs.

    - **program_id**: Program UUID
    - **domain**: Target domain to scan
    - **include_subs**: Include subdomains in discovery (default: true)
    - **timeout**: Scan timeout in seconds (default: 600)

    Returns immediately. Discovered URLs are published to EventBus for HTTPX processing.
    """
    try:
        result = await gau_service.execute(
            program_id=UUID(request.program_id),
            domain=request.domain,
            include_subs=request.include_subs
        )

        return ScanResponse(
            status="success",
            message=result.message,
            results=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
