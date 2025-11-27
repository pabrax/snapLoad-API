from fastapi import FastAPI

from .routes.health import router as health_router
from .routes.download import router as download_router
from .routes.files import router as files_router

app = FastAPI(
    title="CCAPI",
    description="API para descargar música y videos de Spotify usando spotdl y youtube utilizando yt-dlp",
    version="1.1.0"
)

## Include routers

app.include_router(health_router)
app.include_router(download_router)
app.include_router(files_router)


@app.on_event("shutdown")
def _on_shutdown():
    # try to terminate all running jobs gracefully
    try:
        from .job_registry import terminate_all

        terminate_all()
    except Exception:
        pass
