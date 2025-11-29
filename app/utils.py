"""
Módulo de utilidades (compatibilidad hacia atrás).
Este módulo re-exporta funciones de los nuevos módulos para mantener compatibilidad.
Para nuevo código, importar directamente desde helpers, validators, o core.config.
"""
from pathlib import Path

# Re-exportar desde los nuevos módulos
from .core.config import settings
from .helpers import (
    DateTimeHelper,
    FileNameHelper,
    FileSystemHelper,
)
from .validators import (
    URLValidator,
    QualityValidator,
    FormatValidator,
)

# Compatibilidad hacia atrás - constantes
AUDIO_EXTS = settings.AUDIO_EXTENSIONS
BASE_DIR = settings.BASE_DIR
DOWNLOAD_DIR = settings.DOWNLOAD_DIR

# Compatibilidad hacia atrás - funciones
def now_iso():
    """Retorna la fecha/hora actual en formato ISO."""
    return DateTimeHelper.now_iso()

def sanitize_filename(name: str, max_length: int = 150) -> str:
    """Sanitiza un nombre de fichero."""
    return FileNameHelper.sanitize_filename(name, max_length)

def sanitize_filename_ascii(name: str, max_length: int = 150) -> str:
    """Genera una variante ASCII del nombre."""
    return FileNameHelper.sanitize_filename_ascii(name, max_length)

def is_spotify_url(url: str) -> bool:
    """Comprueba si la URL/URI es de Spotify."""
    return URLValidator.is_spotify_url(url)

def list_audio_files(folder: Path):
    """Devuelve una lista de ficheros de audio en la carpeta."""
    return FileSystemHelper.list_audio_files(folder)

def is_youtube_url(url: str) -> bool:
    """Comprueba si la URL corresponde a YouTube."""
    return URLValidator.is_youtube_url(url)

def is_valid_bitrate(value: str) -> bool:
    """Valida un valor de bitrate/quality."""
    return QualityValidator.is_valid_bitrate(value)

def is_valid_video_format(fmt: str) -> bool:
    """Valida formato de contenedor de video."""
    return FormatValidator.is_valid_video_format(fmt)

def normalize_quality(value: str) -> dict:
    """Normaliza un valor de quality para spotdl y yt-dlp."""
    return QualityValidator.normalize_quality(value)