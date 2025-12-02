"""
Aplicación FastAPI principal.
Define la app y configura los routers y lifecycle hooks.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .core.config import settings, cleanup_settings
from .routes.health import router as health_router
from .routes.download import router as download_router
from .routes.files import router as files_router

# Configurar logger
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestión del ciclo de vida de la aplicación.
    Startup: Inicia el scheduler de limpieza
    Shutdown: Detiene el scheduler y termina jobs
    """
    logger.info("Starting application...")
    
    # Iniciar scheduler de limpieza
    if cleanup_settings.CLEANUP_SCHEDULE_ENABLED:
        try:
            from .managers.cleanup_scheduler import cleanup_scheduler
            cleanup_scheduler.start()
            logger.info("Cleanup scheduler started")
        except Exception as e:
            logger.error(f"Failed to start cleanup scheduler: {str(e)}")
    
    yield
    
    logger.info("Shutting down application...")
    
    # Detener scheduler
    try:
        from .managers.cleanup_scheduler import cleanup_scheduler
        cleanup_scheduler.stop()
        logger.info("Cleanup scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping cleanup scheduler: {str(e)}")
    
    # Terminar jobs activos
    try:
        from .managers import job_manager
        job_manager.terminate_all()
        logger.info("All jobs terminated")
    except Exception as e:
        logger.error(f"Error terminating jobs: {str(e)}")


# Crear aplicación con lifespan
app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Incluir routers principales
app.include_router(health_router)
app.include_router(download_router)
app.include_router(files_router)

# Incluir admin router solo si está habilitado
if cleanup_settings.ENABLE_ADMIN_ENDPOINTS:
    from .routes.admin import router as admin_router
    app.include_router(admin_router)
    logger.info("Admin endpoints enabled (development mode)")
