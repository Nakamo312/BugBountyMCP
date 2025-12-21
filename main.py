"""FastAPI application entry point"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dishka.integrations.fastapi import setup_dishka

from src.api.config import Settings
from src.api.application.container import create_container
from src.api.presentation.rest.routes import router
from src.api.presentation.rest.handlers import (
    tool_not_found_handler, 
    scan_execution_handler,
    global_exception_handler
)
from src.api.application.exceptions import ToolNotFoundError, ScanExecutionError

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if hasattr(app.state, "dishka_container"):
        await app.state.dishka_container.close()

def create_app() -> FastAPI:
    settings = Settings()
    # Create DI Container
    container = create_container(context={Settings: settings})
    
    app = FastAPI(
        title="Bug Bounty Framework API",
        version="1.0.0",
        description="API for automating reconnaissance tools (Subfinder, HTTPX, etc.)",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    
    app.add_exception_handler(ToolNotFoundError, tool_not_found_handler)
    app.add_exception_handler(ScanExecutionError, scan_execution_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    
    setup_dishka(container, app)
    app.include_router(router)
    
    return app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:create_app", factory=True, host="0.0.0.0", port=8000, reload=True)