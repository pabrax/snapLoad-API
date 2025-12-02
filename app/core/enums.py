"""
Enumeraciones utilizadas en la aplicación.
Centraliza los estados y tipos para evitar strings mágicos.
"""
from enum import Enum


class JobStatus(str, Enum):
    """Estados posibles de un job de descarga."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUEUED = "queued"
    READY = "ready"
    UNKNOWN = "unknown"


class MediaType(str, Enum):
    """Tipos de media que se pueden descargar."""
    AUDIO = "audio"
    VIDEO = "video"


class DownloadSource(str, Enum):
    """Fuentes de descarga soportadas."""
    SPOTIFY = "spotify"
    YOUTUBE = "youtube"
    YOUTUBE_AUDIO = "youtube_audio"
    YOUTUBE_VIDEO = "youtube_video"


class CacheStatus(str, Enum):
    """Estados de cache."""
    HIT = "ready"
    MISS = "miss"
    PENDING = "pending"


class CleanupTarget(str, Enum):
    """Objetivos de limpieza."""
    DOWNLOADS = "downloads"
    LOGS = "logs"
    METADATA = "metadata"
    TEMP = "temp"
    DATABASE = "database"
    ALL = "all"


class CleanupStrategy(str, Enum):
    """Estrategias de limpieza."""
    AGE_BASED = "age_based"
    ORPHAN = "orphan"
