"""
Cliente mínimo de MusicBrainz (búsqueda de grabaciones) y Cover Art Archive (portadas).

Es una conexión externa y opcional (`MUSICBRAINZ_ENABLED`). Cumple las reglas de MusicBrainz: máximo
1 petición por segundo y un User-Agent identificable (nombre y versión; contacto solo si el usuario lo
configura). Nunca lanza: sin red, con error o sin coincidencia fiable devuelve None.
"""
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

from ..core.config import settings

MB_RECORDING_URL = "https://musicbrainz.org/ws/2/recording"
CAA_FRONT_URL = "https://coverartarchive.org/release/{release_id}/front-500"

MIN_SCORE = 90                 # puntuación mínima de MusicBrainz (0-100)
DURATION_TOLERANCE_S = 5.0     # diferencia máxima de duración si ambas se conocen
MIN_INTERVAL_S = 1.0           # límite de MusicBrainz: 1 petición por segundo
TIMEOUT_S = 10.0
MAX_COVER_BYTES = 5_000_000


@dataclass(frozen=True)
class MBMatch:
    """Coincidencia fiable de MusicBrainz."""
    title: str
    artist: str
    album: Optional[str]
    year: Optional[str]
    track_no: Optional[int]
    recording_id: str
    release_id: Optional[str]


def _escape(text: str) -> str:
    """Escapa para una frase entre comillas de Lucene."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _pick_release(releases: list) -> Optional[dict]:
    """Prefiere un álbum oficial sin etiquetas secundarias (recopilatorio, directo) y el más antiguo."""
    if not releases:
        return None

    def rank(release: dict):
        group = release.get("release-group") or {}
        plain_album = group.get("primary-type") == "Album" and not group.get("secondary-types")
        return (0 if plain_album else 1, 0 if release.get("status") == "Official" else 1,
                release.get("date") or "9999")

    return min(releases, key=rank)


def _artist_credit(credit: list) -> Optional[str]:
    text = "".join(f"{c.get('name', '')}{c.get('joinphrase', '')}" for c in credit or [])
    return text.strip() or None


def _int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _match_from(recording: dict) -> Optional[MBMatch]:
    artist = _artist_credit(recording.get("artist-credit"))
    title = recording.get("title")
    if not (artist and title and recording.get("id")):
        return None
    release = _pick_release(recording.get("releases") or [])
    year = None
    track_no = None
    if release:
        date = str(release.get("date") or "")
        year = date[:4] if date[:4].isdigit() else None
        try:
            track_no = _int(release["media"][0]["track"][0]["number"])
        except (KeyError, IndexError, TypeError):
            track_no = None
    return MBMatch(
        title=title, artist=artist, album=(release or {}).get("title"), year=year, track_no=track_no,
        recording_id=recording["id"], release_id=(release or {}).get("id"),
    )


class MusicBrainzClient:
    """Cliente con limitador de ritmo; `transport`, `clock` y `sleep` se inyectan en los tests."""

    def __init__(
        self,
        transport: Optional[httpx.BaseTransport] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._transport = transport
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last: Optional[float] = None

    @staticmethod
    def _user_agent() -> str:
        contact = (settings.MUSICBRAINZ_CONTACT or "").strip()
        base = f"SnapLoad/{settings.APP_VERSION}"
        return f"{base} ( {contact} )" if contact else base

    def _http(self) -> httpx.Client:
        return httpx.Client(
            transport=self._transport, timeout=TIMEOUT_S, follow_redirects=True,
            headers={"User-Agent": self._user_agent(), "Accept": "application/json"},
        )

    def _throttle(self) -> None:
        """Espera lo necesario para no pasar de 1 petición por segundo (serializa los hilos)."""
        now = self._clock()
        if self._last is not None:
            wait = MIN_INTERVAL_S - (now - self._last)
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
        self._last = now

    def lookup(self, title: Optional[str], artist: Optional[str], duration_s: Optional[float]) -> Optional[MBMatch]:
        """
        Busca una grabación por título (y artista) y devuelve la primera coincidencia fiable.

        Fiable: puntuación >= 90 y, si se conoce la duración de ambos lados, diferencia <= 5 s.
        """
        if not title or not title.strip():
            return None
        query = f'recording:"{_escape(title.strip())}"'
        if artist and artist.strip():
            query += f' AND artist:"{_escape(artist.strip())}"'

        try:
            with self._lock:
                self._throttle()
                with self._http() as http:
                    response = http.get(MB_RECORDING_URL, params={"query": query, "fmt": "json", "limit": 5})
            response.raise_for_status()
            recordings = response.json().get("recordings")
            if not isinstance(recordings, list):
                return None
            for recording in recordings:
                if _int(recording.get("score")) is None or _int(recording["score"]) < MIN_SCORE:
                    continue
                length_ms = _int(recording.get("length"))
                if duration_s and length_ms and abs(length_ms / 1000 - duration_s) > DURATION_TOLERANCE_S:
                    continue
                match = _match_from(recording)
                if match:
                    return match
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return None
        return None

    def fetch_cover(self, release_id: Optional[str]) -> Optional[bytes]:
        """Descarga la portada frontal (500 px) de un release, o None si no hay o falla."""
        if not release_id:
            return None
        try:
            with self._http() as http:
                response = http.get(CAA_FRONT_URL.format(release_id=release_id))
            if response.status_code != 200:
                return None
            if not response.headers.get("content-type", "").startswith("image/"):
                return None
            data = response.content
            return data if 0 < len(data) <= MAX_COVER_BYTES else None
        except (httpx.HTTPError, ValueError):
            return None
