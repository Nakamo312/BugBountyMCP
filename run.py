"""Alternative entry point that sets up PYTHONPATH correctly"""
import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Now import and run
if __name__ == "__main__":
    import uvicorn
    from api.presentation.rest.app import create_app
    from api.config import settings
    
    app = create_app()
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
    )

