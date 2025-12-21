"""REST API routes"""
from fastapi import APIRouter
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from ...application.services.subfinder import SubfinderScanService
from ...application.services.httpx import HTTPXScanService


router = APIRouter(route_class=DishkaRoute)


@router.post("/scan/subfinder")
async def scan_subfinder(
    program_id: str,
    domain: str,
    probe: bool = True,
    subfinder_service: FromDishka[SubfinderScanService],
) -> dict:
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
    return await subfinder_service.execute(
        program_id=program_id,
        domain=domain,
        probe=probe,
    )


@router.post("/scan/httpx")
async def scan_httpx(
    program_id: str,
    targets: list[str] | str,
    httpx_service: FromDishka[HTTPXScanService],
) -> dict:
    """
    Execute HTTPX scan.
    
    Args:
        program_id: Program UUID
        targets: Single target or list of targets
        httpx_service: Injected HTTPXScanService
        
    Returns:
        Scan results
    """
    return await httpx_service.execute(
        program_id=program_id,
        targets=targets,
    )

