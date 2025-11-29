"""
Orchestrator que coordina el flujo completo de descarga.
Maneja la lógica de: cache → catálogo → descarga nueva.
"""
from typing import Optional, Dict, Any
from pathlib import Path

from ..core.config import settings
from ..core.enums import MediaType, DownloadSource, JobStatus
from ..repositories import download_index_repo, media_repo
from ..validators import URLValidator, QualityValidator, FormatValidator
from ..helpers import DateTimeHelper
from ..schemas import DownloadIndexEntry, MediaInfo
from .youtube_service import youtube_audio_service, youtube_video_service
from .spotify_service import spotify_download_service


class AvailabilityResult:
    """Resultado de verificación de disponibilidad."""
    
    def __init__(
        self,
        status: str,
        job_id: Optional[str] = None,
        files: Optional[list] = None,
        error: Optional[str] = None,
        source: Optional[str] = None
    ):
        self.status = status  # 'ready', 'pending', 'miss'
        self.job_id = job_id
        self.files = files or []
        self.error = error
        self.source = source


class DownloadOrchestrator:
    """
    Orquesta el flujo completo de descarga.
    
    Responsabilidades:
    - Verificar si existe en cache o catálogo
    - Determinar el servicio de descarga apropiado
    - Iniciar descargas nuevas
    - Consolidar respuestas
    """
    
    def __init__(self):
        self.download_index = download_index_repo
        self.media_catalog = media_repo
    
    def check_availability(
        self,
        url: str,
        media_type: str,
        quality: Optional[str] = None,
        format_: Optional[str] = None
    ) -> AvailabilityResult:
        """
        Verifica si una descarga existe en cache o catálogo.
        
        Returns:
            AvailabilityResult con estado 'ready', 'pending', o 'miss'
        """
        # 1. Buscar en cache (download index)
        cached = self.download_index.lookup(url, media_type, quality, format_)
        
        if cached and cached.status == "ready":
            # Actualizar último acceso
            self.download_index.touch(
                url,
                media_type,
                quality,
                format_,
                DateTimeHelper.now_iso()
            )
            return AvailabilityResult(
                status="ready",
                job_id=cached.job_id,
                files=cached.files,
                source="cache"
            )
        
        if cached and cached.status == "pending" and cached.job_id:
            return AvailabilityResult(
                status="pending",
                job_id=cached.job_id,
                source="cache"
            )
        
        # 2. Buscar en catálogo de media
        media = self.media_catalog.get_by_url(url)
        
        if media:
            # Verificar si calidad/formato coincide (si se especificó)
            quality_match = quality is None or media.quality == quality
            format_match = format_ is None or media.format == format_
            
            if quality_match and format_match:
                file_path = Path(media.path)
                if file_path.exists():
                    # Registrar en cache para futuros accesos
                    self.download_index.upsert_ready(
                        url,
                        media_type,
                        media.quality,
                        media.format,
                        [str(file_path)],
                        DateTimeHelper.now_iso()
                    )
                    return AvailabilityResult(
                        status="ready",
                        job_id=None,
                        files=[str(file_path)],
                        source="catalog"
                    )
        
        # 3. No encontrado
        return AvailabilityResult(status="miss")
    
    def initiate_download(
        self,
        url: str,
        media_type: str,
        quality: Optional[str] = None,
        format_: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Inicia una nueva descarga.
        
        Returns:
            Dict con job_id y detalles de la descarga
        """
        # Validar URL y determinar servicio
        source = self._determine_source(url)
        
        if source == DownloadSource.SPOTIFY:
            return self._initiate_spotify_download(url, quality, job_id)
        elif source == DownloadSource.YOUTUBE:
            if media_type == "audio":
                return self._initiate_youtube_audio(url, quality, job_id)
            else:  # video
                return self._initiate_youtube_video(url, format_, job_id)
        else:
            raise ValueError(f"URL no soportada: {url}")
    
    def _determine_source(self, url: str) -> DownloadSource:
        """Determina la fuente de la URL."""
        if URLValidator.is_spotify_url(url):
            return DownloadSource.SPOTIFY
        elif URLValidator.is_youtube_url(url):
            return DownloadSource.YOUTUBE
        else:
            raise ValueError("URL no válida")
    
    def _initiate_spotify_download(
        self,
        url: str,
        quality: Optional[str],
        job_id: Optional[str]
    ) -> Dict[str, Any]:
        """Inicia descarga de Spotify."""
        import uuid
        
        if not job_id:
            job_id = uuid.uuid4().hex[:8]
        
        # Registrar como pendiente
        self.download_index.register_pending(
            url,
            "audio",
            quality,
            None,
            job_id,
            DateTimeHelper.now_iso()
        )
        
        # Iniciar descarga asíncrona
        spotify_download_service.download(
            url=url,
            job_id=job_id,
            callback=None,
            quality=quality
        )
        
        return {
            "job_id": job_id,
            "status": "pending",
            "source": "spotify"
        }
    
    def _initiate_youtube_audio(
        self,
        url: str,
        quality: Optional[str],
        job_id: Optional[str]
    ) -> Dict[str, Any]:
        """Inicia descarga de audio de YouTube."""
        import uuid
        
        if not job_id:
            job_id = uuid.uuid4().hex[:8]
        
        # Registrar como pendiente
        self.download_index.register_pending(
            url,
            "audio",
            quality,
            None,
            job_id,
            DateTimeHelper.now_iso()
        )
        
        # Iniciar descarga asíncrona
        youtube_audio_service.download(
            url=url,
            job_id=job_id,
            callback=None,
            quality=quality
        )
        
        return {
            "job_id": job_id,
            "status": "pending",
            "source": "youtube_audio"
        }
    
    def _initiate_youtube_video(
        self,
        url: str,
        format_: Optional[str],
        job_id: Optional[str]
    ) -> Dict[str, Any]:
        """Inicia descarga de video de YouTube."""
        import uuid
        
        if not job_id:
            job_id = uuid.uuid4().hex[:8]
        
        # Registrar como pendiente
        self.download_index.register_pending(
            url,
            "video",
            None,
            format_,
            job_id,
            DateTimeHelper.now_iso()
        )
        
        # Iniciar descarga asíncrona
        youtube_video_service.download(
            url=url,
            job_id=job_id,
            callback=None,
            format=format_
        )
        
        return {
            "job_id": job_id,
            "status": "pending",
            "source": "youtube_video"
        }


# Instancia singleton
download_orchestrator = DownloadOrchestrator()
