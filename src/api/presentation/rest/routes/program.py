# api/presentation/rest/routes/program.py
from uuid import UUID
from xml.dom import NotFoundErr

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, status

from api.application.dto.program import (ProgramCreateDTO,
                                         ProgramFullResponseDTO,
                                         ProgramResponseDTO)
from api.application.services.program import ProgramService

router = APIRouter(prefix="/programs", tags=["Programs"], route_class=DishkaRoute)


@router.post(
    "/",
    response_model=ProgramFullResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create new program",
    description="Create a new bug bounty program with scope rules and root inputs."
)
async def create_program(
    request: ProgramCreateDTO,
    program_service: FromDishka[ProgramService]
) -> ProgramFullResponseDTO:
    """Create a new program"""
    try:
        return await program_service.create_program(request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/{program_id}",
    response_model=ProgramFullResponseDTO,
    summary="Get program with relations",
    description="Get program details including scope rules and root inputs."
)
async def get_program(
    program_id: UUID,
    program_service: FromDishka[ProgramService]
) -> ProgramFullResponseDTO:
    """Get program by ID with all relations"""
    try:
        return await program_service.get_program_with_relations(program_id)
    except NotFoundErr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Program {program_id} not found"
        )


@router.get(
    "/{program_id}/basic",
    response_model=ProgramResponseDTO,
    summary="Get basic program info",
    description="Get basic program information without relations."
)
async def get_program_basic(
    program_id: UUID,
    program_service: FromDishka[ProgramService]
) -> ProgramResponseDTO:
    """Get basic program info"""
    program = await program_service.get_program(program_id)
    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Program {program_id} not found"
        )
    return program


@router.get(
    "/",
    response_model=list[ProgramResponseDTO],
    summary="List programs",
    description="Get paginated list of programs."
)
async def list_programs(
    limit: int = 100,
    offset: int = 0,
    program_service: FromDishka[ProgramService] = None
) -> list[ProgramResponseDTO]:
    """List all programs with pagination"""
    return await program_service.list_programs(limit=limit, offset=offset)


@router.patch(
    "/{program_id}/name",
    response_model=ProgramResponseDTO,
    summary="Update program name",
    description="Update program name only."
)
async def update_program_name(
    program_id: UUID,
    new_name: str,
    program_service: FromDishka[ProgramService]
) -> ProgramResponseDTO:
    """Update program name"""
    try:
        return await program_service.update_program_name(program_id, new_name)
    except NotFoundErr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Program {program_id} not found"
        )


@router.delete(
    "/{program_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete program",
    description="Delete program and all its related data (scope rules, root inputs)."
)
async def delete_program(
    program_id: UUID,
    program_service: FromDishka[ProgramService]
):
    """Delete program"""
    try:
        await program_service.delete_program(program_id)
    except NotFoundErr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Program {program_id} not found"
        )