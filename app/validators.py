"""
Validadores de entrada de la aplicación.
Separa las responsabilidades de validación del resto de utilidades.
"""
import re
from typing import Optional
from .core.constants import (
    SPOTIFY_URI_PATTERN,
    SPOTIFY_URL_PATTERN,
    BITRATE_PATTERN,
    SPOTIFY_URL_PREFIXES,
    YOUTUBE_URL_PREFIXES,
)
from .core.config import settings
from .core.exceptions import InvalidURLException, InvalidQualityException, InvalidFormatException
from .core.constants import ALLOWED_VIDEO_FORMATS


class URLValidator:
    """Validador de URLs para diferentes servicios."""
    
    @staticmethod
    def is_spotify_url(url: str) -> bool:
        """
        Comprueba si la URL/URI es de Spotify.
        
        Args:
            url: URL o URI a validar
            
        Returns:
            True si es una URL/URI válida de Spotify
        """
        if not url or not isinstance(url, str):
            return False
        
        s = url.strip()
        
        # spotify:track:<id> or spotify:album:<id> or spotify:playlist:<id>
        if re.match(SPOTIFY_URI_PATTERN, s):
            return True
        
        # URLs like https://open.spotify.com/intl-es/track/<id>?si=...
        if re.match(SPOTIFY_URL_PATTERN, s):
            return True
        
        return False
    
    @staticmethod
    def is_youtube_url(url: str) -> bool:
        """
        Comprueba si la URL corresponde a YouTube.
        
        Args:
            url: URL a validar
            
        Returns:
            True si es una URL válida de YouTube
        """
        if not url or not isinstance(url, str):
            return False
        
        s = url.strip()
        return s.startswith(YOUTUBE_URL_PREFIXES)
    
    @staticmethod
    def validate_url(url: str, allowed_sources: Optional[list] = None) -> str:
        """
        Valida que una URL sea válida y de una fuente permitida.
        
        Args:
            url: URL a validar
            allowed_sources: Lista de fuentes permitidas ('spotify', 'youtube')
            
        Returns:
            URL validada
            
        Raises:
            InvalidURLException: Si la URL no es válida o no está en las fuentes permitidas
        """
        if not url or not isinstance(url, str):
            raise InvalidURLException(url=url, reason="URL vacía o tipo inválido")
        
        url = url.strip()
        
        if allowed_sources is None:
            if not (URLValidator.is_spotify_url(url) or URLValidator.is_youtube_url(url)):
                raise InvalidURLException(url=url, reason="URL no corresponde a Spotify o YouTube")
        else:
            if 'spotify' in allowed_sources and URLValidator.is_spotify_url(url):
                return url
            if 'youtube' in allowed_sources and URLValidator.is_youtube_url(url):
                return url
            raise InvalidURLException(url=url, reason=f"Fuentes permitidas: {', '.join(allowed_sources)}")
        
        return url


class QualityValidator:
    """Validador de calidad de audio/video."""
    
    @staticmethod
    def is_valid_bitrate(value: str) -> bool:
        """
        Valida un valor de bitrate/quality.
        
        Acepta:
        - "0" (best quality)
        - "bestaudio"
        - números con sufijo k o K (ej. "320k", "128K")
        - números sin sufijo (ej. "320")
        
        Args:
            value: Valor de calidad a validar
            
        Returns:
            True si es válido
        """
        if value is None or not isinstance(value, str):
            return False
        
        v = value.strip().lower()
        return bool(re.match(BITRATE_PATTERN, v))
    
    @staticmethod
    def normalize_quality(value: Optional[str]) -> dict:
        """
        Normaliza un valor de quality para spotdl y yt-dlp.
        
        Args:
            value: Valor de calidad a normalizar
            
        Returns:
            dict con claves 'spotdl' y 'ytdlp'
        """
        if value is None or not isinstance(value, str) or value.strip() == "":
            return {"spotdl": None, "ytdlp": "0"}
        
        v = value.strip()
        lv = v.lower()
        
        if lv == "0":
            return {"spotdl": None, "ytdlp": "0"}
        if lv == "bestaudio":
            return {"spotdl": None, "ytdlp": "bestaudio"}
        
        # Número con o sin sufijo
        m = re.match(r"^(\d+)([kK]?)$", v)
        if m:
            num = m.group(1)
            spot = f"{num}k"  # spotdl usa lowercase 'k'
            ytd = f"{num}K"   # yt-dlp usa uppercase 'K'
            return {"spotdl": spot, "ytdlp": ytd}
        
        return {"spotdl": None, "ytdlp": lv}
    
    @staticmethod
    def validate_quality(quality: Optional[str]) -> Optional[str]:
        """
        Valida una calidad y lanza excepción si no es válida.
        
        Args:
            quality: Calidad a validar
            
        Returns:
            Calidad validada
            
        Raises:
            InvalidQualityException: Si la calidad no es válida
        """
        if quality is None:
            return None
        
        if not QualityValidator.is_valid_bitrate(quality):
            raise InvalidQualityException(quality=quality)
        
        return quality


class FormatValidator:
    """Validador de formatos de video."""
    
    @staticmethod
    def is_valid_video_format(fmt: str) -> bool:
        """
        Valida formato de contenedor de video.
        
        Args:
            fmt: Formato a validar
            
        Returns:
            True si es válido
        """
        if not fmt or not isinstance(fmt, str):
            return False
        return fmt.lower() in ALLOWED_VIDEO_FORMATS
    
    @staticmethod
    def validate_format(fmt: Optional[str]) -> Optional[str]:
        """
        Valida un formato y lanza excepción si no es válido.
        
        Args:
            fmt: Formato a validar
            
        Returns:
            Formato validado
            
        Raises:
            InvalidFormatException: Si el formato no es válido
        """
        if fmt is None:
            return None
        
        if not FormatValidator.is_valid_video_format(fmt):
            raise InvalidFormatException(format_value=fmt, valid_formats=list(ALLOWED_VIDEO_FORMATS))
        
        return fmt.lower()
