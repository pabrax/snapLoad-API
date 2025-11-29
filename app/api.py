"""
Aplicación FastAPI principal.
Define la app y configura los routers y lifecycle hooks.
"""
from fastapi import FastAPI

from .core.config import settings
from .routes.health import router as health_router
from .routes.download import router as download_router
from .routes.files import router as files_router

# Crear aplicación
app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION
)

# Incluir routers
app.include_router(health_router)
app.include_router(download_router)
app.include_router(files_router)


@app.on_event("shutdown")
def on_shutdown():
    """Termina todos los jobs al cerrar la aplicación."""
    try:
        from .managers import job_manager
        job_manager.terminate_all()
    except Exception:
        pass

