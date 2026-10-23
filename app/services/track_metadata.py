"""
Metadatos de pistas de audio: sidecar JSON junto al archivo.
El sidecar existe porque no todos los formatos guardan tags (wav) y como respaldo si el embebido falla.
"""
import json
from pathlib import Path
from typing import Optional

SIDECAR_SUFFIX = ".meta.json"


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
