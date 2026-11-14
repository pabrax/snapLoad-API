"""
Calidad real de un audio: códec, bitrate y frecuencia de muestreo (ffprobe) y una nota honesta.

Todo lo que baja SnapLoad parte de un stream con pérdida (YouTube/YouTube Music ~128-130 kbps, y Spotify
se resuelve desde ahí). Un contenedor lossless o un re-encode muy por encima de esa fuente pesa más pero
no suena mejor; la nota lo dice. Sin origen conocido (archivo ajeno a una descarga) no se afirma nada.
"""
from dataclasses import dataclass
from typing import Optional

# Techo razonable del stream de origen; por encima, un archivo con pérdida es un re-encode inflado.
SOURCE_CEILING_KBPS = 160

_LOSSLESS_CODECS = {"flac", "alac", "wavpack", "tta", "ape"}


@dataclass(frozen=True)
class QualityInfo:
    """Códec y parámetros de un audio tal como los reporta ffprobe."""
    codec: str
    bitrate_kbps: Optional[int]
    sample_rate: Optional[int]
    lossless: bool


def _int(value) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def quality_from_probe(info: Optional[dict]) -> Optional[QualityInfo]:
    """
    Extrae la calidad del primer stream de audio de una salida de ffprobe (`probe`).

    Returns:
        QualityInfo, o None si no hay stream de audio o la entrada es inválida
    """
    if not info:
        return None
    stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if stream is None or not stream.get("codec_name"):
        return None

    codec = str(stream["codec_name"]).lower()
    bits = _int(stream.get("bit_rate")) or _int((info.get("format") or {}).get("bit_rate"))
    return QualityInfo(
        codec=codec,
        bitrate_kbps=round(bits / 1000) if bits else None,
        sample_rate=_int(stream.get("sample_rate")),
        lossless=codec in _LOSSLESS_CODECS or codec.startswith("pcm_"),
    )


def quality_note(quality: Optional[QualityInfo], lossy_origin: bool) -> Optional[str]:
    """
    Nota sobre la calidad real, o None si no hay nada que advertir.

    Args:
        quality: Calidad medida del archivo
        lossy_origin: True si el archivo salió de una descarga (origen con pérdida conocido)
    """
    if quality is None or not lossy_origin:
        return None
    if quality.lossless:
        return (
            "Lossless container from a lossy source: the original stream is ~128 kbps, "
            "so this file is larger but not better."
        )
    if quality.bitrate_kbps and quality.bitrate_kbps > SOURCE_CEILING_KBPS:
        return (
            f"Re-encoded at {quality.bitrate_kbps} kbps from a lossy source of ~128 kbps: "
            "larger file, no real quality gain."
        )
    return None
