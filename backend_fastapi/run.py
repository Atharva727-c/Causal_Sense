import uvicorn
from app.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.host,
        port=s.port,
        reload=s.debug,
        workers=1,
        log_level="debug" if s.debug else "info",
    )
