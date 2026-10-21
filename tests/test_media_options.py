"""Canonical audio quality/format resolution (single source of truth for routes, cache and commands)."""
import pytest

from app.core.exceptions import InvalidFormatException, InvalidQualityException
from app.core.media_options import AUDIO_FORMATS, resolve_audio_options


@pytest.mark.parametrize("quality", [None, "", "0", "best", "bestaudio", " BestAudio "])
def test_missing_or_best_quality_resolves_to_best(quality):
    opts = resolve_audio_options(quality, None, "youtube")
    assert (opts.format, opts.quality) == ("mp3", "best")


@pytest.mark.parametrize("raw", ["192", "192k", "192K", " 192 "])
def test_bitrate_spellings_are_canonicalized(raw):
    assert resolve_audio_options(raw, "mp3", "youtube").quality == "192"


@pytest.mark.parametrize("bad", ["999", "abc", "5", "-1", "192kbps", "1e3"])
def test_invalid_quality_is_rejected(bad):
    with pytest.raises(InvalidQualityException):
        resolve_audio_options(bad, "mp3", "youtube")


@pytest.mark.parametrize("fmt", ["flac", "wav"])
def test_lossless_formats_ignore_bitrate(fmt):
    opts = resolve_audio_options("320", fmt, "youtube")
    assert (opts.format, opts.quality, opts.lossless) == (fmt, "lossless", True)


def test_lossless_still_rejects_garbage_quality():
    with pytest.raises(InvalidQualityException):
        resolve_audio_options("abc", "flac", "youtube")


def test_format_is_case_insensitive_and_validated():
    assert resolve_audio_options("128", "OPUS", "youtube").format == "opus"
    with pytest.raises(InvalidFormatException):
        resolve_audio_options("128", "mp4", "youtube")


def test_aac_is_not_offered_because_it_duplicates_m4a():
    for source in ("youtube", "spotify"):
        with pytest.raises(InvalidFormatException):
            resolve_audio_options("128", "aac", source)


def test_opus_keeps_the_source_stream_so_bitrate_is_not_applicable():
    for quality in (None, "48", "320", "best"):
        opts = resolve_audio_options(quality, "opus", "youtube")
        assert (opts.format, opts.quality, opts.native) == ("opus", "source", True)


def test_supported_audio_formats():
    assert set(AUDIO_FORMATS) == {"mp3", "m4a", "opus", "ogg", "flac", "wav"}


def test_resolution_is_idempotent_on_canonical_values():
    for fmt, quality in (("mp3", "192"), ("m4a", "best"), ("opus", "source"), ("flac", "lossless")):
        first = resolve_audio_options(quality, fmt, "youtube")
        assert resolve_audio_options(first.quality, first.format, "youtube") == first


def test_lossless_quality_with_lossy_format_is_rejected():
    with pytest.raises(InvalidQualityException):
        resolve_audio_options("lossless", "mp3", "youtube")
