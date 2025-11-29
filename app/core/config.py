"""
Configuración centralizada de la aplicación.
Este módulo contiene todas las configuraciones del proyecto.
"""
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
    VIDEO_EXTENSIONS: Set[str] = {".webm", ".mp4", ".mkv", ".mov", ".avi"}
    
    # Formatos válidos
    VALID_VIDEO_FORMATS: Set[str] = {"webm", "mp4", "mkv", "mov", "avi"}
    
    # Configuración de procesos
    JOB_TERMINATION_TIMEOUT: float = 5.0
    
    # Configuración de salida
    MAX_LOG_LINES: int = 200
    MAX_FILENAME_LENGTH: int = 150
    
    # API Info
    APP_TITLE: str = "SnapLoad API"
    APP_DESCRIPTION: str = "REST API for downloading media from YouTube and Spotify using yt-dlp and spotdl"
    APP_VERSION: str = "1.0.0"
    
    # Binarios requeridos
    REQUIRED_BINARIES: dict = {
        "yt-dlp": "yt-dlp",
        "spotdl": "spotdl",
        "ffmpeg": "ffmpeg",
    }


settings = Settings()
