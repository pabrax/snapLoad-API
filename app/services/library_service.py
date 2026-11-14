"""
Servicio de la biblioteca de música.
Registra las pistas de audio descargadas (con sus tags) y rellena las descargas anteriores a la biblioteca.
"""
from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..core.source_id import canonical_source_id
from ..repositories import download_index_repo, track_id_for, track_repo
from . import audio_quality, tagger, track_metadata

BACKFILL_BATCH = 50


def register_track(
    audio_path: Path,
    job_id: Optional[str] = None,
    fmt: Optional[str] = None,
    kept: Optional[bool] = None,
    analyze: bool = False,
) -> str:
    """
    Registra o actualiza una pista leyendo sus tags.

    Args:
        audio_path: Archivo de audio ya en su destino final
        job_id: Job que lo produjo
        fmt: Formato de audio (por defecto, la extensión)
        kept: Marca kept. None: una pista nueva toma `LIBRARY_AUTO_KEEP` y una existente conserva
            la elección del usuario
        analyze: True solo para una descarga recién terminada: mide la sonoridad y escribe el tag
            ReplayGain. El backfill (dentro de un GET) no lo usa: no modifica archivos antiguos

    Returns:
        Id de la pista
    """
    audio_path = Path(audio_path)
    if kept is None and track_repo.get(track_id_for(audio_path)) is None:
        kept = settings.LIBRARY_AUTO_KEEP

    replaygain = None
    if analyze:
        loudness = audio_quality.measure_loudness(audio_path)
        if loudness is not None:
            replaygain = audio_quality.replaygain_db(loudness)
            tagger.write_replaygain(audio_path, loudness)

    tags = track_metadata.read_tags(audio_path)
    quality = audio_quality.quality_from_probe(track_metadata.probe(audio_path))
    sidecar = track_metadata.read_sidecar(audio_path)
    # Origen con pérdida conocido: salió de una descarga (job) o tiene sidecar de yt-dlp/spotdl
    lossy_origin = bool(job_id) or sidecar is not None
    source_id = _resolve_source_id(sidecar, job_id)
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
        codec=quality.codec if quality else None,
        bitrate_kbps=quality.bitrate_kbps if quality else None,
        sample_rate=quality.sample_rate if quality else None,
        quality_note=audio_quality.quality_note(quality, lossy_origin),
        source_id=source_id,
        replaygain_db=replaygain,
    )


def _resolve_source_id(sidecar: Optional[dict], job_id: Optional[str]) -> Optional[str]:
    """
    Id canónico de la fuente de una pista: de la URL del sidecar (yt-dlp) o, si no hay, de la URL
    del job que la descargó (Spotify no deja sidecar con URL). None si no es una pista suelta.
    """
    source_id = canonical_source_id((sidecar or {}).get("source_url"))
    if source_id is None and job_id:
        entry = download_index_repo.find_by_job_id(job_id)
        source_id = canonical_source_id(entry.url) if entry else None
    return source_id


DUPLICATE_DURATION_GAP_S = 2.0


def _norm(text: Optional[str]) -> str:
    return " ".join((text or "").casefold().split())


def find_duplicates() -> "list[list[str]]":
    """
    Grupos de pistas que parecen la misma canción. No borra ni modifica nada.

    Dos pistas son posibles duplicados si comparten `source_id`, o si tienen el mismo artista y
    título (sin mayúsculas ni espacios de más) y duraciones a menos de 2 s. Sin artista, título o
    duración no se afirma nada: una versión en vivo o una pista sin tags no es un duplicado.

    Returns:
        Lista de grupos (ids), de mayor a menor tamaño; solo grupos con 2 o más pistas
    """
    tracks = track_repo.all_entries()
    parent = {t.id: t.id for t in tracks}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    by_source: "dict[str, str]" = {}
    by_name: "dict[tuple, list]" = {}
    for t in tracks:
        if t.source_id:
            if t.source_id in by_source:
                union(t.id, by_source[t.source_id])
            else:
                by_source[t.source_id] = t.id
        if _norm(t.artist) and _norm(t.title) and t.duration_s is not None:
            by_name.setdefault((_norm(t.artist), _norm(t.title)), []).append(t)

    for group in by_name.values():
        group.sort(key=lambda t: t.duration_s)
        for prev, cur in zip(group, group[1:]):
            if cur.duration_s - prev.duration_s <= DUPLICATE_DURATION_GAP_S:
                union(prev.id, cur.id)

    clusters: "dict[str, list[str]]" = {}
    for t in tracks:
        clusters.setdefault(find(t.id), []).append(t.id)
    return sorted((ids for ids in clusters.values() if len(ids) > 1), key=len, reverse=True)


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
