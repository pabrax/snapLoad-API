"""
Servicio de la biblioteca de música.
Registra las pistas de audio descargadas (con sus tags) y rellena las descargas anteriores a la biblioteca.
"""
from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..repositories import download_index_repo, track_id_for, track_repo
from . import track_metadata

BACKFILL_BATCH = 50


def register_track(
    audio_path: Path,
    job_id: Optional[str] = None,
    fmt: Optional[str] = None,
    kept: Optional[bool] = None,
) -> str:
    """
    Registra o actualiza una pista leyendo sus tags.

    Args:
        audio_path: Archivo de audio ya en su destino final
        job_id: Job que lo produjo
        fmt: Formato de audio (por defecto, la extensión)
        kept: Marca kept. None: una pista nueva toma `LIBRARY_AUTO_KEEP` y una existente conserva
            la elección del usuario

    Returns:
        Id de la pista
    """
    audio_path = Path(audio_path)
    if kept is None and track_repo.get(track_id_for(audio_path)) is None:
        kept = settings.LIBRARY_AUTO_KEEP

    tags = track_metadata.read_tags(audio_path)
    return track_repo.upsert(
        path=audio_path,
        job_id=job_id,
        title=tags.title,
        artist=tags.artist,
        album=tags.album,
        duration_s=tags.duration_s,
        fmt=fmt or audio_path.suffix.lstrip(".").lower(),
        size_bytes=audio_path.stat().st_size,
        has_cover=tags.has_cover,
        kept=kept,
        tags_source=tags.source,
    )


def backfill(limit: int = BACKFILL_BATCH) -> int:
    """
    Registra, como máximo `limit` por llamada, los audios `ready` del índice que aún no son pistas.

    Las descargas anteriores a la biblioteca entran sin kept: se conservan solo si el usuario lo decide.

    Returns:
        Número de pistas registradas
    """
    registered = 0
    for entry in download_index_repo.get_all_ready_entries():
        if entry.type != "audio":
            continue
        for file in entry.files:
            if registered >= limit:
                return registered
            path = Path(file)
            if path.suffix.lower() not in settings.AUDIO_EXTENSIONS or not path.is_file():
                continue
            if track_repo.get(track_id_for(path)) is not None:
                continue
            register_track(path, job_id=entry.job_id, kept=False)
            registered += 1
    return registered


def prune_missing() -> int:
    """
    Quita de la biblioteca las pistas cuyo archivo ya no existe y marca su descarga como fallida
    en el índice (así la caché no la da por lista).

    Returns:
        Número de pistas retiradas
    """
    pruned = 0
    for track_id, path, job_id in track_repo.all_files():
        if Path(path).is_file():
            continue
        track_repo.delete(track_id)
        if job_id:
            download_index_repo.register_failed(job_id, f"missing_files:['{path}']")
        pruned += 1
    return pruned


def delete_track(track_id: str) -> bool:
    """
    Borra una pista: audio, sidecar, portada en caché, su fila y la entrada del índice de descargas
    cuando ya no queda en disco ningún archivo de ese job (un job de playlist puede tener varios).

    El llamador debe haber comprobado que la ruta está bajo DOWNLOAD_DIR.

    Returns:
        True si la pista existía
    """
    track = track_repo.get(track_id)
    if track is None:
        return False

    audio = Path(track.path)
    for target in (audio, track_metadata.sidecar_path(audio), settings.DOWNLOAD_DIR / ".covers" / f"{track_id}.jpg"):
        target.unlink(missing_ok=True)
    track_repo.delete(track_id)

    entry = download_index_repo.find_by_job_id(track.job_id) if track.job_id else None
    if entry and not any(Path(f).exists() for f in entry.files):
        download_index_repo.delete_entry(entry.url, entry.type, entry.quality, entry.format)
    return True
