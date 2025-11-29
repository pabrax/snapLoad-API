"""
Índice de descargas (compatibilidad hacia atrás).
Este módulo re-exporta desde repositories para mantener compatibilidad.
Para nuevo código, importar directamente desde repositories.
"""
from ..repositories import download_index_repo

# Crear clase wrapper para mantener compatibilidad con la API anterior
class DownloadIndex:
    """Wrapper de compatibilidad para DownloadIndexRepository."""
    
    def __init__(self):
        self._repo = download_index_repo
    
    def ensure_schema(self):
        """Asegura que el esquema existe."""
        self._repo.ensure_schema()
    
    def lookup(self, url: str, type_: str, quality=None, format_=None):
        """Busca una descarga en el índice."""
        result = self._repo.lookup(url, type_, quality, format_)
        if result:
            return result.dict()
        return None
    
    def register_pending(self, url: str, type_: str, quality, format_, job_id: str, created_at: str):
        """Registra una descarga pendiente."""
        self._repo.register_pending(url, type_, quality, format_, job_id, created_at)
    
    def register_success(self, job_id: str, files: list):
        """Marca un job como exitoso."""
        self._repo.register_success(job_id, files)
    
    def register_failed(self, job_id: str, error: str):
        """Marca un job como fallido."""
        self._repo.register_failed(job_id, error)
    
    def touch(self, url: str, type_: str, quality, format_, last_access: str):
        """Actualiza el timestamp de último acceso."""
        self._repo.touch(url, type_, quality, format_, last_access)
    
    def upsert_ready(self, url: str, type_: str, quality, format_, files: list, created_at: str, job_id=None):
        """Inserta o actualiza una entrada como lista."""
        self._repo.upsert_ready(url, type_, quality, format_, files, created_at, job_id)


download_index = DownloadIndex()

