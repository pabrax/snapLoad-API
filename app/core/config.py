"""
Configuración centralizada de la aplicación.
Este módulo contiene todas las configuraciones del proyecto.
"""
import os
from pathlib import Path
from typing import Set


class Settings:
    """Configuración centralizada de la aplicación."""
    
    # Directorios base
    BASE_DIR: Path = Path(__file__).resolve().parents[2]
    DOWNLOAD_DIR: Path = BASE_DIR / "downloads"
    LOGS_DIR: Path = BASE_DIR / "logs"
    META_DIR: Path = BASE_DIR / "meta"
    TMP_DIR: Path = BASE_DIR / "tmp"
    
    # Extensiones de archivos
    AUDIO_EXTENSIONS: Set[str] = {".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg"}
    VIDEO_EXTENSIONS: Set[str] = {".webm", ".mp4", ".mkv"}
    
    # Formatos válidos
    VALID_VIDEO_FORMATS: Set[str] = {"webm", "mp4", "mkv"}
    
    # Configuración de procesos
    JOB_TERMINATION_TIMEOUT: float = 5.0
    
    # Configuración de salida
    MAX_LOG_LINES: int = 200
    MAX_FILENAME_LENGTH: int = 150
    
    # API Info
    APP_TITLE: str = "SnapLoad API"
    APP_DESCRIPTION: str = "REST API for downloading media from YouTube and Spotify using yt-dlp and spotdl"
    APP_VERSION: str = "1.0.0"
    
    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "9020"))
    RELOAD: bool = os.getenv("RELOAD", "false").lower() == "true"
    WORKERS: int = int(os.getenv("WORKERS", "1"))
    
    # Binarios requeridos
    REQUIRED_BINARIES: dict = {
        "yt-dlp": "yt-dlp",
        "spotdl": "spotdl",
        "ffmpeg": "ffmpeg",
    }


class CleanupSettings:
    """Configuración del sistema de limpieza y optimización."""
    
    # Directorio de logs de limpieza
    CLEANUP_LOG_DIR: Path = Settings.BASE_DIR / "logs" / "cleanup"
    
    # Política de retención (en horas) - acepta decimales para testing
    RETENTION_HOURS: float = float(os.getenv("RETENTION_HOURS", "24"))
    TEMP_RETENTION_HOURS: float = float(os.getenv("TEMP_RETENTION_HOURS", "1"))
    
    # Programación automática
    CLEANUP_SCHEDULE_ENABLED: bool = os.getenv("CLEANUP_SCHEDULE_ENABLED", "true").lower() == "true"
    CLEANUP_CRON: str = os.getenv("CLEANUP_CRON", "0 */6 * * *")  # Cada 6 horas
    TEMP_CLEANUP_CRON: str = os.getenv("TEMP_CLEANUP_CRON", "0 * * * *")  # Cada hora
    
    # Endpoints admin (solo en desarrollo/testing)
    ENABLE_ADMIN_ENDPOINTS: bool = os.getenv("ENABLE_ADMIN_ENDPOINTS", "false").lower() == "true"
    
    # Logging
    CLEANUP_LOG_LEVEL: str = os.getenv("CLEANUP_LOG_LEVEL", "INFO")
    CLEANUP_LOG_RETENTION_DAYS: int = int(os.getenv("CLEANUP_LOG_RETENTION_DAYS", "7"))
    
    # Dry-run para testing
    CLEANUP_DRY_RUN: bool = os.getenv("CLEANUP_DRY_RUN", "false").lower() == "true"


settings = Settings()
cleanup_settings = CleanupSettings()
