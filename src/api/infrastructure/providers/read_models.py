from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.agent_activity import AgentActivityService
from api.application.agent_task_detail import AgentTaskDetailService
from api.application.campaign_workspace import CampaignWorkspaceService
from api.application.program_projection_overview import ProgramProjectionOverviewService
from api.application.surface_component_analysis import SurfaceComponentAnalysisService
from api.infrastructure.agent_activity import AgentActivityStore
from api.infrastructure.agent_task_detail import AgentTaskDetailStore
from api.infrastructure.campaign_workspace import CampaignWorkspaceStore
from api.infrastructure.program_projection_overview import ProgramProjectionOverviewStore
from api.infrastructure.surface_component_analysis import SurfaceComponentAnalysisStore


class ReadModelProvider(Provider):
    scope = Scope.APP

    @provide(scope=Scope.APP)
    def get_campaign_workspace_store(self, session_factory: async_sessionmaker) -> CampaignWorkspaceStore:
        return CampaignWorkspaceStore(session_factory)

    @provide(scope=Scope.APP)
    def get_surface_component_analysis_store(self, session_factory: async_sessionmaker) -> SurfaceComponentAnalysisStore:
        return SurfaceComponentAnalysisStore(session_factory)

    @provide(scope=Scope.APP)
    def get_program_projection_overview_store(self, session_factory: async_sessionmaker) -> ProgramProjectionOverviewStore:
        return ProgramProjectionOverviewStore(session_factory)

    @provide(scope=Scope.APP)
    def get_agent_task_detail_store(self, session_factory: async_sessionmaker) -> AgentTaskDetailStore:
        return AgentTaskDetailStore(session_factory)

    @provide(scope=Scope.APP)
    def get_agent_activity_store(self, session_factory: async_sessionmaker) -> AgentActivityStore:
        return AgentActivityStore(session_factory)

    @provide(scope=Scope.REQUEST)
    def get_agent_activity_service(
        self,
        store: AgentActivityStore,
    ) -> AgentActivityService:
        return AgentActivityService(store)

    @provide(scope=Scope.REQUEST)
    def get_agent_task_detail_service(
        self,
        store: AgentTaskDetailStore,
    ) -> AgentTaskDetailService:
        return AgentTaskDetailService(store)

    @provide(scope=Scope.REQUEST)
    def get_campaign_workspace_service(
        self,
        store: CampaignWorkspaceStore,
    ) -> CampaignWorkspaceService:
        return CampaignWorkspaceService(store)

    @provide(scope=Scope.REQUEST)
    def get_surface_component_analysis_service(
        self,
        store: SurfaceComponentAnalysisStore,
    ) -> SurfaceComponentAnalysisService:
        return SurfaceComponentAnalysisService(store)

    @provide(scope=Scope.REQUEST)
    def get_program_projection_overview_service(
        self,
        store: ProgramProjectionOverviewStore,
    ) -> ProgramProjectionOverviewService:
        return ProgramProjectionOverviewService(store)
