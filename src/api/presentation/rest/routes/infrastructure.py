"""REST routes for infrastructure graph"""

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, status

from api.application.dto.infrastructure import InfrastructureGraphDTO
from api.application.services.infrastructure import InfrastructureService

router = APIRouter(tags=["Infrastructure"], route_class=DishkaRoute)


@router.get(
    "/program/{program_id}/graph",
    response_model=InfrastructureGraphDTO,
    summary="Get infrastructure graph",
    description="Get infrastructure graph for visualization"
)
async def get_infrastructure_graph(
    program_id: UUID,
    infrastructure_service: FromDishka[InfrastructureService] = None
) -> InfrastructureGraphDTO:
    try:
        return await infrastructure_service.get_infrastructure_graph(program_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching infrastructure graph: {str(e)}"
        )
