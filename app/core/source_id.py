"""
Id canónico de la fuente de una URL: la misma canción por enlaces distintos da el mismo id.

Solo se reconocen URLs de UNA pista. Una URL con `list=` se descarta a propósito: yt-dlp se lanza sin
`--no-playlist`, así que esa URL baja la lista entera y no puede reutilizar el archivo de una sola pista.
"""
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{22}$")
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_YT_PATH_KINDS = {"shorts", "embed", "live"}


def _youtube_id(host: str, path: str, query: dict) -> Optional[str]:
    if "list" in query:
        return None
    if host == "youtu.be":
        candidate = path.strip("/").split("/")[0]
    elif host in _YT_HOSTS:
        parts = [p for p in path.split("/") if p]
        if parts[:1] == ["watch"]:
            candidate = (query.get("v") or [""])[0]
        elif len(parts) >= 2 and parts[0] in _YT_PATH_KINDS:
            candidate = parts[1]
        else:
            return None
    else:
        return None
    return f"youtube:{candidate}" if _YT_ID.match(candidate) else None


def _spotify_id(host: str, path: str) -> Optional[str]:
    if host != "open.spotify.com":
        return None
    parts = [p for p in path.split("/") if p]
    if parts and parts[0].startswith("intl-"):
        parts = parts[1:]
    if len(parts) >= 2 and parts[0] == "track" and _SPOTIFY_ID.match(parts[1]):
        return f"spotify:{parts[1]}"
    return None


def canonical_source_id(url: Optional[str]) -> Optional[str]:
    """
    Devuelve `youtube:<id>` o `spotify:<id>` para una URL de una sola pista, o None.

    Args:
        url: URL tal como la pegó el usuario (cualquier variante, con o sin parámetros de seguimiento)
    """
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query)
    return _youtube_id(host, parsed.path, query) or _spotify_id(host, parsed.path)
