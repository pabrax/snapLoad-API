"""
Scheduler para limpieza automática del servidor.
Usa APScheduler para ejecutar tareas de limpieza en background.
"""
import logging
import sys
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED

from ..core.config import cleanup_settings
from ..services.cleanup_service import cleanup_service


class CleanupScheduler:
    """
    Programador de tareas de limpieza automática.
    Ejecuta limpiezas periódicas según configuración.
    """
    
    def __init__(self):
        # Configurar scheduler para no perder ejecuciones y mejor manejo de jobs perdidos
        self.scheduler = BackgroundScheduler(
            job_defaults={
                'coalesce': True,  # Combinar ejecuciones perdidas en una sola
                'max_instances': 1,  # Solo una instancia del job a la vez
                'misfire_grace_time': 300  # 5 minutos de gracia para ejecuciones perdidas
            }
        )
        self.logger = logging.getLogger("cleanup_scheduler")
        self._setup_logger()
        self._started = False
    
    def _setup_logger(self):
        """Configura el logger del scheduler para escribir en archivos."""
        # Solo configurar si no tiene handlers ya
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            
            # Handler de consola
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '[%(asctime)s] [SCHEDULER] %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
            # Evitar propagación duplicada
            self.logger.propagate = False
    
    def start(self) -> None:
        """Inicia el scheduler si está habilitado."""
        if not cleanup_settings.CLEANUP_SCHEDULE_ENABLED:
            self.logger.info("Cleanup scheduler disabled by configuration")
            return
        
        if self._started:
            self.logger.warning("Cleanup scheduler already started")
            return
        
        try:
            # Programar limpieza general
            self.scheduler.add_job(
                func=self._run_cleanup,
                trigger=CronTrigger.from_crontab(cleanup_settings.CLEANUP_CRON),
                id='cleanup_all',
                name='Cleanup All',
                replace_existing=True,
                max_instances=1,
                coalesce=True
            )
            self.logger.info(f"Scheduled cleanup_all with cron: {cleanup_settings.CLEANUP_CRON}")
            
            # Programar limpieza de temporales (más frecuente)
            self.scheduler.add_job(
                func=self._run_temp_cleanup,
                trigger=CronTrigger.from_crontab(cleanup_settings.TEMP_CLEANUP_CRON),
                id='cleanup_temp',
                name='Cleanup Temp',
                replace_existing=True,
                max_instances=1,
                coalesce=True
            )
            self.logger.info(f"Scheduled cleanup_temp with cron: {cleanup_settings.TEMP_CLEANUP_CRON}")
            
            # Iniciar scheduler
            self.scheduler.start()
            self._started = True
            
            # Agregar listeners para eventos
            self.scheduler.add_listener(self._job_executed, EVENT_JOB_EXECUTED)
            self.scheduler.add_listener(self._job_error, EVENT_JOB_ERROR)
            self.scheduler.add_listener(self._job_missed, EVENT_JOB_MISSED)
            
            self.logger.info("Cleanup scheduler started successfully")
            
        except Exception as e:
            self.logger.error(f"Error starting cleanup scheduler: {str(e)}")
            raise
    
    def stop(self) -> None:
        """Detiene el scheduler."""
        if not self._started:
            return
        
        try:
            self.scheduler.shutdown(wait=True)
            self._started = False
            self.logger.info("Cleanup scheduler stopped")
        except Exception as e:
            self.logger.error(f"Error stopping cleanup scheduler: {str(e)}")
    
    def _run_cleanup(self) -> None:
        """Ejecuta limpieza completa (llamada por scheduler)."""
        try:
            self.logger.info("Starting scheduled cleanup (all targets)")
            
            summary = cleanup_service.cleanup_all(
                strategy="age_based",
                dry_run=False
            )
            
            self.logger.info(
                f"Scheduled cleanup completed: "
                f"{summary.total_files_deleted} files deleted, "
                f"{summary.total_space_freed_mb} MB freed"
            )
            
        except Exception as e:
            self.logger.error(f"Error in scheduled cleanup: {str(e)}", exc_info=True)
    
    def _run_temp_cleanup(self) -> None:
        """Ejecuta limpieza de temporales (llamada por scheduler)."""
        try:
            self.logger.info("Starting scheduled temp cleanup")
            
            stats = cleanup_service.cleanup_temp(dry_run=False)
            
            self.logger.info(
                f"Scheduled temp cleanup completed: "
                f"{stats.files_deleted} items deleted, "
                f"{stats.space_freed_mb} MB freed"
            )
            
        except Exception as e:
            self.logger.error(f"Error in scheduled temp cleanup: {str(e)}", exc_info=True)
    
    def _job_executed(self, event):
        """Callback cuando un job se ejecuta exitosamente."""
        self.logger.info(f"Job '{event.job_id}' executed successfully")
    
    def _job_error(self, event):
        """Callback cuando un job falla."""
        self.logger.error(f"Job '{event.job_id}' raised an error: {event.exception}")
    
    def _job_missed(self, event):
        """Callback cuando un job se pierde."""
        self.logger.warning(
            f"Job '{event.job_id}' was missed! "
            f"Scheduled for {event.scheduled_run_time}, "
            f"but run at {event.job_id}"
        )
    
    def get_jobs(self) -> list:
        """
        Obtiene información de los jobs programados.
        
        Returns:
            Lista con información de jobs
        """
        if not self._started:
            return []
        
        jobs_info = []
        for job in self.scheduler.get_jobs():
            jobs_info.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        
        return jobs_info


# Instancia global del scheduler
cleanup_scheduler = CleanupScheduler()
