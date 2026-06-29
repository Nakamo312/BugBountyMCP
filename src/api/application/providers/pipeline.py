from dishka import AsyncContainer, Provider, Scope, from_context, provide

from api.application.pipeline.registry import NodeRegistry
from api.config import Settings
from api.infrastructure.events.event_bus import EventBus


class PipelineProvider(Provider):
    scope = Scope.APP
    settings = from_context(provides=Settings)

    @provide(scope=Scope.APP)
    def get_node_registry(
        self,
        bus: EventBus,
        settings: Settings,
        container: AsyncContainer,
    ) -> NodeRegistry:
        return NodeRegistry(bus, settings, container)
