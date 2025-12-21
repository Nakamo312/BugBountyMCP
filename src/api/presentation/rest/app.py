"""FastAPI application with DI setup"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dishka.integrations.fastapi import setup_dishka
from starlette.middleware.base import BaseHTTPMiddleware

from api.config import Settings

from ...application.container import create_container
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    yield
    container = app.state.dishka_container
    await container.close()


def create_app() -> FastAPI:
    settings = Settings() 
    
    container = create_container(context={Settings: settings})
    
    app = FastAPI(
        title="Bug Bounty Framework API",
        lifespan=lifespan,
    )
    
    setup_dishka(container, app)
    
    app.include_router(router)
    return app