"""Dependency Injection container setup"""
from dishka import make_async_container, AsyncContainer

from ..config import Settings, settings
from .di import DatabaseProvider, RepositoryProvider, ServiceProvider


def create_container(custom_settings: Settings | None = None) -> AsyncContainer:
    """
    Create and configure DI container.
    
    Args:
        custom_settings: Optional custom settings (for testing)
        
    Returns:
        Configured async container
    """
    app_settings = custom_settings or settings
    
    container = make_async_container(
        DatabaseProvider(),
        RepositoryProvider(),
        ServiceProvider(),
        context={
            Settings: app_settings,
        },
    )
    
    return container

