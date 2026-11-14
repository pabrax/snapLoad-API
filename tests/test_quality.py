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


# --- T6: ReplayGain (tag only, audio untouched) -------------------------------------------------------

import hashlib  # noqa: E402

from app.services import audio_quality, enrichment  # noqa: E402
from app.services.tagger import write_replaygain  # noqa: E402


def _audio_md5(path):
    return subprocess.run(
        [resolve_binary("ffmpeg"), "-v", "error", "-i", str(path), "-map", "0:a", "-c", "copy", "-f", "md5", "-"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _tone(path, volume_db, *codec):
    subprocess.run(
        [resolve_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-af", f"volume={volume_db}dB", *codec, str(path)],
        check=True,
    )
    return path


@needs_ffmpeg
def test_loudness_and_gain_follow_the_replaygain_reference(tmp_path):
    quiet = audio_quality.measure_loudness(_tone(tmp_path / "q.flac", -30, "-c:a", "flac"))
    # ffmpeg's sine is generated at -18 dBFS, so +14 dB lands above the -18 LUFS reference
    loud = audio_quality.measure_loudness(_tone(tmp_path / "l.flac", 14, "-c:a", "flac"))

    assert quiet is not None and loud is not None and quiet < loud
    assert round(loud - quiet) == 44                       # 44 dB apart, as generated
    # RG2 reference is -18 LUFS: a quiet track gets a positive gain, a loud one a negative gain
    assert audio_quality.replaygain_db(quiet) > 0 > audio_quality.replaygain_db(loud)
    assert audio_quality.replaygain_db(-18.0) == 0.0


def test_measure_loudness_never_raises(tmp_path):
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not audio")
    assert audio_quality.measure_loudness(junk) is None
    assert audio_quality.measure_loudness(tmp_path / "missing.mp3") is None


@needs_ffmpeg
@pytest.mark.parametrize("ext,codec", [
    ("mp3", ["-c:a", "libmp3lame", "-b:a", "128k"]),
    ("m4a", ["-c:a", "aac", "-b:a", "128k"]),
    ("flac", ["-c:a", "flac"]),
    ("ogg", ["-c:a", "libvorbis", "-q:a", "3"]),
    ("opus", ["-c:a", "libopus", "-b:a", "96k"]),
])
def test_replaygain_tag_written_and_audio_untouched(tmp_path, ext, codec):
    audio = _tone(tmp_path / f"a.{ext}", -20, *codec)
    before = _audio_md5(audio)

    assert write_replaygain(audio, loudness_lufs=-26.0) is True

    from mutagen import File
    tags = File(str(audio), easy=False).tags
    flat = {str(k).lower(): str(v) for k, v in tags.items()}
    if ext == "opus":
        # Ogg Opus uses R128_TRACK_GAIN in Q7.8 dB relative to -23 LUFS: -23 - (-26) = +3 dB = 768
        assert any(k == "r128_track_gain" and "768" in v for k, v in flat.items())
    else:
        # RG2 reference -18 LUFS: -18 - (-26) = +8.00 dB
        assert any("replaygain_track_gain" in k and "+8.00 dB" in v for k, v in flat.items()), flat
    assert _audio_md5(audio) == before


def test_replaygain_unsupported_or_missing_returns_false(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF....WAVE")
    assert write_replaygain(wav, -20.0) is False
    assert write_replaygain(tmp_path / "nope.mp3", -20.0) is False


@needs_ffmpeg
def test_register_track_for_a_download_stores_replaygain(sandbox):
    from app.core.config import settings
    folder = settings.DOWNLOAD_DIR / "audio"
    folder.mkdir(parents=True)
    audio = _tone(folder / "Tone.mp3", -26, "-c:a", "libmp3lame", "-b:a", "128k")

    gain = enrichment.tag_loudness(audio)                  # runs BEFORE the file is moved/published
    track_id = library_service.register_track(audio, job_id="job1", fmt="mp3")

    assert gain is not None and gain > 0                   # quiet tone => positive gain
    assert track_repo.get(track_id).replaygain_db == gain  # registration only READS the tag
    from mutagen.id3 import ID3
    assert any("replaygain_track_gain" in str(k).lower() for k in ID3(str(audio)).keys())


@needs_ffmpeg
def test_library_files_without_a_job_are_not_modified(sandbox):
    """Only fresh downloads get tags written; a user's own file is only read."""
    from app.core.config import settings
    folder = settings.DOWNLOAD_DIR / "audio"
    folder.mkdir(parents=True)
    audio = _tone(folder / "Mine.mp3", -26, "-c:a", "libmp3lame", "-b:a", "128k")
    before = hashlib.sha256(audio.read_bytes()).hexdigest()

    library_service.register_track(audio)
    library_service.register_track(audio, job_id="oldjob")   # backfill path: job known, but no analysis

    assert hashlib.sha256(audio.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("tags,expected", [
    ({"replaygain_track_gain": "+8.00 dB"}, 8.0),
    ({"replaygain_track_gain": "-3.5 dB"}, -3.5),
    ({"r128_track_gain": "768"}, 8.0),          # +3 dB vs -23 LUFS == +8 dB vs -18 LUFS
    ({"r128_track_gain": "-256"}, 4.0),
    ({}, None),
    ({"replaygain_track_gain": "junk"}, None),
    ({"r128_track_gain": "junk"}, None),
])
def test_replaygain_is_read_back_from_tags(tags, expected):
    assert audio_quality.replaygain_from_tags(tags) == expected


@needs_ffmpeg
def test_register_track_never_modifies_the_file(sandbox):
    """Registration (also used inside GET /library/tracks via backfill) is read-only."""
    from app.core.config import settings
    folder = settings.DOWNLOAD_DIR / "audio"
    folder.mkdir(parents=True)
    audio = _tone(folder / "Mine.mp3", -26, "-c:a", "libmp3lame", "-b:a", "128k")
    before = hashlib.sha256(audio.read_bytes()).hexdigest()
    library_service.register_track(audio, job_id="job1", fmt="mp3")
    assert hashlib.sha256(audio.read_bytes()).hexdigest() == before
