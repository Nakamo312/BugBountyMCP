"""Combine all routes into single router"""
from fastapi import APIRouter
from .program import router as program_router
from .host import router as host_router
from .analysis import router as analysis_router
from .infrastructure import router as infrastructure_router
from .actions import router as actions_router
from .agent_protocol import router as agent_protocol_router
from .agent_tasks import router as agent_tasks_router
from .agent_action_proposals import router as agent_action_proposals_router
from .action_experience_proposals import router as action_experience_proposals_router
from .campaign_workspace import router as campaign_workspace_router
from .agent_activity import router as agent_activity_router
from .graph import router as graph_router
from .surface_component_analysis import router as surface_component_analysis_router
from .program_projection_overview import router as program_projection_overview_router
from .credentials import router as credentials_router

router = APIRouter()

router.include_router(program_router, prefix="/api/v1", tags=["Programs"])
router.include_router(host_router, prefix="/api/v1/hosts", tags=["Hosts"])
router.include_router(analysis_router, prefix="/api/v1/analysis", tags=["Analysis"])
router.include_router(infrastructure_router, prefix="/api/v1/infrastructure", tags=["Infrastructure"])
router.include_router(actions_router, prefix="/api/v1/actions", tags=["Actions"])
router.include_router(actions_router, prefix="/api/v1/tool-actions", tags=["Tool Actions"])
router.include_router(agent_protocol_router, prefix="/api/v1/agent", tags=["Agent Protocol"])
router.include_router(agent_tasks_router, prefix="/api/v1/agent-tasks", tags=["Agent Tasks"])
router.include_router(agent_action_proposals_router, prefix="/api/v1/agent-action-proposals", tags=["Agent Action Proposals"])
router.include_router(action_experience_proposals_router, prefix="/api/v1/action-experience-proposals", tags=["Action Experience Proposals"])
router.include_router(campaign_workspace_router, prefix="/api/v1/campaign-workspace", tags=["Campaign Workspace"])
router.include_router(agent_activity_router, prefix="/api/v1/agent-activity", tags=["Agent Activity"])
router.include_router(graph_router, prefix="/api/v1/graph", tags=["Graph"])
router.include_router(surface_component_analysis_router, prefix="/api/v1/surface-component-analysis", tags=["Surface Component Analysis"])
router.include_router(program_projection_overview_router, prefix="/api/v1/program-projection-overview", tags=["Program Projection Overview"])
router.include_router(credentials_router, prefix="/api/v1/credentials", tags=["Credentials"])
