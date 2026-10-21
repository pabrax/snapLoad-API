"""
Resolución canónica de formato y resolución de video, y argumentos de yt-dlp derivados.
Los valores resueltos nunca son None (la resolución "best" es explícita) para que las
claves de caché no lleven NULL.

Decisiones verificadas con ffprobe sobre un clip real de 2160p:
- `bestvideo[ext=mp4]` elegía AV1 dentro de mp4 (poco compatible); mp4 ahora prefiere H.264 (hasta 1080p).
- mov y avi se obtienen por remux (copia de streams, sin pérdida) de H.264 + AAC, por eso se limitan a 1080p.
"""
import re
from dataclasses import dataclass
from typing import Optional

from .exceptions import InvalidFormatException, InvalidQualityException

DEFAULT_VIDEO_FORMAT = "webm"
RESOLUTION_BEST = "best"
VIDEO_RESOLUTIONS = ("best", "2160p", "1440p", "1080p", "720p", "480p", "360p")

# merge: --merge-output-format; sort: -S (None = orden por defecto de yt-dlp, mejor calidad);
# sort_hq: -S cuando la resolución pedida supera 1080p (H.264 no existe por encima);
# h264_aac: exige H.264 + AAC (necesario para remux sin recodificar); remux: --remux-video;
# max_height: tope de resolución del formato.
VIDEO_FORMATS = {
    "webm": {"merge": "webm", "sort": "vcodec:vp9,res,acodec:opus", "sort_hq": None, "h264_aac": False, "remux": None, "max_height": None},
    "mp4": {"merge": "mp4", "sort": "vcodec:h264,res,acodec:m4a", "sort_hq": "res,vcodec:h264,acodec:m4a", "h264_aac": False, "remux": None, "max_height": None},
    "mkv": {"merge": "mkv", "sort": None, "sort_hq": None, "h264_aac": False, "remux": None, "max_height": None},
    "mov": {"merge": "mp4", "sort": "vcodec:h264,res,acodec:m4a", "sort_hq": None, "h264_aac": True, "remux": "mov", "max_height": 1080},
    "avi": {"merge": "mp4", "sort": "vcodec:h264,res,acodec:m4a", "sort_hq": None, "h264_aac": True, "remux": "avi", "max_height": 1080},
}


@dataclass(frozen=True)
class VideoOptions:
    """Opciones de video ya validadas y canónicas."""
    format: str
    resolution: str  # "best" o "<alto>p"

    @property
    def height(self) -> Optional[int]:
        return None if self.resolution == RESOLUTION_BEST else int(self.resolution[:-1])

    def ytdlp_args(self) -> list:
        """Argumentos de yt-dlp (-f, -S, --merge-output-format, --remux-video) para estas opciones."""
        info = VIDEO_FORMATS[self.format]
        cap = f"[height<=?{self.height}]" if self.height else ""

        if info["h264_aac"]:
            selector = f"bv*[vcodec^=avc1]{cap}+ba[acodec^=mp4a]/b{cap}"
        else:
            selector = f"bv*{cap}+ba/b{cap}"

        args = ["-f", selector]

        sort = info["sort_hq"] if self.height and self.height > 1080 and info["sort_hq"] else info["sort"]
        if sort:
            args += ["-S", sort]

        args += ["--merge-output-format", info["merge"]]
        if info["remux"]:
            args += ["--remux-video", info["remux"]]
        return args


def resolve_video_options(fmt: Optional[str], resolution: Optional[str]) -> VideoOptions:
    """
    Valida y normaliza formato y resolución de video.

    Args:
        fmt: webm (default), mp4, mkv, mov o avi
        resolution: "best", "1080", "1080p", ... o None

    Returns:
        VideoOptions canónico

    Raises:
        InvalidFormatException: Si el formato no está soportado
        InvalidQualityException: Si la resolución no es válida o excede el máximo del formato
    """
    fmt_name = (fmt or DEFAULT_VIDEO_FORMAT).strip().lower()
    if fmt_name not in VIDEO_FORMATS:
        raise InvalidFormatException(format_value=fmt, valid_formats=list(VIDEO_FORMATS))

    raw = (resolution or "").strip().lower()
    if raw in ("", RESOLUTION_BEST):
        canonical = RESOLUTION_BEST
    else:
        match = re.fullmatch(r"(\d+)p?", raw)
        canonical = f"{match.group(1)}p" if match else ""
        if canonical not in VIDEO_RESOLUTIONS:
            raise InvalidQualityException(
                quality=resolution,
                reason=f"use una resolución válida: {', '.join(VIDEO_RESOLUTIONS)}",
                media="video",
            )

    max_height = VIDEO_FORMATS[fmt_name]["max_height"]
    opts = VideoOptions(format=fmt_name, resolution=canonical)
    if max_height and opts.height and opts.height > max_height:
        raise InvalidQualityException(
            quality=resolution,
            reason=f"{fmt_name} usa H.264 y admite como máximo {max_height}p",
            media="video",
        )
    return opts
