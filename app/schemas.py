"""
Modelos de datos de la aplicación.
Define los esquemas de entrada/salida y modelos de dominio.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime

from .core.enums import JobStatus, MediaType, DownloadSource


# === Request Models ===

class DownloadRequest(BaseModel):
    """Modelo de solicitud para descargar audio."""
    url: str = Field(..., description="URL del contenido a descargar")
    quality: Optional[str] = Field(
        None, 
        description="Calidad del audio (ej: '320k', '192k', '0')",
        example="320k"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://open.spotify.com/track/...",
                "quality": "320k"
            }
        }


class VideoDownloadRequest(BaseModel):
    """Modelo de solicitud para descargar video."""
    url: str = Field(..., description="URL del video a descargar")
    format: Optional[str] = Field(
        None,
        description="Formato del contenedor de video (webm, mp4, mkv, mov, avi)",
        example="webm"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.youtube.com/watch?v=...",
                "format": "webm"
            }
        }


# === Response Models ===

class FileInfo(BaseModel):
    """Información de un archivo descargado."""
    name: str = Field(..., description="Nombre del archivo")
    path: str = Field(..., description="Ruta completa del archivo")
    size_bytes: int = Field(..., description="Tamaño del archivo en bytes")


class DownloadResponse(BaseModel):
    """Respuesta estándar para operaciones de descarga."""
    message: str = Field(..., description="Mensaje descriptivo")
    job_id: Optional[str] = Field(None, description="ID del job de descarga")
    url: str = Field(..., description="URL solicitada")
    source: Optional[str] = Field(None, description="Fuente de la descarga")
    status: Optional[str] = Field(None, description="Estado del job")
    files: Optional[List[str]] = Field(None, description="Lista de archivos resultantes")
    quality: Optional[str] = Field(None, description="Calidad solicitada")
    format: Optional[str] = Field(None, description="Formato solicitado")


class LookupResponse(BaseModel):
    """Respuesta para consultas de cache/lookup."""
    status: str = Field(..., description="Estado: ready, pending, miss")
    job_id: Optional[str] = Field(None, description="ID del job si existe")
    url: str = Field(..., description="URL consultada")
    type: str = Field(..., description="Tipo de media: audio o video")
    files: Optional[List[str]] = Field(None, description="Archivos disponibles si status=ready")
    quality: Optional[str] = Field(None, description="Calidad")
    format: Optional[str] = Field(None, description="Formato")


class JobStatusResponse(BaseModel):
    """Respuesta para consultas de estado de job."""
    job_id: str = Field(..., description="ID del job")
    status: str = Field(..., description="Estado del job")
    files: Optional[List[str]] = Field(None, description="Archivos producidos")
    error: Optional[str] = Field(None, description="Mensaje de error si falló")


class HealthResponse(BaseModel):
    """Respuesta del health check."""
    status: str = Field(..., description="Estado general: ok o degraded")
    binaries: dict = Field(..., description="Estado de binarios requeridos")


class BinaryInfo(BaseModel):
    """Información de un binario externo."""
    installed: bool = Field(..., description="Si el binario está disponible")
    path: Optional[str] = Field(None, description="Ruta del binario")


class FileListResponse(BaseModel):
    """Respuesta con lista de archivos."""
    job_id: str = Field(..., description="ID del job")
    files: List[dict] = Field(..., description="Lista de archivos con metadatos")


class CancelResponse(BaseModel):
    """Respuesta para cancelación de jobs."""
    job_id: str = Field(..., description="ID del job")
    cancelled: bool = Field(..., description="Si se canceló exitosamente")
    status: Optional[str] = Field(None, description="Estado actual del job")


# === Domain Models ===

class JobMetadata(BaseModel):
    """Metadata completa de un job de descarga."""
    job_id: str
    url: str
    type: str
    source_id: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: str
    files: List[FileInfo] = []
    log_path: str
    error: Optional[str] = None
    inferred_from_filenames: bool = False
    raw_spotdl_summary: Optional[str] = None
    raw_yt_summary: Optional[str] = None


class MediaInfo(BaseModel):
    """Información de un archivo de media en el catálogo."""
    hash: str
    path: str
    quality: Optional[str] = None
    format: Optional[str] = None
    display_name: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: Optional[str] = None


class DownloadIndexEntry(BaseModel):
    """Entrada en el índice de descargas."""
    url: str
    type: str
    quality: Optional[str] = None
    format: Optional[str] = None
    files: List[str] = []
    status: str
    job_id: Optional[str] = None
    created_at: str
    last_access: Optional[str] = None
    error: Optional[str] = None


# === Internal Models ===

class QualityConfig(BaseModel):
    """Configuración normalizada de calidad para diferentes servicios."""
    spotdl: Optional[str] = None
    ytdlp: Optional[str] = None


class DownloadJob(BaseModel):
    """Modelo interno para un job de descarga."""
    job_id: str
    url: str
    media_type: MediaType
    source: DownloadSource
    quality: Optional[str] = None
    format: Optional[str] = None
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
