from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from starlette.background import BackgroundTask
from pathlib import Path as _Path
import mimetypes
import os
import json
import zipfile

from ..utils import (
    DOWNLOAD_DIR,
    BASE_DIR,
)

router = APIRouter(tags=["Files"])


@router.get("/meta/{job_id}")
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


@router.get("/status/{job_id}")
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


@router.get("/files/{job_id}")
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


@router.get("/files/{job_id}/download/{filename}")
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


@router.get("/files/{job_id}/archive")
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

