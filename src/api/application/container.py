"""Dependency Injection container setup"""
from dishka import make_async_container, AsyncContainer

from ..config import Settings, settings
from .di import DatabaseProvider, RepositoryProvider, ServiceProvider


def create_container(context: dict = None) -> AsyncContainer:
    return make_async_container(
        DatabaseProvider(),
        RepositoryProvider(),
        ServiceProvider(),
        context=context,
    )

