"""Application entry point"""
import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

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

