"""Application entry point"""
from pathlib import Path
import sys
import uvicorn
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
    
if __name__ == "__main__":
    from api.presentation.rest.app import create_app
    from api.config import settings

    app = create_app()
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
    )

