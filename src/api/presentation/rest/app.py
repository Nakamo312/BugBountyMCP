"""FastAPI application with DI setup"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dishka.integrations.fastapi import DishkaRoute, setup_dishka

from ...application.container import create_container
from ...application.di import AsyncContainer
from .middleware import db_session_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Create container on startup
    container = create_container()
    app.state.dishka_container = container
    
    # Setup dishka
    setup_dishka(container, app)
    
    yield
    
    # Cleanup on shutdown
    await container.close()


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(
        title="Bug Bounty Framework API",
        description="Bug Bounty Reconnaissance Framework",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # Add database session middleware
    app.middleware("http")(db_session_middleware)
    
    return app

