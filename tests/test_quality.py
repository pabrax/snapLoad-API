"""Audio quality probe and honest quality notes (feature library-quality-dedup-tags, S3)."""
import sqlite3
import subprocess

import pytest

from app.core.process import find_binary, resolve_binary
from app.repositories import track_repo
from app.services import library_service
from app.services.audio_quality import QualityInfo, quality_from_probe, quality_note

needs_ffmpeg = pytest.mark.skipif(
    not (find_binary("ffmpeg") and find_binary("ffprobe")), reason="ffmpeg/ffprobe not installed"
)


def _probe(codec, bit_rate=None, sample_rate="44100", fmt_bit_rate=None):
    stream = {"codec_type": "audio", "codec_name": codec, "sample_rate": sample_rate}
    if bit_rate is not None:
        stream["bit_rate"] = str(bit_rate)
    return {"streams": [stream], "format": {"bit_rate": str(fmt_bit_rate) if fmt_bit_rate else None}}


def test_probe_lossy_stream():
    q = quality_from_probe(_probe("mp3", 320000))
    assert q == QualityInfo(codec="mp3", bitrate_kbps=320, sample_rate=44100, lossless=False)


def test_probe_lossless_codecs():
    assert quality_from_probe(_probe("flac", 900000)).lossless is True
    assert quality_from_probe(_probe("pcm_s16le", 1411000)).lossless is True
    assert quality_from_probe(_probe("alac", 800000)).lossless is True


def test_probe_falls_back_to_format_bitrate():
    q = quality_from_probe(_probe("opus", None, "48000", fmt_bit_rate=131000))
    assert q.bitrate_kbps == 131 and q.sample_rate == 48000


def test_probe_ignores_cover_stream_and_handles_garbage():
    info = {"streams": [{"codec_type": "video", "codec_name": "mjpeg"}], "format": {}}
    assert quality_from_probe(info) is None
    assert quality_from_probe(None) is None
    assert quality_from_probe({}) is None


def test_note_lossless_container_from_lossy_origin():
    note = quality_note(QualityInfo("flac", 900, 44100, True), lossy_origin=True)
    assert note and "lossy" in note.lower()


def test_note_lossless_without_known_origin_is_silent():
    assert quality_note(QualityInfo("flac", 900, 44100, True), lossy_origin=False) is None


def test_note_reencoded_above_source_ceiling():
    note = quality_note(QualityInfo("mp3", 320, 44100, False), lossy_origin=True)
    assert note and "320" in note


@pytest.mark.parametrize("codec,kbps", [("opus", 131), ("aac", 129), ("mp3", 128)])
def test_note_original_or_low_bitrate_is_silent(codec, kbps):
    assert quality_note(QualityInfo(codec, kbps, 44100, False), lossy_origin=True) is None


def test_note_without_quality_info():
    assert quality_note(None, lossy_origin=True) is None


def test_repo_roundtrip_new_columns(sandbox, tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    track_id = track_repo.upsert(
        audio, title="T", codec="mp3", bitrate_kbps=320, sample_rate=44100,
        quality_note="note", source_id="youtube:abcdefghijk",
    )
    t = track_repo.get(track_id)
    assert (t.codec, t.bitrate_kbps, t.sample_rate, t.quality_note, t.source_id) == (
        "mp3", 320, 44100, "note", "youtube:abcdefghijk")


def test_old_database_is_migrated_in_place(sandbox):
    """A tracks table created before this feature gains the new columns and keeps its rows."""
    con = sqlite3.connect(str(track_repo.db_path))
    con.execute("DROP TABLE tracks")
    con.execute(
        """CREATE TABLE tracks (id TEXT PRIMARY KEY, job_id TEXT, path TEXT NOT NULL, title TEXT,
           artist TEXT, album TEXT, duration_s REAL, format TEXT, size_bytes INTEGER NOT NULL DEFAULT 0,
           has_cover INTEGER NOT NULL DEFAULT 0, kept INTEGER NOT NULL DEFAULT 0,
           mtime REAL NOT NULL DEFAULT 0, tags_source TEXT)"""
    )
    con.execute("INSERT INTO tracks(id, path, title) VALUES ('old1', '/x/old.mp3', 'Old')")
    con.commit()
    con.close()

    track_repo.ensure_schema()
    track_repo.ensure_schema()  # idempotent

    old = track_repo.get("old1")
    assert old.title == "Old" and old.codec is None and old.quality_note is None


def _make_audio(path, *codec_args):
    subprocess.run(
        [resolve_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         *codec_args, str(path)],
        check=True,
    )


@needs_ffmpeg
def test_register_track_stores_probed_quality(sandbox):
    from app.core.config import settings
    folder = settings.DOWNLOAD_DIR / "audio" / "best"
    folder.mkdir(parents=True)
    audio = folder / "Tone.mp3"
    _make_audio(audio, "-c:a", "libmp3lame", "-b:a", "320k")

    track_id = library_service.register_track(audio, job_id="job1", fmt="mp3")

    t = track_repo.get(track_id)
    assert t.codec == "mp3" and t.bitrate_kbps == 320 and t.sample_rate == 44100
    assert t.quality_note and "320" in t.quality_note  # job_id => known lossy origin


@needs_ffmpeg
def test_register_track_without_origin_has_no_note(sandbox):
    from app.core.config import settings
    folder = settings.DOWNLOAD_DIR / "audio"
    folder.mkdir(parents=True)
    audio = folder / "Mine.flac"
    _make_audio(audio, "-c:a", "flac")

    track_id = library_service.register_track(audio)  # no job, no sidecar: origin unknown

    t = track_repo.get(track_id)
    assert t.codec == "flac" and t.quality_note is None
