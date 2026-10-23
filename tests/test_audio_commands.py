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


def test_ytdlp_best_mp3_uses_vbr_zero():
    assert yt(quality="best", format="mp3")[3:7] == ["--audio-format", "mp3", "--audio-quality", "0"]


def test_ytdlp_best_ogg_uses_vbr_zero():
    args = yt(quality="best", format="ogg")
    assert args[args.index("--audio-quality") + 1] == "0"


def test_ytdlp_best_m4a_copies_source_instead_of_inflating():
    args = yt(quality="best", format="m4a")
    assert "--audio-quality" not in args and args[args.index("--audio-format") + 1] == "m4a"


def test_ytdlp_m4a_with_bitrate_reencodes():
    args = yt(quality="64", format="m4a")
    assert args[args.index("--audio-quality") + 1] == "64K"


def test_ytdlp_opus_never_gets_audio_quality():
    args = yt(quality="96", format="opus")
    assert "--audio-quality" not in args and args[args.index("--audio-format") + 1] == "opus"


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
    args = sp(quality="192", format="ogg")
    assert args[args.index("--format") + 1] == "ogg"
    assert args[args.index("--bitrate") + 1] == "192k"


def test_spotdl_best_and_opus_are_auto_and_lossless_disables_bitrate():
    assert sp(quality="best", format="mp3")[-2:] == ["--bitrate", "auto"]
    assert sp(quality="source", format="opus")[-2:] == ["--bitrate", "auto"]
    assert sp(quality="lossless", format="flac")[-2:] == ["--bitrate", "disable"]


def test_spotdl_missing_kwargs_never_emit_none():
    args = sp(quality=None, format=None)
    assert "None" not in args and args[args.index("--format") + 1] == "mp3"


def test_all_output_extensions_are_collected():
    for ext in (".mp3", ".m4a", ".opus", ".ogg", ".flac", ".wav"):
        assert ext in settings.AUDIO_EXTENSIONS


def test_ytdlp_prefers_the_native_source_stream_so_it_can_be_copied():
    def selector(**kw):
        args = yt(**kw)
        return args[args.index("-f") + 1]

    assert selector(quality="best", format="m4a") == "bestaudio[ext=m4a]/bestaudio/best"
    assert selector(quality="best", format="opus") == "bestaudio[acodec=opus]/bestaudio/best"
    assert selector(quality="128", format="mp3") == "bestaudio/best"


def test_ytdlp_embeds_metadata_and_cover_for_formats_that_hold_pictures():
    for fmt in ("mp3", "m4a", "opus", "ogg", "flac"):
        args = yt(quality="best", format=fmt)
        assert "--embed-metadata" in args and "--write-info-json" in args
        assert "--embed-thumbnail" in args
        assert args[args.index("--convert-thumbnails") + 1] == "jpg"
        assert "--no-embed-info-json" in args
        assert args[-3:-1] == ["-o", str(OUT / "%(title)s.%(ext)s")]


def test_ytdlp_wav_gets_tags_and_info_but_never_a_thumbnail():
    """yt-dlp exits 1 when asked to embed a thumbnail into wav (verified with 2026.08.19)."""
    args = yt(quality="lossless", format="wav")
    assert "--embed-metadata" in args and "--write-info-json" in args
    assert "--embed-thumbnail" not in args and "--convert-thumbnails" not in args
