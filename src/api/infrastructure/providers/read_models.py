from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.config import Settings

from api.application.agent_activity import AgentActivityService
from api.application.agent_task_detail import AgentTaskDetailService
from api.application.campaign_workspace import CampaignWorkspaceService
from api.application.program_projection_overview import ProgramProjectionOverviewService
from api.application.surface_component_analysis import SurfaceComponentAnalysisService
from api.application.workbench import WorkbenchReadService
from api.application.workbench_action_affordances import WorkbenchActionAffordanceService
from api.application.workbench_projection_control import WorkbenchProjectionControlService
from api.application.services.action import ActionService
from api.application.services.action_catalog import ActionCatalogService
from api.infrastructure.agent_activity import AgentActivityStore
from api.infrastructure.agent_task_detail import AgentTaskDetailStore
from api.infrastructure.campaign_workspace import CampaignWorkspaceStore
from api.infrastructure.program_projection_overview import ProgramProjectionOverviewStore
from api.infrastructure.surface_component_analysis import SurfaceComponentAnalysisStore
from api.infrastructure.workbench import WorkbenchGraphStore
from api.infrastructure.workbench_projection_control import WorkbenchProjectionControlStore


class ReadModelProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

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
    def get_workbench_graph_store(
        self,
        session_factory: async_sessionmaker,
        settings: Settings,
    ) -> WorkbenchGraphStore:
        return WorkbenchGraphStore(session_factory, settings)

    @provide(scope=Scope.APP)
    def get_workbench_projection_control_store(
        self,
        session_factory: async_sessionmaker,
        settings: Settings,
    ) -> WorkbenchProjectionControlStore:
        return WorkbenchProjectionControlStore(session_factory, settings)

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

    @provide(scope=Scope.REQUEST)
    def get_workbench_read_service(
        self,
        graph_store: WorkbenchGraphStore,
        projection_overview: ProgramProjectionOverviewService,
    ) -> WorkbenchReadService:
        return WorkbenchReadService(
            graph_store=graph_store,
            projection_overview=projection_overview,
        )

    @provide(scope=Scope.REQUEST)
    def get_workbench_action_affordance_service(
        self,
        workbench: WorkbenchReadService,
        catalog_service: ActionCatalogService,
        action_service: ActionService,
    ) -> WorkbenchActionAffordanceService:
        return WorkbenchActionAffordanceService(
            workbench=workbench,
            catalog=catalog_service,
            actions=action_service,
        )


    @provide(scope=Scope.REQUEST)
    def get_workbench_projection_control_service(
        self,
        store: WorkbenchProjectionControlStore,
    ) -> WorkbenchProjectionControlService:
        return WorkbenchProjectionControlService(store)
