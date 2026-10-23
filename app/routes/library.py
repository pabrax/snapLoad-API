"""
Rutas de la biblioteca de música.
Sirve las pistas de audio descargadas para reproducirlas en el navegador.
"""
import re
import urllib.parse
from pathlib import Path as _Path
from typing import Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..core.config import settings
from ..core.http_range import UNSATISFIABLE, parse_range
from ..helpers import FileNameHelper
from ..repositories import track_repo

router = APIRouter(prefix="/library", tags=["library"])

TRACK_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")
CHUNK_SIZE = 64 * 1024

AUDIO_MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg; codecs=opus",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
}


def _get_track_file(track_id: str) -> _Path:
    """
    Resuelve el archivo de una pista desde su registro, nunca desde datos del cliente.

    Raises:
        HTTPException: 404 si el id no es válido, no existe o el archivo falta; 403 si la
            ruta registrada queda fuera de DOWNLOAD_DIR
    """
    if not TRACK_ID_PATTERN.match(track_id):
        raise HTTPException(status_code=404, detail="pista no encontrada")
    track = track_repo.get(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="pista no encontrada")

    file_path = _Path(track.path)
    try:
        file_path.resolve().relative_to(settings.DOWNLOAD_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="archivo no encontrado")
    return file_path


def _iter_file(path: _Path, start: int, length: int) -> Iterator[bytes]:
    """Lee `length` bytes desde `start` en bloques, cerrando el archivo al terminar."""
    with open(path, "rb") as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _inline_disposition(name: str) -> str:
    ascii_name = FileNameHelper.sanitize_filename_ascii(name)
    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{urllib.parse.quote(name, safe="")}'


@router.get("/tracks/{track_id}/stream")
def stream_track(track_id: str, request: Request):
    """
    Sirve el audio de una pista en línea, con soporte de HTTP Range para poder hacer seek.
    """
    file_path = _get_track_file(track_id)
    size = file_path.stat().st_size
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": _inline_disposition(file_path.name),
    }
    media_type = AUDIO_MIME_TYPES.get(file_path.suffix.lower(), "application/octet-stream")

    byte_range = parse_range(request.headers.get("range"), size)
    if byte_range == UNSATISFIABLE:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})

    if byte_range is None:
        start, end, status = 0, size - 1, 200
    else:
        start, end = byte_range
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    length = end - start + 1 if size else 0
    headers["Content-Length"] = str(length)
    return StreamingResponse(
        _iter_file(file_path, start, length),
        status_code=status,
        media_type=media_type,
        headers=headers,
    )
