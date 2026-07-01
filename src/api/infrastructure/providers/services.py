from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.ports.runners import ToolRunnerFactoryPort
from api.application.services.analysis import AnalysisService
from api.application.services.host import HostService
from api.application.services.infrastructure import InfrastructureService
from api.application.services.mapcidr import MapCIDRService
from api.application.services.program import ProgramService
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.host_asset_reader import RepositoryHostAssetReader
from api.infrastructure.infrastructure_graph_reader import RepositoryInfrastructureGraphReader
from api.infrastructure.program_store import RepositoryProgramStore
from api.infrastructure.read_only_view_reader import SQLAlchemyReadOnlyViewReader
from api.infrastructure.unit_of_work.adapters.httpx import SQLAlchemyHTTPXUnitOfWork
from api.infrastructure.unit_of_work.adapters.infrastructure import SQLAlchemyInfrastructureUnitOfWork


class ServiceProvider(Provider):
    scope = Scope.APP

    @provide(scope=Scope.REQUEST)
    def get_program_service(self, session_factory: async_sessionmaker) -> ProgramService:
        return ProgramService(RepositoryProgramStore(session_factory))

    @provide(scope=Scope.REQUEST)
    def get_mapcidr_service(
        self,
        tool_runner_factory: ToolRunnerFactoryPort,
        event_bus: EventBus,
    ) -> MapCIDRService:
        return MapCIDRService(
            runner_factory=tool_runner_factory,
            bus=event_bus,
        )

    @provide(scope=Scope.REQUEST)
    def get_host_service(
        self,
        scan_uow: SQLAlchemyHTTPXUnitOfWork
    ) -> HostService:
        return HostService(
            RepositoryHostAssetReader(scan_uow),
            SQLAlchemyReadOnlyViewReader(scan_uow),
        )

    @provide(scope=Scope.REQUEST)
    def get_analysis_service(
        self,
        scan_uow: SQLAlchemyHTTPXUnitOfWork
    ) -> AnalysisService:
        return AnalysisService(SQLAlchemyReadOnlyViewReader(scan_uow))

    @provide(scope=Scope.REQUEST)
    def get_infrastructure_service(
        self,
        infrastructure_uow: SQLAlchemyInfrastructureUnitOfWork,
    ) -> InfrastructureService:
        return InfrastructureService(
            RepositoryInfrastructureGraphReader(infrastructure_uow),
        )
