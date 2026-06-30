from dishka import Provider, Scope, provide

from api.application.services.analysis import AnalysisService
from api.application.services.host import HostService
from api.application.services.infrastructure import InfrastructureService
from api.application.services.mapcidr import MapCIDRService
from api.application.services.program import ProgramService
from api.infrastructure.events.event_bus import EventBus
from api.application.ports.runners import ToolRunnerFactoryPort
from api.infrastructure.unit_of_work.adapters.httpx import SQLAlchemyHTTPXUnitOfWork
from api.infrastructure.unit_of_work.adapters.infrastructure import SQLAlchemyInfrastructureUnitOfWork
from api.infrastructure.unit_of_work.interfaces.program import ProgramUnitOfWork


class ServiceProvider(Provider):
    scope = Scope.APP

    @provide(scope=Scope.REQUEST)
    def get_program_service(self, program_uow: ProgramUnitOfWork) -> ProgramService:
        return ProgramService(program_uow)

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
        return HostService(scan_uow)

    @provide(scope=Scope.REQUEST)
    def get_analysis_service(
        self,
        scan_uow: SQLAlchemyHTTPXUnitOfWork
    ) -> AnalysisService:
        return AnalysisService(scan_uow)

    @provide(scope=Scope.REQUEST)
    def get_infrastructure_service(
        self,
        infrastructure_uow: SQLAlchemyInfrastructureUnitOfWork
    ) -> InfrastructureService:
        return InfrastructureService(infrastructure_uow)
