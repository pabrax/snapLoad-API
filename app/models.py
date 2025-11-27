from pydantic import BaseModel
from typing import Optional


class DownloadRequest(BaseModel):
    url: str
    # audio quality (e.g. "320k", "192k" or yt-dlp quality "0")
    quality: Optional[str] = None


class VideoDownloadRequest(BaseModel):
    url: str
    # desired container/format for video ("webm" or "mp4")
    format: Optional[str] = None