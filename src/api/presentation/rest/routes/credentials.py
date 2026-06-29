"""REST boundary for credential refs and secret rotation."""
from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query

from api.application.credential_management import (
    CredentialCreateRequest,
    CredentialExpireCurrentSecretRequest,
    CredentialManagementService,
    CredentialMetadataReadRequest,
    CredentialSecretRotateRequest,
)
from api.application.credential_storage import CredentialStorageError

router = APIRouter(route_class=DishkaRoute)


@router.post(
    "",
    summary="Register credential identity ref",
    description=(
        "Creates an audit-safe credential_ref identity record. This endpoint "
        "does not accept raw secret material; rotate the secret separately."
    ),
    tags=["Credentials"],
    status_code=201,
)
async def register_credential(
    request: CredentialCreateRequest,
    service: FromDishka[CredentialManagementService],
) -> dict:
    try:
        return {"credential": service.register_credential(request), "secret_material": None}
    except CredentialStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "",
    summary="List credential metadata",
    description="Lists audit-safe credential metadata for a program without secret material.",
    tags=["Credentials"],
)
async def list_credentials(
    service: FromDishka[CredentialManagementService],
    program_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    try:
        return {"items": service.list_metadata(program_id=program_id, limit=limit, offset=offset)}
    except CredentialStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/metadata",
    summary="Read credential metadata",
    description="Returns one audit-safe credential metadata record without secret material.",
    tags=["Credentials"],
)
async def get_credential_metadata(
    service: FromDishka[CredentialManagementService],
    program_id: UUID,
    credential_ref: str,
) -> dict:
    try:
        metadata = service.get_metadata(
            CredentialMetadataReadRequest(program_id=program_id, credential_ref=credential_ref)
        )
    except CredentialStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"credential": metadata}


@router.post(
    "/rotate-secret",
    summary="Rotate credential secret version",
    description=(
        "Stores a new secret version behind an existing credential_ref. The "
        "response is audit-safe and never returns the submitted secret value."
    ),
    tags=["Credentials"],
)
async def rotate_credential_secret(
    request: CredentialSecretRotateRequest,
    service: FromDishka[CredentialManagementService],
) -> dict:
    try:
        return service.rotate_secret(request)
    except CredentialStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/expire-current-secret",
    summary="Mark current credential secret as expired",
    description="Expires the current secret version and marks the credential as refresh_due.",
    tags=["Credentials"],
)
async def expire_current_credential_secret(
    request: CredentialExpireCurrentSecretRequest,
    service: FromDishka[CredentialManagementService],
) -> dict:
    try:
        return service.mark_current_secret_expired(request)
    except CredentialStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
