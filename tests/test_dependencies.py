"""Guards the YouTube extraction stack: an outdated yt-dlp stops working when YouTube changes."""
import importlib
from importlib.metadata import version


def as_tuple(v: str) -> tuple:
    return tuple(int(p) for p in v.split(".")[:3])


def test_yt_dlp_is_recent_enough():
    assert as_tuple(version("yt-dlp")) >= (2026, 8, 19)


def test_yt_dlp_ejs_challenge_solver_is_installed():
    assert importlib.import_module("yt_dlp_ejs")
