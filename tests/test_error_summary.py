"""Failed jobs expose one readable line; the full output stays in the job log."""
from app.helpers import TextHelper

SPOTDL_BOX = """\
┌───────────────────── Traceback (most recent call last) ─────────────────────┐
│ in _run_module_as_main:198                                                  │
│                                                                             │
│ C:\proyecto\.venv\Lib\site-packages\spotdl\console\entry_point.py:101 in    │
│                                                                             │
│   100 │   │   if not check_ytmusic_connection():                            │
│ > 101 │   │   │   raise DownloaderError(                                    │
│   102 │   │   │   │   "You are blocked by YouTube Music. "                  │
└─────────────────────────────────────────────────────────────────────────────┘
DownloaderError: You are blocked by YouTube Music. Please use a VPN, change 
youtube-music to piped, or use other audio providers
"""

YTDLP_403 = """\
WARNING: Your yt-dlp version (2025.11.12) is older than 90 days!
[download] Destination: C:\tmp\video.f399.mp4
[download]   8.0% of  118.62MiB at   15.06MiB/s ETA 00:07ERROR: unable to download video data: HTTP Error 403: Forbidden
"""


def test_spotdl_traceback_is_reduced_to_the_exception_message():
    msg = TextHelper.summarize_error(SPOTDL_BOX)
    assert msg.startswith("DownloaderError: You are blocked by YouTube Music")
    assert "providers" in msg and "│" not in msg and "\n" not in msg


def test_ytdlp_error_is_extracted_even_when_glued_to_a_progress_line():
    assert TextHelper.summarize_error(YTDLP_403) == "unable to download video data: HTTP Error 403: Forbidden"


def test_last_error_wins_and_ansi_is_stripped():
    out = "ERROR: first\n\x1b[0;31mERROR:\x1b[0m [youtube] abc: Video unavailable\n"
    assert TextHelper.summarize_error(out) == "[youtube] abc: Video unavailable"


def test_falls_back_to_last_line_and_limits_length():
    assert TextHelper.summarize_error("a\nb\nfinal line") == "final line"
    assert len(TextHelper.summarize_error("ERROR: " + "x" * 1000)) <= 300
    assert TextHelper.summarize_error("") == "Unknown error"
