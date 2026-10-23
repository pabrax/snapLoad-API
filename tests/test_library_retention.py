"""Library registration at job success, auto-keep and legacy backfill (spec library/track-retention)."""
import sys
from pathlib import Path

from app.core.config import settings
from app.core.enums import MediaType
from app.repositories import download_index_repo, track_repo
from app.services import library_service
from app.services.youtube_service import YouTubeAudioService, YouTubeVideoService

URL = "https://youtu.be/abc"


class OneFileAudio(YouTubeAudioService):
    """Real post-download flow with a scripted command that writes one audio file."""

    def validate_url(self, url):
        pass

    def build_command(self, url, output_path: Path, **kwargs):
        code = f"from pathlib import Path; Path(r'{output_path}', 'Song.mp3').write_bytes(b'x' * 10)"
        return [sys.executable, "-c", code]


class OneFileVideo(YouTubeVideoService):
    def validate_url(self, url):
        pass

    def build_command(self, url, output_path: Path, **kwargs):
        code = f"from pathlib import Path; Path(r'{output_path}', 'Clip.mp4').write_bytes(b'x' * 10)"
        return [sys.executable, "-c", code]


def _run(service, job_id, media="audio", quality="best", fmt="mp3"):
    download_index_repo.register_pending(URL, media, quality, fmt, job_id, "2026-01-01T00:00:00Z")
    service.download_sync(URL, job_id=job_id, quality=quality, format=fmt)


def test_auto_keep_default_true(sandbox):
    assert settings.LIBRARY_AUTO_KEEP is True

    _run(OneFileAudio(), "job1")

    tracks, total = track_repo.list()
    assert total == 1
    track = tracks[0]
    assert (track.kept, track.job_id, track.format, track.size_bytes) == (True, "job1", "mp3", 10)
    assert Path(track.path).name == "Song.mp3" and track.title == "Song"


def test_auto_keep_false(sandbox, monkeypatch):
    monkeypatch.setattr(settings, "LIBRARY_AUTO_KEEP", False)

    _run(OneFileAudio(), "job1")

    assert track_repo.list()[0][0].kept is False


def test_video_downloads_are_not_registered(sandbox):
    _run(OneFileVideo(), "job2", media="video", quality="best", fmt="mp4")

    assert track_repo.list() == ([], 0)


def test_failed_job_registers_nothing(sandbox):
    class Failing(OneFileAudio):
        def build_command(self, url, output_path, **kwargs):
            return [sys.executable, "-c", "import sys; print('ERROR: boom'); sys.exit(1)"]

    _run(Failing(), "job3")

    assert track_repo.list() == ([], 0)


def test_registering_again_keeps_the_user_choice(sandbox):
    path = settings.DOWNLOAD_DIR / "audio" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x")
    library_service.register_track(path, job_id="j1", fmt="mp3")
    track_id = track_repo.list()[0][0].id
    track_repo.set_kept(track_id, False)

    library_service.register_track(path, job_id="j2", fmt="mp3")

    assert track_repo.get(track_id).kept is False


def _ready_entry(name, media="audio", create=True):
    path = settings.DOWNLOAD_DIR / media / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if create:
        path.write_bytes(b"x" * 5)
    download_index_repo.upsert_ready(
        f"https://youtu.be/{name}", media, "best", "mp3", [str(path)], "2026-01-01T00:00:00Z", job_id=name
    )
    return path


def test_backfill_registers_legacy_ready_audio_as_unkept(sandbox):
    legacy = _ready_entry("Old Song.mp3")

    assert library_service.backfill() == 1

    track = track_repo.list()[0][0]
    assert (Path(track.path), track.kept, track.title) == (legacy, False, "Old Song")


def test_backfill_skips_video_missing_files_and_known_tracks(sandbox):
    _ready_entry("Clip.mp4", media="video")
    _ready_entry("Gone.mp3", create=False)
    known = _ready_entry("Known.mp3")
    library_service.register_track(known, job_id="Known.mp3", fmt="mp3", kept=True)

    assert library_service.backfill() == 0
    assert [t.title for t in track_repo.list()[0]] == ["Known"]
    assert track_repo.list()[0][0].kept is True


def test_backfill_is_bounded_per_call(sandbox):
    for i in range(5):
        _ready_entry(f"s{i}.mp3")

    assert library_service.backfill(limit=2) == 2
    assert library_service.backfill(limit=10) == 3
    assert library_service.backfill() == 0
