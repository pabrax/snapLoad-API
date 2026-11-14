"""
Cliente mínimo de MusicBrainz (búsqueda de grabaciones) y Cover Art Archive (portadas).

Es una conexión externa y opcional (`MUSICBRAINZ_ENABLED`). Cumple las reglas de MusicBrainz: máximo
1 petición por segundo y un User-Agent identificable (nombre y versión; contacto solo si el usuario lo
configura). Nunca lanza: sin red, con error o sin coincidencia fiable devuelve None.
"""
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

from ..core.config import settings

logger = logging.getLogger("snapload.musicbrainz")

MB_RECORDING_URL = "https://musicbrainz.org/ws/2/recording"
CAA_FRONT_URL = "https://coverartarchive.org/release/{release_id}/front-500"

SEARCH_LIMIT = 100             # MusicBrainz devuelve cientos de directos/recopilatorios con score 100: hay que ver muchas
MIN_SCORE = 90                 # puntuación mínima de MusicBrainz (0-100)
DURATION_TOLERANCE_S = 5.0     # diferencia máxima de duración si ambas se conocen
MIN_INTERVAL_S = 1.0           # límite de MusicBrainz: 1 petición por segundo
TIMEOUT_S = 10.0
MAX_ATTEMPTS = 3               # MusicBrainz responde 503 "ocupado" a menudo: se reintenta
RETRY_DELAY_S = 2.0
RETRYABLE_STATUS = {429, 503}
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


_PLAIN_TYPES = {"Album": 0, "Single": 1, "EP": 1}


def _release_rank(release: dict) -> Optional[int]:
    """
    0 = álbum, 1 = sencillo/EP; None si no sirve para etiquetar. Solo cuentan releases OFICIALES sin tipos
    secundarios: así se descartan directos, bootlegs, recopilatorios y bandas sonoras, que darían un álbum falso.
    """
    if release.get("status") != "Official":
        return None
    group = release.get("release-group") or {}
    if group.get("secondary-types"):
        return None
    return _PLAIN_TYPES.get(group.get("primary-type"))


def _norm(text: Optional[str]) -> str:
    return re.sub(r"[\W_]+", "", (text or "").casefold())


def _artist_credit(credit: list) -> Optional[str]:
    text = "".join(f"{c.get('name', '')}{c.get('joinphrase', '')}" for c in credit or [])
    return text.strip() or None


def _int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _track_no(release: dict) -> Optional[int]:
    try:
        return _int(release["media"][0]["track"][0]["number"])
    except (KeyError, IndexError, TypeError):
        return None


def _consensus_track_no(chosen: dict, rank: int, candidates: list) -> Optional[int]:
    """
    Número de pista más frecuente entre las ediciones aceptadas del mismo álbum. Una sola edición puede
    traer otra numeración (extras, discos dobles); el consenso evita escribir "13 - Creep".
    """
    album = _norm(chosen.get("title"))
    numbers = [n for r_rank, r in candidates
               if r_rank == rank and _norm(r.get("title")) == album and (n := _track_no(r)) is not None]
    if not numbers:
        return None
    counts = {n: numbers.count(n) for n in set(numbers)}
    return min(counts, key=lambda n: (-counts[n], n))


def _match_from(recording: dict, release: dict, track_no: Optional[int]) -> Optional[MBMatch]:
    artist = _artist_credit(recording.get("artist-credit"))
    title = recording.get("title")
    if not (artist and title and recording.get("id")):
        return None
    date = str(release.get("date") or "")
    year = date[:4] if date[:4].isdigit() else None
    return MBMatch(
        title=title, artist=artist, album=release.get("title"), year=year, track_no=track_no,
        recording_id=recording["id"], release_id=release.get("id"),
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

        Fiable: puntuación >= 90, mismo título, duración a <= 5 s si se conoce en ambos lados y una release
        oficial de álbum, sencillo o EP sin tipos secundarios (nunca directos, bootlegs ni recopilatorios).
        """
        if not title or not title.strip():
            return None
        query = f'recording:"{_escape(title.strip())}"'
        if artist and artist.strip():
            query += f' AND artist:"{_escape(artist.strip())}"'
        query += " AND status:official"

        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                with self._lock:
                    self._throttle()
                    with self._http() as http:
                        response = http.get(
                            MB_RECORDING_URL, params={"query": query, "fmt": "json", "limit": SEARCH_LIMIT}
                        )
                if response.status_code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS:
                    logger.info("MusicBrainz %s, retry %s/%s", response.status_code, attempt, MAX_ATTEMPTS - 1)
                    self._sleep(RETRY_DELAY_S)
                    continue
                break
            response.raise_for_status()
            recordings = response.json().get("recordings")
            if not isinstance(recordings, list):
                return None
            wanted = _norm(title)
            best = None
            candidates = []
            for recording in recordings:
                if _int(recording.get("score")) is None or _int(recording["score"]) < MIN_SCORE:
                    continue
                if _norm(recording.get("title")) != wanted:
                    continue
                length_ms = _int(recording.get("length"))
                gap = abs(length_ms / 1000 - duration_s) if duration_s and length_ms else None
                if gap is not None and gap > DURATION_TOLERANCE_S:
                    continue
                for release in recording.get("releases") or []:
                    rank = _release_rank(release)
                    if rank is None:
                        continue
                    # álbum antes que sencillo; luego la edición más antigua (la original, no la reedición);
                    # luego la duración más cercana
                    key = (rank, str(release.get("date") or "9999"), gap if gap is not None else DURATION_TOLERANCE_S)
                    candidates.append((rank, release))
                    if best is None or key < best[0]:
                        best = (key, recording, release)
            if best is None:
                return None
            return _match_from(best[1], best[2], _consensus_track_no(best[2], best[0][0], candidates))
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.warning("MusicBrainz lookup failed: %s", exc.__class__.__name__)
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
