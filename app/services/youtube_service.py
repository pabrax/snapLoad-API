"""
Servicio de descarga de YouTube.
Implementa la descarga de audio y video desde YouTube usando yt-dlp.
"""
from pathlib import Path
from typing import List

from .base_download_service import BaseDownloadService
from ..core.enums import MediaType
from ..core.config import settings
from ..core.exceptions import InvalidURLException
from ..core.media_options import AUDIO_FORMATS, resolve_audio_options
from ..core.process import resolve_binary
from ..core.video_options import resolve_video_options
from ..validators import URLValidator
from . import track_metadata


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
            **kwargs: Puede incluir 'quality' y 'format' (valores canónicos de media_options)
            
        Returns:
            Lista con el comando y argumentos
        """
        output_template = str(output_path / "%(title)s.%(ext)s")
        opts = resolve_audio_options(kwargs.get("quality"), kwargs.get("format"), "youtube")

        cmd = [
            resolve_binary("yt-dlp"),
            "-f",
            opts.ytdlp_format_selector(),
            "-x",
            "--audio-format",
            AUDIO_FORMATS[opts.format]["ytdlp"],
        ]

        audio_quality = opts.ytdlp_audio_quality()
        if audio_quality is not None:
            cmd += ["--audio-quality", audio_quality]

        # Tags en el archivo + info.json para el sidecar de la biblioteca; la portada solo donde cabe
        cmd += ["--embed-metadata", "--no-embed-info-json", "--write-info-json"]
        if AUDIO_FORMATS[opts.format]["cover"]:
            cmd += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]

        cmd += ["-o", output_template, url]

        return cmd

    def _process_succeeded(self, returncode: int, raw_output: str, temp_dir: Path) -> bool:
        """
        yt-dlp sale con código 1 si falla solo el embebido de portada/tags, pero el audio ya existe.
        Ese caso no debe tumbar la descarga; cualquier otro error sí.
        """
        if returncode == 0:
            return True
        errors = [l for l in raw_output.splitlines() if l.startswith("ERROR")]
        only_embed_errors = bool(errors) and all(
            l.startswith("ERROR: Postprocessing:") and ("thumbnail" in l.lower() or "metadata" in l.lower())
            for l in errors
        )
        has_audio = any(
            p.is_file() and p.suffix.lower() in self.get_file_extensions() for p in temp_dir.rglob("*")
        )
        return only_embed_errors and has_audio

    def _after_move(self, source: Path, destination: Path) -> None:
        """Escribe el sidecar de metadatos junto al audio a partir del info.json de yt-dlp."""
        info_path = source.with_suffix(".info.json")
        if info_path.is_file():
            track_metadata.write_sidecar_from_info(info_path, destination)


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
            **kwargs: Puede incluir 'format' (contenedor) y 'quality' (resolución, p. ej. "1080p")

        Returns:
            Lista con el comando y argumentos
        """
        output_template = str(output_path / "%(title)s.%(ext)s")
        opts = resolve_video_options(kwargs.get("format"), kwargs.get("quality"))

        return [
            resolve_binary("yt-dlp"),
            *opts.ytdlp_args(),
            "--restrict-filenames",
            "-o",
            output_template,
            url,
        ]


# Instancias globales
youtube_audio_service = YouTubeAudioService()
youtube_video_service = YouTubeVideoService()
