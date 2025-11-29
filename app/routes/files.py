"""
Rutas de archivos refactorizadas.
Usa FileManager y MetadataManager en lugar de manipulación directa.
"""
import os
import mimetypes
import urllib.parse
from pathlib import Path as _Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..managers import file_manager, metadata_manager
from ..core.config import settings
from ..core.exceptions import FileNotFoundException, JobNotFoundException
from ..helpers import FileNameHelper


router = APIRouter(tags=["files"])


@router.get("/files/{job_id}")
def list_files(job_id: str):
    """
    Lista los archivos generados por un job.
    """
    try:
        metadata = metadata_manager.read_metadata(job_id)
        
        # Normalizar files a dict (pueden ser FileInfo objects o dicts)
        files_list = []
        for f in metadata.files:
            if hasattr(f, 'name'):  # Es un FileInfo object
                files_list.append({
                    "name": f.name,
                    "path": f.path,
                    "size_bytes": f.size_bytes,
                })
            elif isinstance(f, dict):  # Es un dict
                files_list.append({
                    "name": f.get("name", ""),
                    "path": f.get("path", ""),
                    "size_bytes": f.get("size_bytes", 0),
                })
        
        return {
            "job_id": job_id,
            "files": files_list,
        }
    except JobNotFoundException:
        raise HTTPException(status_code=404, detail="job no encontrado")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _serve_file_response(job_id: str, filename: str):
    """
    Función interna para servir un archivo.
    Compartida entre /files/{job_id}/{filename} y /files/{job_id}/download/{filename}.
    """
    # Obtener metadata
    metadata = metadata_manager.read_metadata(job_id)
    
    # Buscar el archivo en la metadata
    target_file = None
    for f in metadata.files:
        # Manejar tanto FileInfo objects como dicts
        file_name = f.name if hasattr(f, 'name') else f.get('name', '')
        if file_name == filename:
            target_file = f
            break
    
    if not target_file:
        raise FileNotFoundException(filename=filename, context=f"No está listado en metadata del job {job_id}")
    
    # Obtener path
    file_path_str = target_file.path if hasattr(target_file, 'path') else target_file.get('path', '')
    file_path = _Path(file_path_str)
    
    if not file_path.exists():
        raise FileNotFoundException(filename=filename, path=str(file_path), context="Archivo no existe en disco")
    
    # Verificar que está bajo downloads/ (seguridad)
    try:
        file_path.resolve().relative_to(settings.DOWNLOAD_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    
    # Preparar respuesta
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    ascii_name = FileNameHelper.sanitize_filename_ascii(file_path.name)
    
    resp = FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=ascii_name
    )
    
    # RFC5987 filename encoding para UTF-8
    try:
        filename_star = urllib.parse.quote(file_path.name, safe='')
        cd = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{filename_star}'
        resp.headers['Content-Disposition'] = cd
    except Exception:
        # Fallback a ASCII
        resp.headers['Content-Disposition'] = f'attachment; filename="{ascii_name}"'
    
    # Header custom solo si es ASCII seguro
    if all(ord(ch) < 128 for ch in file_path.name):
        resp.headers['X-Original-Filename'] = file_path.name
    
    return resp


@router.get("/files/{job_id}/archive")
def download_archive(job_id: str):
    """
    Crea un ZIP con todos los archivos del job y lo sirve.
    El ZIP se elimina automáticamente después de servirlo.
    """
    try:
        # Obtener metadata
        metadata = metadata_manager.read_metadata(job_id)
        
        if not metadata.files:
            raise HTTPException(status_code=404, detail="No hay archivos para este job")
        
        # Crear ZIP usando FileManager
        zip_path = file_manager.create_archive(job_id, metadata.files)
        
        # Servir con auto-eliminación
        background = BackgroundTask(lambda path: os.remove(path), str(zip_path))
        
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=f"{job_id}.zip",
            background=background
        )
        
    except JobNotFoundException:
        raise HTTPException(status_code=404, detail="job no encontrado")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{job_id}/{filename}")
def serve_file(job_id: str, filename: str):
    """
    Sirve un archivo individual de un job.
    Seguridad: solo sirve archivos listados en metadata y bajo downloads/.
    """
    try:
        return _serve_file_response(job_id, filename)
    except (FileNotFoundException, JobNotFoundException) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
