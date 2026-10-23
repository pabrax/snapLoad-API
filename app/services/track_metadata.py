"""
Metadatos de pistas de audio: sidecar JSON junto al archivo.
El sidecar existe porque no todos los formatos guardan tags (wav) y como respaldo si el embebido falla.
"""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.process import resolve_binary

SIDECAR_SUFFIX = ".meta.json"
PROBE_TIMEOUT_S = 20


def sidecar_path(audio_path: Path) -> Path:
    """Ruta del sidecar de un audio: `<archivo>.meta.json`."""
    audio_path = Path(audio_path)
    return audio_path.with_name(audio_path.name + SIDECAR_SUFFIX)


def reduce_info(info: dict) -> dict:
    """
    Reduce el info.json de yt-dlp a los campos que usa la biblioteca.

    Artista: artist, creator, uploader o channel (el primero disponible).
    """
    artist = next((info.get(k) for k in ("artist", "creator", "uploader", "channel") if info.get(k)), None)
    return {
        "title": info.get("track") or info.get("title"),
        "artist": artist,
        "album": info.get("album"),
        "duration_s": info.get("duration"),
        "thumbnail_url": info.get("thumbnail"),
        "source_url": info.get("webpage_url"),
        "source_id": info.get("id"),
    }


def write_sidecar(audio_path: Path, data: dict) -> Path:
    """Escribe el sidecar junto al audio y devuelve su ruta."""
    target = sidecar_path(audio_path)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_sidecar_from_info(info_path: Path, audio_path: Path) -> Optional[Path]:
    """
    Crea el sidecar de `audio_path` desde un info.json de yt-dlp.

    Returns:
        Ruta del sidecar, o None si el info.json no se puede leer (no es motivo para fallar la descarga)
    """
    try:
        info = json.loads(Path(info_path).read_text(encoding="utf-8"))
        return write_sidecar(audio_path, reduce_info(info))
    except (OSError, ValueError):
        return None


def read_sidecar(audio_path: Path) -> Optional[dict]:
    """Lee el sidecar de un audio, o None si no existe o está corrupto."""
    try:
        data = json.loads(sidecar_path(audio_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@dataclass(frozen=True)
class TrackTags:
    """Tags resueltos de una pista; `source` indica el origen de título/artista/álbum."""
    title: Optional[str]
    artist: Optional[str]
    album: Optional[str]
    duration_s: Optional[float]
    has_cover: bool
    source: str  # "embedded", "sidecar" o "filename"


def probe(audio_path: Path) -> Optional[dict]:
    """
    Ejecuta ffprobe (JSON de formato y streams). Devuelve None si ffprobe falta, falla o agota el tiempo.
    """
    try:
        res = subprocess.run(
            [resolve_binary("ffprobe"), "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(audio_path)],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT_S,
        )
        return json.loads(res.stdout) if res.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _lower_tags(tags: Optional[dict]) -> dict:
    return {str(k).lower(): v for k, v in (tags or {}).items() if str(v).strip()}


def _embedded(info: dict) -> dict:
    """
    Tags embebidos: primero los del formato (mp3, m4a, flac, wav) y, si faltan, los del stream
    de audio (ogg/opus los guardan ahí). Los streams de imagen se ignoran: la portada trae su
    propio tag title ("Album cover") que no es el de la canción.
    """
    tags = _lower_tags(info.get("format", {}).get("tags"))
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            for key, value in _lower_tags(stream.get("tags")).items():
                tags.setdefault(key, value)
    return tags


def _has_cover(info: dict) -> bool:
    return any(
        s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") == 1
        for s in info.get("streams", [])
    )


def _float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_tags(audio_path: Path) -> TrackTags:
    """
    Resuelve los tags de una pista campo a campo: embebidos, luego sidecar y, solo para el
    título, el nombre del archivo. Nunca lanza: un archivo ilegible devuelve lo que haya en
    el sidecar o el nombre.
    """
    audio_path = Path(audio_path)
    info = probe(audio_path)
    embedded = _embedded(info) if info else {}
    sidecar = read_sidecar(audio_path) or {}

    def pick(key: str) -> "tuple[Optional[str], Optional[str]]":
        if embedded.get(key):
            return embedded[key], "embedded"
        if sidecar.get(key):
            return sidecar[key], "sidecar"
        return None, None

    title, title_from = pick("title")
    artist, artist_from = pick("artist")
    album, album_from = pick("album")
    if title is None:
        title, title_from = audio_path.stem, "filename"

    sources = {title_from, artist_from, album_from} - {None}
    source = next((s for s in ("embedded", "sidecar", "filename") if s in sources), "filename")

    duration = _float(info.get("format", {}).get("duration")) if info else None
    if duration is None:
        duration = _float(sidecar.get("duration_s"))

    return TrackTags(title, artist, album, duration, _has_cover(info) if info else False, source)


def extract_cover(audio_path: Path, target: Path) -> bool:
    """
    Extrae la portada embebida a `target` (JPEG). Devuelve False, sin dejar archivo, si no hay portada.
    """
    info = probe(audio_path)
    if not info or not _has_cover(info):
        return False
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [resolve_binary("ffmpeg"), "-v", "error", "-y", "-i", str(audio_path),
             "-an", "-map", "0:v:0", "-frames:v", "1", "-c:v", "mjpeg", str(target)],
            capture_output=True, timeout=PROBE_TIMEOUT_S, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        target.unlink(missing_ok=True)
        return False
    return target.is_file() and target.stat().st_size > 0


def write_sidecar_from_tags(audio_path: Path) -> Optional[Path]:
    """
    Crea el sidecar desde los tags embebidos (ruta de Spotify: spotdl los embebe pero no deja info.json).
    """
    tags = read_tags(audio_path)
    try:
        return write_sidecar(audio_path, {
            "title": tags.title, "artist": tags.artist, "album": tags.album, "duration_s": tags.duration_s,
            "thumbnail_url": None, "source_url": None, "source_id": None,
        })
    except OSError:
        return None
