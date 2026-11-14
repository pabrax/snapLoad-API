"""
Enriquecimiento de una descarga de audio antes de moverla a su destino final.

Con `MUSICBRAINZ_ENABLED` busca la canción y escribe tags y portada en el archivo temporal; con
`LIBRARY_LAYOUT=artist-album` decide la carpeta `Artista/Álbum` y el nombre `NN - Título`.
Con ambas funciones apagadas no hace nada. Ningún error aquí puede fallar la descarga.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..helpers import FileNameHelper
from . import track_metadata
from .musicbrainz import MBMatch, MusicBrainzClient
from .tagger import TagData, clean_artist, clean_title, write_tags

_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_client: Optional[MusicBrainzClient] = None


@dataclass(frozen=True)
class Placement:
    """Dónde dejar el archivo: subcarpeta bajo el destino y, opcionalmente, un nombre nuevo."""
    subdir: Path
    name: Optional[str] = None


def get_client() -> MusicBrainzClient:
    """Cliente compartido: el límite de 1 petición por segundo vale para todo el proceso."""
    global _client
    if _client is None:
        _client = MusicBrainzClient()
    return _client


def safe_component(text: Optional[str]) -> str:
    """Nombre de carpeta/archivo válido en Windows y POSIX; nunca vacío ni '..'."""
    name = FileNameHelper.sanitize_filename(text or "")
    name = re.sub(r'[<>:"|?*]+', "_", name).rstrip(" .")
    if not name:
        return "_"
    return f"{name}_" if name.split(".")[0].upper() in _WINDOWS_RESERVED else name


def build_placement(
    artist: Optional[str], album: Optional[str], title: Optional[str], track_no: Optional[int], ext: str
) -> Optional[Placement]:
    """Placement `Artista/Álbum/NN - Título.ext`, o None si faltan artista o título."""
    if not (artist and artist.strip() and title and title.strip()):
        return None
    stem = safe_component(title)
    name = f"{track_no:02d} - {stem}{ext}" if track_no else f"{stem}{ext}"
    return Placement(Path(safe_component(artist)) / safe_component(album or "Singles"), name)


def _write_match(source: Path, match: MBMatch) -> None:
    cover = None
    try:
        cover = get_client().fetch_cover(match.release_id)
    except Exception:
        cover = None
    write_tags(source, TagData(
        title=match.title, artist=match.artist, album=match.album, year=match.year,
        track_no=match.track_no, mb_recording_id=match.recording_id, mb_release_id=match.release_id,
    ), cover=cover)


def _prepare(source: Path) -> Optional[Placement]:
    tags = track_metadata.read_tags(source)
    artist = clean_artist(tags.artist)
    title = clean_title(tags.title, artist)

    match = None
    if settings.MUSICBRAINZ_ENABLED:
        try:
            match = get_client().lookup(title, artist, tags.duration_s)
        except Exception:
            match = None
        if match:
            _write_match(source, match)

    if settings.LIBRARY_LAYOUT != "artist-album":
        return None
    if match:
        return build_placement(match.artist, match.album, match.title, match.track_no, source.suffix.lower())
    return build_placement(artist, tags.album, title, None, source.suffix.lower())


def prepare_audio(source: Path) -> Optional[Placement]:
    """
    Enriquece el audio temporal `source` y devuelve dónde colocarlo, o None para el comportamiento de siempre.
    """
    if not (settings.MUSICBRAINZ_ENABLED or settings.LIBRARY_LAYOUT == "artist-album"):
        return None
    try:
        return _prepare(Path(source))
    except Exception:
        return None
