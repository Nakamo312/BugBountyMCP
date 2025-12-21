"""FastAPI application with DI setup"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dishka.integrations.fastapi import DishkaRoute, setup_dishka
from starlette.middleware.base import BaseHTTPMiddleware

from ...application.container import create_container
from .middleware import db_session_middleware
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Container is already created and setup_dishka is already called
    yield
    
    # Cleanup on shutdown
    container = app.state.dishka_container
    await container.close()


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    # Create container before app creation
    container = create_container()
    
    app = FastAPI(
        title="Bug Bounty Framework API",
        description="Bug Bounty Reconnaissance Framework",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # Store container in app state
    app.state.dishka_container = container
    
    # Add database session middleware FIRST
    # Due to LIFO stack, this runs AFTER ContainerMiddleware
    # It wraps the request container created by ContainerMiddleware with session context
    app.middleware("http")(db_session_middleware)
    
    # Setup dishka AFTER adding session middleware
    # ContainerMiddleware creates request scope, then our middleware wraps it with session
    setup_dishka(container, app)
    
    # Include routes
    app.include_router(router)
    
    return app

