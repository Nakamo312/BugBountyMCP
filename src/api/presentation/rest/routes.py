"""REST API routes"""
from fastapi import APIRouter, Query, Body
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from api.presentation.schemas import HTTPXScanRequest, ScanResponse, SubfinderScanRequest

from api.application.services.subfinder import SubfinderScanService
from api.application.services.httpx import HTTPXScanService


router = APIRouter(route_class=DishkaRoute)


@router.post("/scan/subfinder",
    response_model=ScanResponse,
    summary="Run Subfinder Scan",
    description="Executes Subfinder to discover subdomains for a given target."
)
async def scan_subfinder(
    request: SubfinderScanRequest,
    *,
    subfinder_service: FromDishka[SubfinderScanService],
) -> ScanResponse:
    """
    Execute Subfinder scan to discover subdomains.
    
    Args:
        program_id: Program UUID
        domain: Target domain to scan
        probe: If True, probe discovered subdomains with HTTPX (default: True)
        subfinder_service: Injected SubfinderScanService
        
    Returns:
        Scan results
    """
    results = await subfinder_service.execute(
        program_id=request.program_id,
        domain=request.domain,
        probe=request.probe,
    )
    
    return ScanResponse(
        status="success",
        message=f"Subfinder scan completed for {request.domain}",
        results=results
    )


@router.post(
    "/scan/httpx",
    response_model=ScanResponse,
    summary="Run HTTPX Scan",
    description="Executes HTTPX probing on a list of targets."
)
async def scan_httpx(
    request: HTTPXScanRequest,
    *,
    httpx_service: FromDishka[HTTPXScanService],
) -> ScanResponse:
    """
    Execute HTTPX scan.
    
    Args:
        program_id: Program UUID
        targets: Single target or list of targets
        httpx_service: Injected HTTPXScanService
        
    Returns:
        Scan results
    """
    results = await httpx_service.execute(
            program_id=request.program_id,
            targets=request.targets,
        )

    return ScanResponse(
        status="success",
        message="HTTPX scan completed",
        results=results
    )

