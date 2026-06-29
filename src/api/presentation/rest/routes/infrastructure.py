"""REST routes for infrastructure graph"""

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

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
    return await infrastructure_service.get_infrastructure_graph(program_id)
