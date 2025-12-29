"""Application entry point"""
import logging
import sys
from pathlib import Path

# Setup logging
def setup_logging(level: str = "INFO"):
    """Configure application logging"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('app.log')
        ]
    )

# Add src to path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
    
if __name__ == "__main__":
    import uvicorn
    from api.presentation.rest.app import create_app
    from api.config import Settings

    settings = Settings()
    # Setup logging
    setup_logging(settings.LOG_LEVEL)
    logger = logging.getLogger(__name__)
    logger.info(f"Starting Bug Bounty Framework API on {settings.API_HOST}:{settings.API_PORT}")

    app = create_app()
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
