"""
Endpoints administrativos para limpieza y monitoreo.
Solo disponibles cuando ENABLE_ADMIN_ENDPOINTS=true (desarrollo/testing).
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List

from ..core.config import cleanup_settings
from ..schemas import (
    CleanupRequest,
    CleanupSummary,
    CleanupStats,
    StorageStats
)
from ..services.cleanup_service import cleanup_service
from ..managers.cleanup_scheduler import cleanup_scheduler


router = APIRouter(prefix="/admin", tags=["admin"])


def check_admin_enabled():
    """Dependency para verificar si endpoints admin están habilitados."""
    if not cleanup_settings.ENABLE_ADMIN_ENDPOINTS:
        raise HTTPException(
            status_code=404,
            detail="Admin endpoints are disabled. Set ENABLE_ADMIN_ENDPOINTS=true to enable."
        )


@router.post("/cleanup/trigger", response_model=CleanupSummary, dependencies=[Depends(check_admin_enabled)])
async def trigger_cleanup(request: CleanupRequest):
    """
    Trigger manual de limpieza.
    
    Solo disponible en desarrollo/testing.
    Permite ejecutar limpieza manualmente con diferentes configuraciones.
    
    Args:
        request: Configuración de limpieza
        
    Returns:
        CleanupSummary con resultados
    """
    try:
        if "all" in request.targets or len(request.targets) == 0:
            # Limpieza completa
            summary = cleanup_service.cleanup_all(
                strategy=request.strategy,
                dry_run=request.dry_run
            )
        else:
            # Limpieza de targets específicos
            from ..helpers import DateTimeHelper
            import time
            
            start_time = time.time()
            targets_cleaned = []
            total_files = 0
            total_space = 0.0
            errors = []
            
            for target in request.targets:
                try:
                    if target == "downloads":
                        stats = cleanup_service.cleanup_downloads(
                            request.strategy, request.dry_run
                        )
                    elif target == "logs":
                        stats = cleanup_service.cleanup_logs(
                            cleanup_settings.RETENTION_HOURS, request.dry_run
                        )
                    elif target == "metadata":
                        stats = cleanup_service.cleanup_metadata(
                            cleanup_settings.RETENTION_HOURS, request.dry_run
                        )
                    elif target == "temp":
                        stats = cleanup_service.cleanup_temp(request.dry_run)
                    elif target == "database":
                        stats = cleanup_service.cleanup_database(
                            cleanup_settings.RETENTION_HOURS, request.dry_run
                        )
                    else:
                        errors.append(f"Unknown target: {target}")
                        continue
                    
                    targets_cleaned.append(stats)
                    total_files += stats.files_deleted
                    total_space += stats.space_freed_mb
                except Exception as e:
                    errors.append(f"Error in {target}: {str(e)}")
            
            summary = CleanupSummary(
                total_files_deleted=total_files,
                total_space_freed_mb=round(total_space, 2),
                targets_cleaned=targets_cleaned,
                errors=errors,
                timestamp=DateTimeHelper.now_iso(),
                duration_seconds=round(time.time() - start_time, 2),
                dry_run=request.dry_run
            )
        
        return summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.get("/storage/stats", response_model=StorageStats, dependencies=[Depends(check_admin_enabled)])
async def get_storage_stats():
    """
    Obtiene estadísticas de almacenamiento del servidor.
    
    Solo disponible en desarrollo/testing.
    Muestra el uso actual de espacio en disco.
    
    Returns:
        StorageStats con información de almacenamiento
    """
    try:
        stats = cleanup_service.get_storage_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/cleanup/schedule", dependencies=[Depends(check_admin_enabled)])
async def get_cleanup_schedule():
    """
    Obtiene información de las tareas programadas.
    
    Solo disponible en desarrollo/testing.
    
    Returns:
        Información de los jobs de limpieza programados
    """
    try:
        jobs = cleanup_scheduler.get_jobs()
        return {
            "enabled": cleanup_settings.CLEANUP_SCHEDULE_ENABLED,
            "retention_hours": cleanup_settings.RETENTION_HOURS,
            "temp_retention_hours": cleanup_settings.TEMP_RETENTION_HOURS,
            "cleanup_cron": cleanup_settings.CLEANUP_CRON,
            "temp_cleanup_cron": cleanup_settings.TEMP_CLEANUP_CRON,
            "jobs": jobs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get schedule: {str(e)}")


@router.get("/cleanup/config", dependencies=[Depends(check_admin_enabled)])
async def get_cleanup_config():
    """
    Obtiene la configuración actual de limpieza.
    
    Solo disponible en desarrollo/testing.
    
    Returns:
        Configuración de limpieza
    """
    return {
        "retention_hours": cleanup_settings.RETENTION_HOURS,
        "temp_retention_hours": cleanup_settings.TEMP_RETENTION_HOURS,
        "schedule_enabled": cleanup_settings.CLEANUP_SCHEDULE_ENABLED,
        "cleanup_cron": cleanup_settings.CLEANUP_CRON,
        "temp_cleanup_cron": cleanup_settings.TEMP_CLEANUP_CRON,
        "dry_run": cleanup_settings.CLEANUP_DRY_RUN,
        "log_level": cleanup_settings.CLEANUP_LOG_LEVEL,
        "log_retention_days": cleanup_settings.CLEANUP_LOG_RETENTION_DAYS,
    }
