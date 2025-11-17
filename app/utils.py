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
    url = url.strip()
    return url.startswith("https://open.spotify.com/") or url.startswith("spotify:")


def list_audio_files(folder: Path):
    """Devuelve una lista de Path de ficheros con extensiones de audio en `folder` (recursivo)."""
    if not folder.exists():
        return []
    files = []
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            files.append(p)
    return files