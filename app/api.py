from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from starlette.background import BackgroundTask
import mimetypes
import os
import zipfile
from pathlib import Path as _Path
import shutil
import tempfile
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from .controllers.sd_controller import download
from .utils import is_spotify_url
from .utils import is_valid_bitrate, is_valid_video_format, normalize_quality, now_iso
from .controllers.yt_controller import download_audio, download_video as yt_download_video
from .utils import is_youtube_url
import uuid
import json


BASE_DIR = Path(__file__).resolve().parent.parent  # raíz del proyecto
DOWNLOAD_DIR = BASE_DIR / "downloads"

class DownloadRequest(BaseModel):
    url: str
    # audio quality (e.g. "320k", "192k" or yt-dlp quality "0")
    quality: Optional[str] = None

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


class VideoDownloadRequest(BaseModel):
    url: str
    # desired container/format for video ("webm" or "mp4")
    format: Optional[str] = None


# Note: YouTube-audio is now handled by the unified `/download` endpoint above.


@app.post("/download/video")
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


@app.get("/files/{job_id}")
def list_files(job_id: str):
    """Lista ficheros producidos por un job (según `meta/meta-<job_id>.json`)."""
    meta_dir = BASE_DIR / "meta"
    meta_path = meta_dir / f"meta-{job_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="meta no encontrada para job_id")
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        files = data.get("files", [])
        # Return minimal info and download URL
        result = []
        for f in files:
            name = f.get("name")
            size = f.get("size_bytes")
            download_url = f"/files/{job_id}/download/{name}"
            result.append({"name": name, "size_bytes": size, "download_url": download_url})
        return JSONResponse(content={"job_id": job_id, "files": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files/{job_id}/download/{filename}")
def download_file(job_id: str, filename: str):
    """Entrega un fichero individual asociado a `job_id`.

    Seguridad: solo se sirven ficheros listados en la `meta` y que residan bajo `downloads/`.
    """
    meta_dir = BASE_DIR / "meta"
    meta_path = meta_dir / f"meta-{job_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="meta no encontrada para job_id")
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        files = data.get("files", [])
        target = None
        for f in files:
            if f.get("name") == filename:
                target = f
                break
        if not target:
            raise HTTPException(status_code=404, detail="archivo no encontrado para este job_id")

        p = _Path(target.get("path"))
        if not p.exists():
            raise HTTPException(status_code=404, detail="archivo no existe en el disco")

        # Ensure file is under downloads directory
        try:
            p.resolve().relative_to(DOWNLOAD_DIR.resolve())
        except Exception:
            raise HTTPException(status_code=403, detail="acceso a ruta no permitido")

        media_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        return FileResponse(path=str(p), media_type=media_type, filename=p.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files/{job_id}/archive")
def download_archive(job_id: str):
    """Crea un ZIP temporal con todos los ficheros del job y lo entrega.

    El ZIP temporal se elimina tras servirlo usando un BackgroundTask.
    """
    meta_dir = BASE_DIR / "meta"
    meta_path = meta_dir / f"meta-{job_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="meta no encontrada para job_id")
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        files = data.get("files", [])
        if not files:
            raise HTTPException(status_code=404, detail="no hay ficheros para este job_id")

        tmp_dir = BASE_DIR / "tmp" / "archives"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        zip_path = tmp_dir / f"{job_id}.zip"

        # create zip
        with zipfile.ZipFile(str(zip_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                p = _Path(f.get("path"))
                if p.exists():
                    # ensure path is under downloads
                    try:
                        p.resolve().relative_to(DOWNLOAD_DIR.resolve())
                    except Exception:
                        continue
                    zf.write(str(p), arcname=p.name)

        # serve and schedule deletion
        background = BackgroundTask(lambda pth: os.remove(pth), str(zip_path))
        return FileResponse(path=str(zip_path), media_type="application/zip", filename=f"{job_id}.zip", background=background)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cancel/{job_id}")
def cancel_job(job_id: str):
    """Intentar cancelar un job en ejecución identificándolo por `job_id`."""
    from .job_registry import terminate_job, get_job_proc

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


@app.on_event("shutdown")
def _on_shutdown():
    # try to terminate all running jobs gracefully
    try:
        from .job_registry import terminate_all

        terminate_all()
    except Exception:
        pass



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