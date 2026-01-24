"""Proxy route for making HTTP requests to external hosts"""

import logging
from typing import Dict, Optional, List

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class ProxyRequestDTO(BaseModel):
    url: str
    method: str = "GET"
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, str]] = None
    body: Optional[str] = None
    timeout: int = 10


class ProxyResponseDTO(BaseModel):
    status_code: int
    status_text: str
    headers: Dict[str, str]
    body: str
    url: str


@router.post(
    "/proxy",
    response_model=ProxyResponseDTO,
    summary="Proxy HTTP request",
    description="Make HTTP request to external host bypassing CORS"
)
async def proxy_request(request: ProxyRequestDTO) -> ProxyResponseDTO:
    try:
        async with httpx.AsyncClient(
            timeout=request.timeout,
            follow_redirects=True,
            verify=False
        ) as client:
            response = await client.request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                params=request.params,
                content=request.body if request.body else None,
            )

            response_headers = {k: v for k, v in response.headers.items()}

            try:
                body = response.text
            except Exception:
                body = response.content.decode('utf-8', errors='replace')

            return ProxyResponseDTO(
                status_code=response.status_code,
                status_text=httpx.codes.get_reason_phrase(response.status_code),
                headers=response_headers,
                body=body,
                url=str(response.url),
            )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request timeout"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Request failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Proxy error: {str(e)}"
        )
