"""
Rutas de descarga refactorizadas usando DownloadOrchestrator.
Eliminado: lógica de negocio, SQL directo, validación duplicada, manipulación directa de archivos.
"""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from ..schemas import DownloadRequest, VideoDownloadRequest
from ..services import download_orchestrator
from ..repositories import download_index_repo
from ..managers import file_manager, metadata_manager, job_manager
from ..validators import URLValidator, QualityValidator, FormatValidator
from ..helpers import DateTimeHelper
from ..core.config import settings
from ..core.exceptions import InvalidURLException, InvalidQualityException, InvalidFormatException
from ..core.media_options import resolve_audio_options
from ..core.video_options import resolve_video_options


router = APIRouter(tags=["download"])


def _video_options(fmt, resolution):
    """Resuelve formato/resolución de video; 400 si no son válidos."""
    try:
        return resolve_video_options(fmt, resolution)
    except (InvalidQualityException, InvalidFormatException) as e:
        raise HTTPException(status_code=400, detail=str(e))


def _audio_options(url: str, quality, fmt):
    """Resuelve calidad/formato de audio para la fuente de la URL; 400 si no son válidos."""
    source = "spotify" if URLValidator.is_spotify_url(url) else "youtube"
    try:
        return resolve_audio_options(quality, fmt, source)
    except (InvalidQualityException, InvalidFormatException) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/lookup")
