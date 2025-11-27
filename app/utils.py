from pathlib import Path
import re
import unicodedata
from datetime import datetime

# Common audio extensions
AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg"}


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def sanitize_filename(name: str, max_length: int = 150) -> str:
    """Sanitiza un nombre de fichero o carpeta para evitar caracteres inválidos.

    - Normaliza Unicode (NFC)
    - Reemplaza barras y caracteres de control
    - Recorta a `max_length` caracteres
    """
    if not name:
        return ""
    # Normalize
    name = unicodedata.normalize("NFC", name)
    # Replace path separators
    name = name.replace("/", "-").replace("\\", "-")
    # Remove control characters
    name = re.sub(r"[\x00-\x1f\x7f]+", "", name)
    # Collapse repeated spaces
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_length:
        name = name[:max_length]
    return name


def is_spotify_url(url: str) -> bool:
    """Comprueba de forma básica si la URL/URI es de Spotify."""
    if not url or not isinstance(url, str):
        return False
    s = url.strip()

    # spotify:track:<id> or spotify:album:<id> or spotify:playlist:<id>
    m = re.match(r"^spotify:(track|album|playlist):([A-Za-z0-9]{22})$", s)
    if m:
        return True

    # URLs like https://open.spotify.com/intl-es/track/<id>?si=... or https://open.spotify.com/track/<id>
    m = re.match(r"^https?://open\.spotify\.com/(?:[A-Za-z\-]+/)?(track|album|playlist)/([A-Za-z0-9]{22})(?:[/?#].*)?$", s)
    if m:
        return True

    return False


def list_audio_files(folder: Path):
    """Devuelve una lista de Path de ficheros con extensiones de audio en `folder` (recursivo)."""
    if not folder.exists():
        return []
    files = []
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            files.append(p)
    return files


def is_youtube_url(url: str) -> bool:
    """Comprueba de forma básica si la URL corresponde a YouTube (incluye youtu.be, youtube.com, music.youtube.com)."""
    if not url or not isinstance(url, str):
        return False
    s = url.strip()
    return (
        s.startswith("https://www.youtube.com/")
        or s.startswith("https://youtube.com/")
        or s.startswith("https://youtu.be/")
        or s.startswith("https://music.youtube.com/")
        or s.startswith("http://www.youtube.com/")
        or s.startswith("http://youtube.com/")
        or s.startswith("http://youtu.be/")
    )


def is_valid_bitrate(value: str) -> bool:
    """Valida un valor de bitrate/quality aceptable.

    Acepta:
    - "0" (indica best/equivalente en yt-dlp)
    - números con sufijo k o K (ej. "320k", "128K")
    - números sin sufijo (ej. "320")
    """
    if value is None:
        return False
    if not isinstance(value, str):
        return False
    v = value.strip().lower()
    # allow '0', 'bestaudio', or digits optionally followed by 'k'/'K'
    import re

    return bool(re.match(r"^(0|bestaudio|\d+[kK]?)$", v))


def is_valid_video_format(fmt: str) -> bool:
    """Valida formato de contenedor de video aceptable (webm/mp4/mkv/mov/avi)."""
    if not fmt or not isinstance(fmt, str):
        return False
    allowed = {"webm", "mp4", "mkv", "mov", "avi"}
    return fmt.lower() in allowed


def normalize_quality(value: str) -> dict:
    """Normaliza un valor de `quality` y devuelve variantes para spotdl y yt-dlp.

    Retorna un dict con claves:
      - 'spotdl': valor para pasar a `spotdl --bitrate` (ej. '320k') o None para no pasar
      - 'ytdlp': valor para pasar a `yt-dlp --audio-quality` (ej. '0' o '128K')

    Reglas simples:
      - None/empty -> {'spotdl': None, 'ytdlp': '0'}
      - '0' -> {'spotdl': None, 'ytdlp': '0'}
      - 'bestaudio' -> {'spotdl': None, 'ytdlp': 'bestaudio'}
      - numeric like '320' -> spotdl '320k', ytdlp '320K'
      - with suffix 'k'/'K' -> spotdl lowercased '320k', ytdlp uppercased '320K'
    """
    if value is None:
        return {"spotdl": None, "ytdlp": "0"}
    if not isinstance(value, str):
        return {"spotdl": None, "ytdlp": "0"}

    v = value.strip()
    if v == "":
        return {"spotdl": None, "ytdlp": "0"}

    lv = v.lower()
    # special cases
    if lv == "0":
        return {"spotdl": None, "ytdlp": "0"}
    if lv == "bestaudio":
        return {"spotdl": None, "ytdlp": "bestaudio"}

    import re
    m = re.match(r"^(\d+)([kK]?)$", v)
    if m:
        num = m.group(1)
        suffix = m.group(2)
        spot = f"{num}k"  # spotdl prefers lowercase 'k'
        ytd = f"{num}K"  # yt-dlp conventional capital 'K' for quality
        return {"spotdl": spot, "ytdlp": ytd}

    # fallback: return for yt-dlp as given (lowercased) and no spotdl bitrate
    return {"spotdl": None, "ytdlp": lv}