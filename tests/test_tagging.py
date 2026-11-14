"""Tag writer (mutagen) and title/artist cleanup (feature library-quality-dedup-tags, S2)."""
import subprocess

import pytest

from app.core.process import find_binary, resolve_binary
from app.services import track_metadata
from app.services.tagger import TagData, clean_artist, clean_title, write_tags

needs_ffmpeg = pytest.mark.skipif(
    not (find_binary("ffmpeg") and find_binary("ffprobe")), reason="ffmpeg/ffprobe not installed"
)

CODECS = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
    "m4a": ["-c:a", "aac", "-b:a", "128k"],
    "flac": ["-c:a", "flac"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "3"],
    "opus": ["-c:a", "libopus", "-b:a", "96k"],
}


def make_audio(path, ext):
    subprocess.run(
        [resolve_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         *CODECS[ext], str(path)],
        check=True,
    )
    return path


def make_cover(path):
    subprocess.run(
        [resolve_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
         "-frames:v", "1", str(path)],
        check=True,
    )
    return path.read_bytes()


def audio_md5(path):
    """MD5 of the decoded-container audio packets (stream copy): unchanged iff the audio is untouched."""
    out = subprocess.run(
        [resolve_binary("ffmpeg"), "-v", "error", "-i", str(path), "-map", "0:a", "-c", "copy", "-f", "md5", "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    return out.strip()


DATA = TagData(title="Karma Police", artist="Radiohead", album="OK Computer", year="1997", track_no=6,
               mb_recording_id="11111111-1111-1111-1111-111111111111",
               mb_release_id="22222222-2222-2222-2222-222222222222")


@needs_ffmpeg
@pytest.mark.parametrize("ext", sorted(CODECS))
def test_tags_and_cover_roundtrip_and_audio_untouched(tmp_path, ext):
    audio = make_audio(tmp_path / f"a.{ext}", ext)
    cover = make_cover(tmp_path / "c.jpg")
    before = audio_md5(audio)

    assert write_tags(audio, DATA, cover=cover) is True

    tags = track_metadata.read_tags(audio)
    assert (tags.title, tags.artist, tags.album) == ("Karma Police", "Radiohead", "OK Computer")
    assert tags.has_cover is True or ext in ("ogg", "opus")  # ffprobe shows ogg/opus pictures only as tags
    assert audio_md5(audio) == before, "tagging must not touch the audio stream"


@needs_ffmpeg
@pytest.mark.parametrize("ext", ["mp3", "m4a", "flac", "ogg", "opus"])
def test_year_and_track_number_are_written(tmp_path, ext):
    audio = make_audio(tmp_path / f"a.{ext}", ext)
    write_tags(audio, DATA)

    info = track_metadata.probe(audio)
    tags = track_metadata._embedded(info)
    assert str(tags.get("date") or tags.get("year")).startswith("1997")
    assert str(tags.get("track")).split("/")[0] == "6"


@needs_ffmpeg
def test_tagging_a_cover_replaces_the_previous_one(tmp_path):
    audio = make_audio(tmp_path / "a.mp3", "mp3")
    cover = make_cover(tmp_path / "c.jpg")
    write_tags(audio, DATA, cover=cover)
    write_tags(audio, DATA, cover=cover)
    pics = [s for s in track_metadata.probe(audio)["streams"] if s["codec_type"] == "video"]
    assert len(pics) == 1


def test_missing_values_never_blank_existing_tags(tmp_path):
    from mutagen.id3 import ID3, TIT2
    audio = tmp_path / "x.mp3"
    audio.write_bytes(b"")
    if find_binary("ffmpeg"):
        make_audio(audio, "mp3")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Keep Me"))
    tags.save(str(audio))

    write_tags(audio, TagData(title=None, artist="New Artist"))

    from mutagen.easyid3 import EasyID3
    assert EasyID3(str(audio))["title"] == ["Keep Me"] and EasyID3(str(audio))["artist"] == ["New Artist"]


def test_unsupported_or_corrupt_file_returns_false_without_raising(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF....WAVE")
    assert write_tags(wav, DATA) is False
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not audio at all")
    assert write_tags(junk, DATA) in (True, False)  # must not raise
    assert write_tags(tmp_path / "missing.mp3", DATA) is False


@pytest.mark.parametrize("raw,expected", [
    ("Radiohead - Topic", "Radiohead"),
    ("RadioheadVEVO", "Radiohead"),
    ("Radiohead VEVO", "Radiohead"),
    ("  Radiohead  ", "Radiohead"),
    ("Daft Punk", "Daft Punk"),
    ("Topic", "Topic"),
    (None, None),
    ("", None),
])
def test_clean_artist(raw, expected):
    assert clean_artist(raw) == expected


@pytest.mark.parametrize("raw,artist,expected", [
    ("Radiohead - Karma Police (Official Video)", "Radiohead", "Karma Police"),
    ("Karma Police [Official Audio]", "Radiohead", "Karma Police"),
    ("Karma Police (Lyrics)", None, "Karma Police"),
    ("Karma Police (Official Music Video) [4K]", None, "Karma Police"),
    ("Song (feat. Someone)", None, "Song (feat. Someone)"),
    ("Song (Live at Wembley)", None, "Song (Live at Wembley)"),
    ("Song (Remastered 2011)", None, "Song (Remastered 2011)"),
    ("Just A Title", "Other Artist", "Just A Title"),
    ("Artist - Song - Part 2", "Artist", "Song - Part 2"),
    ("(Official Video)", None, "(Official Video)"),   # never reduce a title to nothing
])
def test_clean_title(raw, artist, expected):
    assert clean_title(raw, artist) == expected
