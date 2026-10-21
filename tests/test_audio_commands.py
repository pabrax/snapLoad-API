"""Exact CLI arguments built for yt-dlp and spotdl from canonical options."""
from pathlib import Path

from app.core.config import settings
from app.services.spotify_service import spotify_download_service as spotdl
from app.services.youtube_service import youtube_audio_service as ytdlp

OUT = Path("out")


def yt(**kw):
    cmd = ytdlp.build_command("https://youtu.be/x", OUT, **kw)
    return cmd[1:]  # drop resolved binary path


def sp(**kw):
    cmd = spotdl.build_command("https://open.spotify.com/track/" + "a" * 22, OUT, **kw)
    return cmd[1:]


def test_ytdlp_bitrate():
    args = yt(quality="192", format="mp3")
    assert args[:7] == ["-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", "192K"]
    assert args[-1] == "https://youtu.be/x"


def test_ytdlp_best_uses_vbr_zero():
    assert yt(quality="best", format="m4a")[3:7] == ["--audio-format", "m4a", "--audio-quality", "0"]


def test_ytdlp_lossless_omits_audio_quality():
    args = yt(quality="lossless", format="flac")
    assert "--audio-quality" not in args and args[args.index("--audio-format") + 1] == "flac"


def test_ytdlp_ogg_maps_to_vorbis():
    args = yt(quality="128", format="ogg")
    assert args[args.index("--audio-format") + 1] == "vorbis"


def test_ytdlp_missing_kwargs_never_emit_none():
    args = yt(quality=None, format=None)
    assert "None" not in args
    assert args[args.index("--audio-format") + 1] == "mp3"
    assert args[args.index("--audio-quality") + 1] == "0"


def test_spotdl_bitrate_and_format():
    args = sp(quality="192", format="opus")
    assert args[args.index("--format") + 1] == "opus"
    assert args[args.index("--bitrate") + 1] == "192k"


def test_spotdl_best_is_auto_and_lossless_disables_bitrate():
    assert sp(quality="best", format="mp3")[-2:] == ["--bitrate", "auto"]
    assert sp(quality="lossless", format="flac")[-2:] == ["--bitrate", "disable"]


def test_spotdl_missing_kwargs_never_emit_none():
    args = sp(quality=None, format=None)
    assert "None" not in args and args[args.index("--format") + 1] == "mp3"


def test_all_output_extensions_are_collected():
    for ext in (".mp3", ".m4a", ".aac", ".opus", ".ogg", ".flac", ".wav"):
        assert ext in settings.AUDIO_EXTENSIONS
