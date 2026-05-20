
from dishka import make_async_container

from api.application.di import (
    DatabaseProvider,
    OrchestrationProvider,
    ServiceProvider,
    UnitOfWorkProvider,
    CLIRunnerProvider,
    BatchProcessorProvider,
    IngestorProvider,
    PipelineProvider,
)


def create_container(context: dict):
    return make_async_container(
        DatabaseProvider(),
        OrchestrationProvider(),
        UnitOfWorkProvider(),
        CLIRunnerProvider(),
        BatchProcessorProvider(),
        IngestorProvider(),
        ServiceProvider(),
        PipelineProvider(),
        context=context,
    )