def lookup_endpoint(url: str, type: str = "audio", quality: str = None, format: str = None, resolution: str = None):
    """
    Verifica si una descarga existe en cache o catálogo.
    Retorna estado: ready (disponible), pending (en progreso), miss (no existe).
    """
    try:
        if not url:
            raise HTTPException(status_code=400, detail="URL requerida")
        
        try:
            URLValidator.validate_url(url)
        except InvalidURLException as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        normalized_quality = None
        if type == "audio":
            opts = _audio_options(url, quality, format)
            normalized_quality, format = opts.quality, opts.format
        else:
            video = _video_options(format, resolution)
            normalized_quality, format = video.resolution, video.format
        result = download_orchestrator.check_availability(
            url=url,
            media_type=type,
            quality=normalized_quality,
            format_=format
        )
        
        response_data = {
            "status": result.status,
            "url": url,
            "type": type,
        }
        
        if result.status == "ready":
            response_data.update({
                "job_id": result.job_id,
                "files": result.files,
                "source": result.source,
            })
            if normalized_quality:
                response_data["quality"] = normalized_quality
                if type == "video":
                    response_data["resolution"] = normalized_quality
            if format:
                response_data["format"] = format
        elif result.status == "pending":
            response_data.update({
                "job_id": result.job_id,
            })
        else:  # miss
            response_data.update({
                "quality": normalized_quality,
                "format": format,
            })
            if type == "video":
                response_data["resolution"] = normalized_quality
        
        return JSONResponse(status_code=200, content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_job_status_response(job_id: str):
    """
    Función interna para obtener el estado de un job.
    Compartida entre /jobs/{job_id} y /status/{job_id}.
    """
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id requerido")
    
    # Intentar leer metadata
    metadata = None
    try:
        metadata = metadata_manager.read_metadata(job_id)
    except Exception:
        pass
    
    # Buscar en download index
    download_info = download_index_repo.find_by_job_id(job_id)
    
    # Consolidar información
    status = None
    files = []
    error = None
    
    if metadata:
        status = metadata.status.value if hasattr(metadata.status, 'value') else metadata.status
        files = [{"name": f.name, "path": f.path, "size_bytes": f.size_bytes} for f in metadata.files]
        error = metadata.error
    
    if not status and download_info:
        status = download_info.status
        files = [{"path": f} for f in download_info.files]
        error = download_info.error
    
    if not status:
        raise HTTPException(status_code=404, detail="job no encontrado")
    
    return JSONResponse(content={
        "job_id": job_id,
        "status": status,
        "files": files,
        "error": error,
    })


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    """
    Obtiene el estado de un job por su ID.
    Busca en metadata y download index.
    """
    try:
        return _get_job_status_response(job_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download")
def download_endpoint(payload: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Inicia una descarga de audio (Spotify o YouTube).
    Usa DownloadOrchestrator para manejar la lógica.
    """
    try:
        url = payload.url
        
        if not url:
            raise HTTPException(status_code=400, detail="URL requerida")
        
        try:
            URLValidator.validate_url(url)
        except InvalidURLException as e:
            raise HTTPException(status_code=400, detail=str(e))

        opts = _audio_options(url, payload.quality, payload.format)

        # Verificar disponibilidad primero
        availability = download_orchestrator.check_availability(
            url=url,
            media_type="audio",
            quality=opts.quality,
            format_=opts.format
        )

        if availability.status == "ready":
            return JSONResponse(status_code=200, content={
                "message": f"Reusado desde {availability.source}",
                "status": "ready",
                "job_id": availability.job_id,
                "url": url,
                "files": availability.files,
                "quality": opts.quality,
                "format": opts.format,
            })
        
        if availability.status == "pending":
            return JSONResponse(status_code=202, content={
                "message": "Descarga ya en progreso",
                "status": "pending",
                "job_id": availability.job_id,
                "url": url,
            })
        
        # Iniciar nueva descarga
        result = download_orchestrator.initiate_download(
            url=url,
            media_type="audio",
            quality=opts.quality,
            format_=opts.format
        )

        return JSONResponse(status_code=202, content={
            "message": "Descarga encolada",
            "job_id": result["job_id"],
            "url": url,
            "source": result["source"],
            "quality": opts.quality,
            "format": opts.format,
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/video")
def download_video(payload: VideoDownloadRequest, background_tasks: BackgroundTasks):
    """
    Inicia una descarga de video de YouTube.
    """
    try:
        url = payload.url
        
        # Validar URL
        try:
            URLValidator.validate_url(url, allowed_sources=['youtube'])
        except InvalidURLException as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        video = _video_options(payload.format, payload.resolution)
        
        # Verificar disponibilidad
        availability = download_orchestrator.check_availability(
            url=url,
            media_type="video",
            quality=video.resolution,
            format_=video.format
        )

        if availability.status == "ready":
            return JSONResponse(status_code=200, content={
                "message": f"Reusado desde {availability.source}",
                "status": "ready",
                "job_id": availability.job_id,
                "url": url,
                "source": "youtube_video",
                "files": availability.files,
                "format": video.format,
                "resolution": video.resolution,
            })
        
        if availability.status == "pending":
            return JSONResponse(status_code=202, content={
                "message": "Descarga ya en progreso",
                "status": "pending",
                "job_id": availability.job_id,
                "url": url,
                "source": "youtube_video",
            })
        
        # Iniciar nueva descarga
        result = download_orchestrator.initiate_download(
            url=url,
            media_type="video",
            quality=video.resolution,
            format_=video.format
        )

        return JSONResponse(status_code=202, content={
            "message": "Descarga encolada",
            "job_id": result["job_id"],
            "url": url,
            "source": "youtube_video",
            "format": video.format,
            "resolution": video.resolution,
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel/{job_id}")
def cancel_job(job_id: str):
    """
    Cancela un job en ejecución.
    """
    try:
        if not job_id:
            raise HTTPException(status_code=400, detail="job_id requerido")
        
        # Intentar terminar el proceso
        success = job_manager.terminate_job(job_id)
        
        if not success:
            # Verificar si el job existe en metadata
            try:
                metadata = metadata_manager.read_metadata(job_id)
                return JSONResponse(content={
                    "job_id": job_id,
                    "cancelled": False,
                    "status": metadata.status.value if hasattr(metadata.status, 'value') else metadata.status,
                })
            except Exception:
                raise HTTPException(status_code=404, detail="job no encontrado")
        
        # Actualizar metadata si existe
        try:
            metadata = metadata_manager.read_metadata(job_id)
            # Actualizar status (esto se podría hacer en el manager)
            from ..schemas import JobMetadata
            updated = JobMetadata(
                job_id=metadata.job_id,
                url=metadata.url,
                media_type=metadata.media_type,
                status="cancelled",
                files=metadata.files,
                created_at=metadata.created_at,
                started_at=metadata.started_at,
                finished_at=DateTimeHelper.now_iso(),
                error=metadata.error,
            )
            metadata_manager.write_metadata(updated)
        except Exception:
            pass
        
        return JSONResponse(content={
            "job_id": job_id,
            "cancelled": success,
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
