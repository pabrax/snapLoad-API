"""Canonical video format/resolution resolution and the yt-dlp arguments derived from it."""
import pytest

from app.core.exceptions import InvalidFormatException, InvalidQualityException
from app.core.video_options import VIDEO_FORMATS, VIDEO_RESOLUTIONS, resolve_video_options


def args(fmt, res=None):
    return resolve_video_options(fmt, res).ytdlp_args()


def value(a, flag):
    return a[a.index(flag) + 1]


def test_defaults_and_case_insensitivity():
    opts = resolve_video_options(None, None)
    assert (opts.format, opts.resolution) == ("webm", "best")
    assert resolve_video_options("MP4", "1080P").resolution == "1080p"


@pytest.mark.parametrize("raw,expected", [("1080", "1080p"), (" 720p ", "720p"), ("BEST", "best"), ("", "best"), (None, "best")])
def test_resolution_spellings(raw, expected):
    assert resolve_video_options("mp4", raw).resolution == expected


@pytest.mark.parametrize("bad", ["999p", "abc", "1080x", "0p"])
def test_invalid_resolution_rejected(bad):
    with pytest.raises(InvalidQualityException):
        resolve_video_options("mp4", bad)


def test_invalid_format_rejected():
    with pytest.raises(InvalidFormatException):
        resolve_video_options("flv", None)


def test_supported_formats_and_resolutions():
    assert set(VIDEO_FORMATS) == {"webm", "mp4", "mkv", "mov", "avi"}
    assert VIDEO_RESOLUTIONS == ("best", "2160p", "1440p", "1080p", "720p", "480p", "360p")


def test_mp4_best_prefers_h264_for_compatibility():
    a = args("mp4")
    assert value(a, "-f") == "bv*+ba/b"
    assert value(a, "-S") == "vcodec:h264,res,acodec:m4a"
    assert value(a, "--merge-output-format") == "mp4" and "--remux-video" not in a


def test_mp4_resolution_cap_uses_height_filter():
    assert value(args("mp4", "720p"), "-f") == "bv*[height<=?720]+ba/b[height<=?720]"


@pytest.mark.parametrize("res", ["1440p", "2160p"])
def test_mp4_above_1080_puts_resolution_before_codec(res):
    assert value(args("mp4", res), "-S") == "res,vcodec:h264,acodec:m4a"


def test_webm_prefers_vp9_opus():
    a = args("webm", "1080p")
    assert value(a, "-S") == "vcodec:vp9,res,acodec:opus" and value(a, "--merge-output-format") == "webm"


def test_mkv_takes_best_quality_without_codec_preference():
    a = args("mkv")
    assert "-S" not in a and value(a, "--merge-output-format") == "mkv"


@pytest.mark.parametrize("fmt", ["mov", "avi"])
def test_mov_and_avi_force_h264_aac_then_remux_without_reencoding(fmt):
    a = args(fmt, "720p")
    assert value(a, "-f") == "bv*[vcodec^=avc1][height<=?720]+ba[acodec^=mp4a]/b[height<=?720]"
    assert value(a, "--merge-output-format") == "mp4" and value(a, "--remux-video") == fmt
    assert "--recode-video" not in a


@pytest.mark.parametrize("fmt", ["mov", "avi"])
def test_mov_and_avi_reject_resolutions_above_1080(fmt):
    with pytest.raises(InvalidQualityException):
        resolve_video_options(fmt, "2160p")


def test_invalid_resolution_message_talks_about_video_not_audio():
    with pytest.raises(InvalidQualityException) as exc:
        resolve_video_options("mp4", "999p")
    assert "video" in str(exc.value).lower() and "audio" not in str(exc.value).lower()
