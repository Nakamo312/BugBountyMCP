
from dishka import make_async_container

from api.application.di import (DatabaseProvider,
                                    ServiceProvider, UnitOfWorkProvider, CLIRunnerProvider,IngestorProvider)


def create_container(context: dict):
    """Create DI container with all providers"""
    return make_async_container(
        DatabaseProvider(),
        UnitOfWorkProvider(),
        CLIRunnerProvider(),
        IngestorProvider(),
        ServiceProvider(),
        context=context,
    )