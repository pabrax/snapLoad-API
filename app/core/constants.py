"""
Constantes utilizadas en la aplicación.
Centraliza valores constantes para facilitar el mantenimiento.
"""

# Calidad por defecto
DEFAULT_QUALITY = "default"
DEFAULT_VIDEO_FORMAT = "webm"

# Patrones regex
SPOTIFY_URI_PATTERN = r"^spotify:(track|album|playlist):([A-Za-z0-9]{22})$"
SPOTIFY_URL_PATTERN = r"^https?://open\.spotify\.com/(?:[A-Za-z\-]+/)?(track|album|playlist)/([A-Za-z0-9]{22})(?:[/?#].*)?$"
BITRATE_PATTERN = r"^(0|bestaudio|\d+[kK]?)$"

# Prefijos de URL
SPOTIFY_URL_PREFIXES = ("spotify:", "https://open.spotify.com/", "http://open.spotify.com/")
YOUTUBE_URL_PREFIXES = (
    "https://www.youtube.com/",
    "https://youtube.com/",
    "https://youtu.be/",
    "https://music.youtube.com/",
    "http://www.youtube.com/",
    "http://youtube.com/",
    "http://youtu.be/",
)

# Mensajes de error
ERROR_INVALID_URL = "URL inválida"
ERROR_INVALID_QUALITY = "quality inválida; use '0', 'bestaudio' o valores numéricos como '320k' o '128'"
ERROR_INVALID_FORMAT = "format inválido"
ERROR_JOB_NOT_FOUND = "job no encontrado"
ERROR_FILE_NOT_FOUND = "archivo no encontrado"
ERROR_META_NOT_FOUND = "meta no encontrada para job_id"
ERROR_UNAUTHORIZED_PATH = "acceso a ruta no permitido"

# Mensajes de éxito
SUCCESS_CACHED = "Reusado desde cache"
SUCCESS_CATALOG = "Reusado desde catálogo"
SUCCESS_QUEUED = "Descarga encolada"
SUCCESS_DOWNLOAD_PROGRESS = "Descarga ya en progreso"

# Comandos externos
YTDLP_AUDIO_EXTRACT_FORMAT = "mp3"
YTDLP_BEST_VIDEO_FORMAT = "bestvideo+bestaudio/best"

VIDEO_FORMAT_INFO = {
    "mp4": {
        "selector": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "codecs": "H.264 + AAC",
        "description": "Universal, alta compatibilidad"
    },
    "webm": {
        "selector": "bestvideo[ext=webm]+bestaudio[ext=webm]/bestvideo+bestaudio/best",
        "codecs": "VP9 + Opus",
        "description": "Optimizado para web"
    },
    "mkv": {
        "selector": "bestvideo+bestaudio/best",
        "codecs": "Universal (todos)",
        "description": "Contenedor flexible, máxima calidad"
    }
}

# Formatos de video permitidos
ALLOWED_VIDEO_FORMATS = ["mp4", "webm", "mkv"]
