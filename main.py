"""Application entry point"""
import uvicorn
from api.presentation.rest.app import create_app
from api.config import settings

if __name__ == "__main__":
    app = create_app()
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
    )

