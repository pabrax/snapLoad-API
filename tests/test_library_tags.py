"""Tag reader: embedded tags -> sidecar -> filename, cover extraction (spec library/track-index)."""
import json
import subprocess
from pathlib import Path

import pytest

from app.core.process import find_binary, resolve_binary
from app.services import track_metadata
from app.services.track_metadata import extract_cover, read_tags, write_sidecar

needs_ffmpeg = pytest.mark.skipif(
    not (find_binary("ffmpeg") and find_binary("ffprobe")), reason="ffmpeg/ffprobe not installed"
)


def _ffmpeg(*args):
    subprocess.run([resolve_binary("ffmpeg"), "-v", "error", "-y", *args], check=True)


def make_audio(path: Path, ext="mp3", cover=False, **tags) -> Path:
    """Generate a 1 s sine file with real tags and, optionally, an attached cover picture."""
    out = path / f"song.{ext}"
    meta = [x for k, v in tags.items() for x in ("-metadata", f"{k}={v}")]
    tone = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    if cover:
        jpg = path / "cover.jpg"
        _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=64x64:d=1", "-frames:v", "1", str(jpg))
        _ffmpeg(*tone, "-i", str(jpg), "-map", "0", "-map", "1", "-c:a", "libmp3lame", "-c:v", "copy",
                "-id3v2_version", "3", "-disposition:v", "attached_pic",
                "-metadata:s:v", "title=Album cover", *meta, str(out))
    else:
        _ffmpeg(*tone, *meta, str(out))
    return out


@needs_ffmpeg
def test_embedded_tags_and_duration_are_read(tmp_path):
    audio = make_audio(tmp_path, title="Embedded", artist="Band", album="LP")

    tags = read_tags(audio)

    assert (tags.title, tags.artist, tags.album) == ("Embedded", "Band", "LP")
    assert tags.duration_s == pytest.approx(1.0, abs=0.2)
    assert tags.has_cover is False and tags.source == "embedded"


@needs_ffmpeg
def test_embedded_over_sidecar(tmp_path):
    audio = make_audio(tmp_path, title="A", artist="Embedded artist")
    write_sidecar(audio, {"title": "B", "artist": "Sidecar artist", "album": "From sidecar", "duration_s": 99})

    tags = read_tags(audio)

    assert (tags.title, tags.artist) == ("A", "Embedded artist")
    assert tags.album == "From sidecar"  # filled from the sidecar because the file has none
    assert tags.duration_s == pytest.approx(1.0, abs=0.2)  # real duration wins over the sidecar's


@needs_ffmpeg
def test_cover_stream_tags_do_not_override_the_title(tmp_path):
    """The attached picture has its own title tag ("Album cover") that must be ignored."""
    audio = make_audio(tmp_path, cover=True, title="Real title", artist="Band")

    tags = read_tags(audio)

    assert tags.title == "Real title" and tags.has_cover is True


@needs_ffmpeg
def test_stream_level_tags_are_read_for_ogg(tmp_path):
    out = tmp_path / "song.ogg"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "libvorbis",
            "-metadata", "title=Vorbis title", "-metadata", "artist=Vorbis artist", str(out))

    tags = read_tags(out)

    assert (tags.title, tags.artist) == ("Vorbis title", "Vorbis artist")


@needs_ffmpeg
def test_untagged_wav_uses_the_sidecar(tmp_path):
    audio = make_audio(tmp_path, ext="wav")
    write_sidecar(audio, {"title": "From sidecar", "artist": "Band", "album": None, "duration_s": 1})

    tags = read_tags(audio)

    assert (tags.title, tags.artist, tags.source) == ("From sidecar", "Band", "sidecar")


@needs_ffmpeg
def test_filename_fallback_for_legacy(tmp_path):
    audio = make_audio(tmp_path, ext="wav")
    legacy = audio.rename(tmp_path / "Some Old Download.wav")

    tags = read_tags(legacy)

    assert tags.title == "Some Old Download"
    assert tags.artist is None and tags.album is None and tags.source == "filename"


def test_ffprobe_failure_falls_back(tmp_path):
    """A corrupt file (ffprobe error) still yields a usable record from sidecar/filename."""
    broken = tmp_path / "Broken Song.mp3"
    broken.write_bytes(b"not audio at all")

    assert read_tags(broken).title == "Broken Song"

    write_sidecar(broken, {"title": "Sidecar title", "artist": "X", "duration_s": 42})
    tags = read_tags(broken)
    assert (tags.title, tags.artist, tags.duration_s) == ("Sidecar title", "X", 42)
    assert tags.has_cover is False


def test_missing_binary_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(track_metadata, "resolve_binary", lambda name: str(tmp_path / "does-not-exist"))
    audio = tmp_path / "Offline.mp3"
    audio.write_bytes(b"x")

    assert read_tags(audio).title == "Offline"


@needs_ffmpeg
def test_cover_extracted_to_the_target_path(tmp_path):
    audio = make_audio(tmp_path, cover=True, title="T")
    target = tmp_path / "covers" / "x.jpg"

    assert extract_cover(audio, target) is True
    assert target.read_bytes()[:3] == b"\xff\xd8\xff"  # JPEG magic


@needs_ffmpeg
def test_cover_extraction_without_picture_returns_false(tmp_path):
    audio = make_audio(tmp_path, title="T")
    target = tmp_path / "covers" / "x.jpg"

    assert extract_cover(audio, target) is False
    assert not target.exists()


@needs_ffmpeg
def test_sidecar_built_from_embedded_tags(tmp_path):
    """Spotify path: spotdl embeds tags and writes no info.json, so the sidecar is derived from the file."""
    audio = make_audio(tmp_path, title="Spotify song", artist="Artist", album="Album")

    written = track_metadata.write_sidecar_from_tags(audio)

    data = json.loads(written.read_text(encoding="utf-8"))
    assert (data["title"], data["artist"], data["album"]) == ("Spotify song", "Artist", "Album")
    assert data["duration_s"] == pytest.approx(1.0, abs=0.2)


@needs_ffmpeg
def test_spotify_service_writes_the_sidecar_after_moving_the_file(tmp_path):
    from app.services.spotify_service import spotify_download_service

    audio = make_audio(tmp_path, title="Spotify song", artist="Artist")

    spotify_download_service._after_move(audio, audio)

    assert json.loads(track_metadata.sidecar_path(audio).read_text(encoding="utf-8"))["artist"] == "Artist"
