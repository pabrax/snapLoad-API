from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from .controllers.sd_controller import download_sync
from .utils import is_spotify_url
from .controllers.yt_controller import download_audio_sync, download_video_sync
from .utils import is_youtube_url
import uuid
import json


BASE_DIR = Path(__file__).resolve().parent.parent  # raíz del proyecto
DOWNLOAD_DIR = BASE_DIR / "downloads"

class DownloadRequest(BaseModel):
    url: str
    type: Optional[str] = None

app = FastAPI(
    title="SDAPI",
    description="API para descargar música de Spotify usando spotdl",
    version="1.0.0"
)

@app.post("/download")
def download_endpoint(payload: DownloadRequest, background_tasks: BackgroundTasks):
    try:
        # Decide source by inspecting the URL (no `type` field used)
        url = payload.url
        if not url or not isinstance(url, str):
            raise HTTPException(status_code=400, detail="URL inválida")

        job_id = uuid.uuid4().hex[:8]

        # Spotify path
        if is_spotify_url(url):
            logs_dir = BASE_DIR / "logs" / "spotify"
            (logs_dir).mkdir(parents=True, exist_ok=True)
            (logs_dir / job_id).mkdir(parents=True, exist_ok=True)

            # Encolar spotdl sync (forced_type not used)
            background_tasks.add_task(
                download_sync,
                url,
                DOWNLOAD_DIR,
                None,
                job_id=job_id,
                logs_dir=logs_dir,
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
                download_audio_sync,
                url,
                DOWNLOAD_DIR,
                None,
                job_id=job_id,
                logs_dir=logs_dir,
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


class VideoDownloadRequest(BaseModel):
    url: str
    type: Optional[str] = None


# Note: YouTube-audio is now handled by the unified `/download` endpoint above.


@app.post("/download/video")
def download_video(payload: VideoDownloadRequest, background_tasks: BackgroundTasks):
    # Validate URL before entering try/except so HTTPException isn't accidentally caught
    if not is_youtube_url(payload.url):
        raise HTTPException(status_code=400, detail="URL inválida: solo se aceptan enlaces de YouTube")

    try:
        job_id = uuid.uuid4().hex[:8]
        logs_dir = BASE_DIR / "logs" / "yt"
        (logs_dir).mkdir(parents=True, exist_ok=True)
        (logs_dir / job_id).mkdir(parents=True, exist_ok=True)

        background_tasks.add_task(
            download_video_sync,
            payload.url,
            DOWNLOAD_DIR,
            payload.type,
            job_id=job_id,
            logs_dir=logs_dir,
        )

        return JSONResponse(status_code=202, content={"message": "Descarga encolada", "job_id": job_id, "url": payload.url})
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return JSONResponse(content={"message": "Bienvenido a SDAPI"})


@app.get("/meta/{job_id}")
def get_meta(job_id: str):
    meta_dir = BASE_DIR / "meta"
    meta_path = meta_dir / f"meta-{job_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="meta no encontrada para job_id")
    try:
        data = meta_path.read_text(encoding="utf-8")
        return JSONResponse(content=json.loads(data))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{job_id}")
def get_status(job_id: str):
    """Devuelve un estado ligero del job.

    Lógica:
    - Si existe `meta/meta-<job_id>.json` devuelve su `status` y la `meta` completa.
    - Si no existe meta pero existe `logs/<job_id>/job-<job_id>.log` se asume `running`.
    - Si existe `logs/<job_id>/` pero no log ni meta se asume `queued`.
    - Si no existe nada devuelve 404.
    """
    meta_dir = BASE_DIR / "meta"
    meta_path = meta_dir / f"meta-{job_id}.json"

    # If final meta exists, return it (authoritative)
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return JSONResponse(content={
                "job_id": job_id,
                "status": data.get("status", "unknown"),
                "meta": data,
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Fallback heuristics: search in spotify and yt specific logs, then generic logs/
    candidates = [
        BASE_DIR / "logs" / "spotify" / job_id,
        BASE_DIR / "logs" / "yt" / job_id,
        BASE_DIR / "logs" / job_id,
    ]

    for d in candidates:
        log_path = d / f"job-{job_id}.log"
        if log_path.exists():
            return JSONResponse(content={"job_id": job_id, "status": "running", "log_path": str(log_path)})

    for d in candidates:
        if d.exists():
            return JSONResponse(content={"job_id": job_id, "status": "queued"})

    raise HTTPException(status_code=404, detail="job no encontrado")



# Health endpoint (commented — activate if you want a simple dependency check)
#
# from shutil import which
#
# @app.get("/health")
# def health_check():
#     """Simple health check that verifies required binaries are present.
#
#     Currently commented out; enable when you want to expose a health endpoint.
#     """
#     required = {"spotdl": which("spotdl"), "ffmpeg": which("ffmpeg")}
#     missing = [k for k, v in required.items() if not v]
#     if missing:
#         return JSONResponse(status_code=503, content={"status": "degraded", "missing": missing})
#     return JSONResponse(content={"status": "ok"})