"""
Rutas de la biblioteca de música.
Sirve las pistas de audio descargadas para reproducirlas en el navegador.
"""
import re
import urllib.parse
from pathlib import Path as _Path
from typing import Iterator, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, StrictBool
from fastapi.responses import FileResponse, Response, StreamingResponse

from ..core.config import settings
from ..core.http_range import UNSATISFIABLE, parse_range
from ..helpers import FileNameHelper
from ..repositories import track_repo
from ..schemas import TrackEntry, TrackListResponse, TrackResponse
from ..services import library_service, track_metadata

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


class KeptUpdate(BaseModel):
    """Cuerpo de PATCH /library/tracks/{id}; `kept` debe ser un booleano real."""
    kept: StrictBool


def _get_track(track_id: str) -> TrackEntry:
    """
    Busca una pista por id (nunca por datos del cliente) y comprueba que su ruta registrada
    queda bajo DOWNLOAD_DIR.

    Raises:
        HTTPException: 404 si el id no es válido o no existe; 403 si la ruta queda fuera
    """
    if not TRACK_ID_PATTERN.match(track_id):
        raise HTTPException(status_code=404, detail="pista no encontrada")
    track = track_repo.get(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="pista no encontrada")
    try:
        _Path(track.path).resolve().relative_to(settings.DOWNLOAD_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return track


def _get_track_file(track_id: str) -> _Path:
    """
    Resuelve el archivo de una pista desde su registro.

    Raises:
        HTTPException: 404 si el id no es válido, no existe o el archivo falta; 403 si la
            ruta registrada queda fuera de DOWNLOAD_DIR
    """
    file_path = _Path(_get_track(track_id).path)
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


def _to_response(track: TrackEntry) -> TrackResponse:
    """Proyecta una pista a lo que ve el cliente (sin rutas del servidor)."""
    return TrackResponse(**track.model_dump(include=set(TrackResponse.model_fields)))


@router.get("/tracks", response_model=TrackListResponse)
def list_tracks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="Búsqueda en título o artista"),
):
    """
    Lista las pistas de audio descargadas, las más recientes primero.
    """
    library_service.backfill()
    library_service.prune_missing()
    tracks, total = track_repo.list(limit=limit, offset=offset, q=q)
    return TrackListResponse(
        tracks=[_to_response(t) for t in tracks],
        total=total,
        limit=limit,
        offset=offset,
        kept_bytes=track_repo.kept_bytes(),
    )


@router.get("/tracks/{track_id}/cover")
def track_cover(track_id: str):
    """
    Sirve la portada embebida de una pista (se extrae una vez y se cachea).
    """
    audio = _get_track_file(track_id)
    track = track_repo.get(track_id)
    if not track.has_cover:
        raise HTTPException(status_code=404, detail="la pista no tiene portada")

    cover = settings.DOWNLOAD_DIR / ".covers" / f"{track_id}.jpg"
    if not cover.is_file() and not track_metadata.extract_cover(audio, cover):
        raise HTTPException(status_code=404, detail="la pista no tiene portada")
    return FileResponse(
        path=str(cover),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.patch("/tracks/{track_id}", response_model=TrackResponse)
def update_track(track_id: str, body: KeptUpdate):
    """
    Marca o desmarca una pista como kept (protegida de la limpieza automática).
    """
    _get_track(track_id)
    return _to_response(track_repo.set_kept(track_id, body.kept))


@router.delete("/tracks/{track_id}", status_code=204)
def delete_track(track_id: str):
    """
    Elimina una pista: su audio, sidecar, portada en caché y registros.
    """
    _get_track(track_id)
    library_service.delete_track(track_id)
    return Response(status_code=204)
