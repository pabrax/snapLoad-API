"""
Gestor de jobs de descarga.
Mantiene un registro de procesos en ejecución y permite su gestión.
"""
import threading
from typing import Optional, Dict, Set
from subprocess import Popen

from ..core.config import settings
from ..core.process import terminate_process


class JobManager:
    """
    Gestor centralizado de jobs de descarga.
    Implementa el patrón Singleton para mantener un registro único de procesos.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Implementación del patrón Singleton."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Inicializa el gestor de jobs."""
        if self._initialized:
            return
        
        self._registry: Dict[str, Popen] = {}
        self._cancelled: Set[str] = set()
        self._initialized = True
    
    def register_job(self, job_id: str, process: Popen) -> None:
        """
        Registra un proceso de descarga.
        
        Args:
            job_id: Identificador único del job
            process: Proceso Popen asociado
        """
        with self._lock:
            self._registry[job_id] = process
    
    def unregister_job(self, job_id: str) -> None:
        """
        Elimina un job del registro.
        
        Args:
            job_id: Identificador del job a eliminar
        """
        with self._lock:
            self._registry.pop(job_id, None)
    
    def get_job_process(self, job_id: str) -> Optional[Popen]:
        """
        Obtiene el proceso asociado a un job.
        
        Args:
            job_id: Identificador del job
            
        Returns:
            Proceso Popen o None si no existe
        """
        with self._lock:
            return self._registry.get(job_id)
    
    def has_job(self, job_id: str) -> bool:
        """
        Verifica si un job está registrado.
        
        Args:
            job_id: Identificador del job
            
        Returns:
            True si el job existe
        """
        with self._lock:
            return job_id in self._registry
    
    def terminate_job(self, job_id: str, timeout: float = None) -> bool:
        """
        Intenta terminar un proceso de forma controlada.
        
        Args:
            job_id: Identificador del job a terminar
            timeout: Tiempo de espera en segundos (default desde settings)
            
        Returns:
            True si se envió la señal de terminación
        """
        if timeout is None:
            timeout = settings.JOB_TERMINATION_TIMEOUT
        
        process = self.get_job_process(job_id)
        if not process:
            return False

        with self._lock:
            self._cancelled.add(job_id)

        try:
            terminate_process(process, timeout=timeout)
        finally:
            self.unregister_job(job_id)
        
        return True
    
    def consume_cancelled(self, job_id: str) -> bool:
        """
        Indica si el job fue terminado a propósito (cancelación o apagado) y borra la marca.

        Args:
            job_id: Identificador del job

        Returns:
            True si se había solicitado su terminación
        """
        with self._lock:
            if job_id in self._cancelled:
                self._cancelled.discard(job_id)
                return True
            return False

    def terminate_all(self) -> None:
        """Termina todos los jobs registrados de forma ordenada."""
        with self._lock:
            job_ids = list(self._registry.keys())
        
        for job_id in job_ids:
            try:
                self.terminate_job(job_id)
            except Exception:
                # Continuar con otros jobs incluso si uno falla
                pass
    
    def get_active_jobs(self) -> list:
        """
        Obtiene la lista de jobs activos.
        
        Returns:
            Lista de job_ids activos
        """
        with self._lock:
            return list(self._registry.keys())
    
    def count_active_jobs(self) -> int:
        """
        Cuenta el número de jobs activos.
        
        Returns:
            Número de jobs en ejecución
        """
        with self._lock:
            return len(self._registry)


# Instancia global del gestor
job_manager = JobManager()
