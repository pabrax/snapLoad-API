"""
Registro de jobs (compatibilidad hacia atrás).
Este módulo re-exporta desde managers.job_manager para mantener compatibilidad.
Para nuevo código, importar directamente desde managers.
"""
from .managers.job_manager import (
    register_job,
    unregister_job,
    get_job_proc,
    terminate_job,
    terminate_all,
    job_manager,
)

__all__ = [
    "register_job",
    "unregister_job",
    "get_job_proc",
    "terminate_job",
    "terminate_all",
    "job_manager",
]
