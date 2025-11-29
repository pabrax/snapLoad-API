"""
Servicio de descarga de Spotify.
Implementa la descarga de audio desde Spotify usando spotdl.
"""
from pathlib import Path
from typing import List

from .base_download_service import BaseDownloadService
from ..core.enums import MediaType
from ..core.config import settings
from ..core.exceptions import InvalidURLException
from ..validators import URLValidator


class SpotifyDownloadService(BaseDownloadService):
    """Servicio para descargar contenido de Spotify."""
    
    def get_source_name(self) -> str:
        """Retorna 'spotify'."""
        return "spotify"
    
    def get_media_type(self) -> MediaType:
        """Retorna MediaType.AUDIO."""
        return MediaType.AUDIO
    
    def get_file_extensions(self) -> set:
        """Retorna las extensiones de audio."""
        return settings.AUDIO_EXTENSIONS
    
    def validate_url(self, url: str) -> None:
        """
        Valida que la URL sea de Spotify.
        
        Args:
            url: URL a validar
            
        Raises:
            InvalidURLException: Si no es una URL de Spotify
        """
        if not URLValidator.is_spotify_url(url):
            raise InvalidURLException(url=url, reason="Solo se aceptan enlaces/URIs de Spotify")
    
    def build_command(
        self,
        url: str,
        output_path: Path,
        **kwargs
    ) -> List[str]:
        """
        Construye el comando spotdl.
        
        Args:
            url: URL de Spotify
            output_path: Directorio de salida
            **kwargs: Puede incluir 'quality'
            
        Returns:
            Lista con el comando y argumentos
        """
        cmd = ["spotdl", url, "--output", str(output_path)]
        
        quality = kwargs.get("quality")
        if quality:
            cmd.extend(["--bitrate", str(quality)])
        
        return cmd


# Instancia global
spotify_download_service = SpotifyDownloadService()
