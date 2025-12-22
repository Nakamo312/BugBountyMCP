
from dishka import make_async_container

from src.api.application.di import (DatabaseProvider, RepositoryProvider,
                                    ServiceProvider, UnitOfWorkProvider)


def create_container(context: dict):
    """Create DI container with all providers"""
    return make_async_container(
        DatabaseProvider(),
        RepositoryProvider(),
        UnitOfWorkProvider(),
        ServiceProvider(),
        context=context,
    )