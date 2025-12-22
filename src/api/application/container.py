
from dishka import make_async_container

from src.api.application.di import (DatabaseProvider,
                                    ServiceProvider, UnitOfWorkProvider)


def create_container(context: dict):
    """Create DI container with all providers"""
    return make_async_container(
        DatabaseProvider(),
        UnitOfWorkProvider(),
        ServiceProvider(),
        context=context,
    )