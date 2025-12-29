
from dishka import make_async_container

from api.application.di import (
    DatabaseProvider,
    OrchestratorProvider,
    ServiceProvider,
    UnitOfWorkProvider,
    CLIRunnerProvider,
    BatchProcessorProvider,
    IngestorProvider,
)


def create_container(context: dict):
    """Create DI container with all providers"""
    return make_async_container(
        DatabaseProvider(),
        UnitOfWorkProvider(),
        CLIRunnerProvider(),
        BatchProcessorProvider(),
        IngestorProvider(),
        ServiceProvider(),
        OrchestratorProvider(),
        context=context,
    )