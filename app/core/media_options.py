"""
Resolución canónica de calidad y formato de audio.
Única fuente de verdad para rutas, caché (índice/catálogo) y construcción de comandos:
ningún valor resuelto es None, así las claves de caché nunca llevan NULL.
"""
import re
from dataclasses import dataclass
from typing import Optional

from .exceptions import InvalidFormatException, InvalidQualityException

DEFAULT_AUDIO_FORMAT = "mp3"
QUALITY_BEST = "best"
QUALITY_LOSSLESS = "lossless"
QUALITY_SOURCE = "source"  # el stream original se copia tal cual (opus de YouTube)

# Bitrates (kbps) aceptados: intersección de lo que soportan yt-dlp/ffmpeg y spotdl.
AUDIO_BITRATES = ("32", "40", "48", "64", "80", "96", "112", "128", "160", "192", "224", "256", "320")

# Alias que significan "la mejor calidad disponible".
_BEST_ALIASES = {"", "0", "best", "bestaudio"}

# ytdlp/spotdl: valor de --audio-format / --format (None = no soportado por esa herramienta).
# lossless: sin pérdida, el bitrate no aplica. native: YouTube ya entrega ese códec y se copia
# el stream original, así que tampoco hay bitrate que elegir (verificado con ffprobe: opus 48 = 320 = best).
# aac se omite a propósito: yt-dlp lo entrega en un .m4a idéntico al formato m4a.
AUDIO_FORMATS = {
    "mp3": {"ytdlp": "mp3", "spotdl": "mp3", "lossless": False, "native": False},
    "m4a": {"ytdlp": "m4a", "spotdl": "m4a", "lossless": False, "native": False},
    "opus": {"ytdlp": "opus", "spotdl": "opus", "lossless": False, "native": True},
    "ogg": {"ytdlp": "vorbis", "spotdl": "ogg", "lossless": False, "native": False},
    "flac": {"ytdlp": "flac", "spotdl": "flac", "lossless": True, "native": False},
    "wav": {"ytdlp": "wav", "spotdl": "wav", "lossless": True, "native": False},
}


@dataclass(frozen=True)
class AudioOptions:
    """Opciones de audio ya validadas y canónicas."""
    format: str
    quality: str  # "best", "lossless", "source" o un bitrate en kbps ("192")

    @property
    def lossless(self) -> bool:
        return AUDIO_FORMATS[self.format]["lossless"]

    @property
    def native(self) -> bool:
        return AUDIO_FORMATS[self.format]["native"]

    def ytdlp_audio_quality(self) -> Optional[str]:
        """
        Valor de --audio-quality, o None si no debe pasarse (así yt-dlp copia el stream original).

        - lossless y native: no aplica
        - m4a + best: se copia el stream AAC original; recodificar a "mejor VBR" lo infla sin ganar fidelidad
        - otros + best: 0 (mejor VBR del codificador)
        """
        if self.lossless or self.native:
            return None
        if self.quality == QUALITY_BEST:
            return None if self.format == "m4a" else "0"
        return f"{self.quality}K"

    def ytdlp_format_selector(self) -> str:
        """
        Selector -f: para m4a/opus se prefiere el stream nativo para poder copiarlo sin recodificar
        (bestaudio a secas puede elegir Opus y recodificarlo a AAC, ~170 kbps desde una fuente de ~128).
        """
        if self.format == "m4a":
            return "bestaudio[ext=m4a]/bestaudio/best"
        if self.format == "opus":
            return "bestaudio[acodec=opus]/bestaudio/best"
        return "bestaudio/best"

    def spotdl_bitrate(self) -> str:
        """Valor de --bitrate: disable (sin pérdida), auto (bitrate/stream original) o Nk."""
        if self.lossless:
            return "disable"
        if self.native or self.quality == QUALITY_BEST:
            return "auto"
        return f"{self.quality}k"


def supported_audio_formats(source: str) -> list:
    """Formatos de audio soportados por la fuente ('youtube' o 'spotify')."""
    key = "spotdl" if source == "spotify" else "ytdlp"
    return [name for name, info in AUDIO_FORMATS.items() if info[key]]


def resolve_audio_options(
    quality: Optional[str],
    fmt: Optional[str],
    source: str,
) -> AudioOptions:
    """
    Valida y normaliza calidad y formato de audio.

    Args:
        quality: Bitrate en kbps ("192", "192k"), alias de mejor calidad o None
        fmt: Formato de salida (mp3, m4a, aac, opus, ogg, flac, wav) o None
        source: 'youtube' o 'spotify'

    Returns:
        AudioOptions canónico (formato en minúsculas; calidad "best", "lossless" o kbps)

    Raises:
        InvalidQualityException: Si la calidad no es un bitrate soportado
        InvalidFormatException: Si el formato no existe o la fuente no lo soporta
    """
    fmt_name = (fmt or DEFAULT_AUDIO_FORMAT).strip().lower()
    if fmt_name not in supported_audio_formats(source):
        raise InvalidFormatException(
            format_value=fmt, valid_formats=supported_audio_formats(source), media="audio"
        )

    raw = (quality or "").strip().lower()
    if raw == QUALITY_SOURCE and AUDIO_FORMATS[fmt_name]["native"]:
        canonical = QUALITY_SOURCE  # valor canónico (re-resolución idempotente)
    elif raw == QUALITY_LOSSLESS:
        # Valor canónico (re-resolución idempotente); solo tiene sentido con formatos sin pérdida.
        if not AUDIO_FORMATS[fmt_name]["lossless"]:
            raise InvalidQualityException(quality=quality, reason=f"'{fmt_name}' no es un formato sin pérdida")
        canonical = QUALITY_LOSSLESS
    elif raw in _BEST_ALIASES:
        canonical = QUALITY_BEST
    else:
        match = re.fullmatch(r"(\d+)k?", raw)
        if not match or match.group(1) not in AUDIO_BITRATES:
            raise InvalidQualityException(
                quality=quality,
                reason=f"use 'best' o un bitrate en kbps: {', '.join(AUDIO_BITRATES)}",
            )
        canonical = match.group(1)

    if AUDIO_FORMATS[fmt_name]["lossless"]:
        canonical = QUALITY_LOSSLESS
    elif AUDIO_FORMATS[fmt_name]["native"]:
        canonical = QUALITY_SOURCE

    return AudioOptions(format=fmt_name, quality=canonical)
