import json
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import uuid

from app.models import DownloadRequest, VideoDownloadRequest
from app.utils import is_spotify_url, is_youtube_url, is_valid_bitrate, normalize_quality, is_valid_video_format, now_iso
from app.controllers.sd_controller import download
from app.controllers.yt_controller import download_audio, download_video as yt_download_video
from app.utils import DOWNLOAD_DIR, BASE_DIR



router = APIRouter(tags=["Download"])

@router.post("/download")
def download_endpoint(payload: DownloadRequest, background_tasks: BackgroundTasks):
    try:
        # Decide source by inspecting the URL (no `type` field used)
        url = payload.url
        if not url or not isinstance(url, str):
            raise HTTPException(status_code=400, detail="URL inválida")

        job_id = uuid.uuid4().hex[:8]

        # Validate and normalize quality if provided
        normalized = None
        if payload.quality is not None:
            if not is_valid_bitrate(payload.quality):
                raise HTTPException(status_code=400, detail="quality inválida; use '0', 'bestaudio' o valores numéricos como '320k' or '128'.")
            normalized = normalize_quality(payload.quality)

        # Spotify path
        if is_spotify_url(url):
            logs_dir = BASE_DIR / "logs" / "spotify"
            (logs_dir).mkdir(parents=True, exist_ok=True)
            (logs_dir / job_id).mkdir(parents=True, exist_ok=True)

            # Encolar spotdl (wrapper que lanza hilo daemon)
            background_tasks.add_task(
                download,
                url,
                DOWNLOAD_DIR,
                job_id=job_id,
                logs_dir=logs_dir,
                quality=(normalized["spotdl"] if normalized else None),
            )

            return JSONResponse(status_code=202, content={
                "message": "Descarga encolada",
                "job_id": job_id,
                "url": url,
                "source": "spotify",
            })

        # YouTube audio path
        if is_youtube_url(url):
            logs_dir = BASE_DIR / "logs" / "yt"
            (logs_dir).mkdir(parents=True, exist_ok=True)
            (logs_dir / job_id).mkdir(parents=True, exist_ok=True)

            background_tasks.add_task(
                download_audio,
                url,
                DOWNLOAD_DIR,
                job_id=job_id,
                logs_dir=logs_dir,
                quality=(normalized["ytdlp"] if normalized else None),
            )

            return JSONResponse(status_code=202, content={
                "message": "Descarga encolada",
                "job_id": job_id,
                "url": url,
                "source": "youtube_audio",
            })

        raise HTTPException(status_code=400, detail="URL inválida: solo se aceptan enlaces/URIs de Spotify o YouTube")

    except HTTPException as he:
        raise he
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/video")
def download_video(payload: VideoDownloadRequest, background_tasks: BackgroundTasks):
    # Validate URL before entering try/except so HTTPException isn't accidentally caught
    if not is_youtube_url(payload.url):
        raise HTTPException(status_code=400, detail="URL inválida: solo se aceptan enlaces de YouTube")

    try:
        job_id = uuid.uuid4().hex[:8]
        # Validate requested video format
        if payload.format is not None and not is_valid_video_format(payload.format):
            raise HTTPException(status_code=400, detail=f"format inválido: {payload.format}. formatos aceptados: webm, mp4, mkv, mov, avi")
        logs_dir = BASE_DIR / "logs" / "yt"
        (logs_dir).mkdir(parents=True, exist_ok=True)
        (logs_dir / job_id).mkdir(parents=True, exist_ok=True)

        background_tasks.add_task(
            yt_download_video,
            payload.url,
            DOWNLOAD_DIR,
            payload.format,
            job_id=job_id,
            logs_dir=logs_dir,
        )

        return JSONResponse(status_code=202, content={"message": "Descarga encolada", "job_id": job_id, "url": payload.url})
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/cancel/{job_id}")
def cancel_job(job_id: str):
    """Intentar cancelar un job en ejecución identificándolo por `job_id`."""
    from app.job_registry import terminate_job, get_job_proc

    proc = get_job_proc(job_id)
    if not proc:
        # If no process registered, check if meta exists and was already finished
        meta_path = BASE_DIR / "meta" / f"meta-{job_id}.json"
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail="job no encontrado")
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        status = data.get("status")
        return JSONResponse(content={"job_id": job_id, "cancelled": False, "status": status})

    ok = terminate_job(job_id)
    if ok:
        # mark meta as cancelled if exists
        try:
            meta_path = BASE_DIR / "meta" / f"meta-{job_id}.json"
            if meta_path.exists():
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                data["status"] = "cancelled"
                data["finished_at"] = now_iso()
                with open(meta_path, "w", encoding="utf-8") as mf:
                    json.dump(data, mf, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return JSONResponse(content={"job_id": job_id, "cancelled": ok})

