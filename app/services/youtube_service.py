"""
Servicio de descarga de YouTube.
Implementa la descarga de audio y video desde YouTube usando yt-dlp.
"""
from pathlib import Path
from typing import List

from .base_download_service import BaseDownloadService
from ..core.enums import MediaType
from ..core.config import settings
from ..core.constants import (
    YTDLP_AUDIO_EXTRACT_FORMAT,
    YTDLP_BEST_VIDEO_FORMAT,
    DEFAULT_VIDEO_FORMAT,
    VIDEO_FORMAT_INFO,
    ALLOWED_VIDEO_FORMATS,
)
from ..core.exceptions import InvalidURLException
from ..validators import URLValidator


class YouTubeAudioService(BaseDownloadService):
    """Servicio para descargar audio de YouTube."""
    
    def get_source_name(self) -> str:
        """Retorna 'yt'."""
        return "yt"
    
    def get_media_type(self) -> MediaType:
        """Retorna MediaType.AUDIO."""
        return MediaType.AUDIO
    
    def get_file_extensions(self) -> set:
        """Retorna las extensiones de audio."""
        return settings.AUDIO_EXTENSIONS
    
    def validate_url(self, url: str) -> None:
        """
        Valida que la URL sea de YouTube.
        
        Args:
            url: URL a validar
            
        Raises:
            InvalidURLException: Si no es una URL de YouTube
        """
        if not URLValidator.is_youtube_url(url):
            raise InvalidURLException(url=url, reason="Solo se aceptan enlaces de YouTube")
    
    def build_command(
        self,
        url: str,
        output_path: Path,
        **kwargs
    ) -> List[str]:
        """
        Construye el comando para ejecutar yt-dlp (audio).
        
        Args:
            url: URL de YouTube
            output_path: Directorio de salida
            **kwargs: Puede incluir 'quality'
            
        Returns:
            Lista con el comando y argumentos
        """
        output_template = str(output_path / "%(title)s.%(ext)s")
        audio_quality = str(kwargs.get("quality", "0"))
        
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format",
            YTDLP_AUDIO_EXTRACT_FORMAT,
            "--audio-quality",
            audio_quality,
            "-o",
            output_template,
            url,
        ]
        
        return cmd


class YouTubeVideoService(BaseDownloadService):
    """Servicio para descargar video de YouTube."""
    
    def get_source_name(self) -> str:
        """Retorna 'yt'."""
        return "yt"
    
    def get_media_type(self) -> MediaType:
        """Retorna MediaType.VIDEO."""
        return MediaType.VIDEO
    
    def get_file_extensions(self) -> set:
        """Retorna las extensiones de video."""
        return settings.VIDEO_EXTENSIONS
    
    def validate_url(self, url: str) -> None:
        """
        Valida que la URL sea de YouTube.
        
        Args:
            url: URL a validar
            
        Raises:
            InvalidURLException: Si no es una URL de YouTube
        """
        if not URLValidator.is_youtube_url(url):
            raise InvalidURLException(url=url, reason="Solo se aceptan enlaces de YouTube")
    
    def build_command(
        self,
        url: str,
        output_path: Path,
        **kwargs
    ) -> List[str]:
        """
        Construye el comando yt-dlp para descargar video.
        
        Args:
            url: URL de YouTube
            output_path: Directorio de salida
            **kwargs: Puede incluir 'format'
            
        Returns:
            Lista con el comando y argumentos
        """
        output_template = str(output_path / "%(title)s.%(ext)s")
        merge_format = kwargs.get("format") or DEFAULT_VIDEO_FORMAT

        format_selector = self._get_format_selector(merge_format)
        
        cmd = [
            "yt-dlp",
            "-f",
            format_selector,
            "--merge-output-format",
            merge_format,
            "--restrict-filenames",
            "-o",
            output_template,
            url,
        ]
        
        return cmd
    
    def _get_format_selector(self, merge_format: str) -> str:
        """
        Retorna el selector de formato óptimo según el contenedor solicitado.
        
        Args:
            merge_format: Formato del contenedor (mp4, webm, mkv, etc.)
            
        Returns:
            String con el selector de formato para yt-dlp
        """
        # Normalizar formato y obtener selector desde constantes
        fmt = (merge_format or DEFAULT_VIDEO_FORMAT).lower()

        info = VIDEO_FORMAT_INFO.get(fmt)
        if info and info.get("selector"):
            return info["selector"]

        # Fallback al selector por defecto de yt-dlp
        return YTDLP_BEST_VIDEO_FORMAT


# Instancias globales
youtube_audio_service = YouTubeAudioService()
youtube_video_service = YouTubeVideoService()
