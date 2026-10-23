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


# --- PATCH /library/tracks/{id} ---

import pytest
from fastapi.testclient import TestClient

from app.api import app


@pytest.fixture
def client(sandbox):
    return TestClient(app)


def _track(kept):
    path = settings.DOWNLOAD_DIR / "audio" / "a.mp3"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return track_repo.upsert(path=path, job_id="j", fmt="mp3", size_bytes=1, title="A", kept=kept)


def test_patch_unkeep(client):
    track_id = _track(kept=True)

    res = client.patch(f"/library/tracks/{track_id}", json={"kept": False})

    assert res.status_code == 200
    assert res.json()["kept"] is False and res.json()["id"] == track_id and "path" not in res.json()
    assert track_repo.get(track_id).kept is False

    assert client.patch(f"/library/tracks/{track_id}", json={"kept": True}).json()["kept"] is True


@pytest.mark.parametrize("body", [{"kept": "yes"}, {"kept": 1}, {}, {"kept": None}])
def test_patch_invalid_body_422(client, body):
    track_id = _track(kept=True)

    assert client.patch(f"/library/tracks/{track_id}", json=body).status_code == 422
    assert track_repo.get(track_id).kept is True


def test_patch_unknown_track_404(client):
    assert client.patch(f"/library/tracks/{'0' * 16}", json={"kept": True}).status_code == 404
    assert client.patch("/library/tracks/zzz", json={"kept": True}).status_code == 404


# --- cleanup respects kept tracks ---

import os
import time

from app.core.config import cleanup_settings
from app.services import track_metadata
from app.services.cleanup_service import cleanup_service


def _old_track(name, kept, age_hours=5):
    audio = settings.DOWNLOAD_DIR / "audio" / name
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"x" * 10)
    sidecar = track_metadata.write_sidecar(audio, {"title": name})
    past = time.time() - age_hours * 3600
    for f in (audio, sidecar):
        os.utime(f, (past, past))
    download_index_repo.upsert_ready(
        f"https://youtu.be/{name}", "audio", "best", "mp3", [str(audio)], "2026-01-01T00:00:00Z", job_id=name
    )
    track_id = track_repo.upsert(path=audio, job_id=name, fmt="mp3", size_bytes=10, title=name, kept=kept)
    return audio, sidecar, track_id


def test_cleanup_skips_kept_old_track(sandbox, monkeypatch):
    monkeypatch.setattr(cleanup_settings, "RETENTION_HOURS", 1.0)
    audio, sidecar, track_id = _old_track("kept.mp3", kept=True)

    stats = cleanup_service.cleanup_downloads(dry_run=False)

    assert audio.exists() and sidecar.exists()
    assert stats.files_deleted == 0
    assert track_repo.get(track_id) is not None


def test_cleanup_removes_unkept_old_track_and_row(sandbox, monkeypatch):
    monkeypatch.setattr(cleanup_settings, "RETENTION_HOURS", 1.0)
    audio, sidecar, track_id = _old_track("temp.mp3", kept=False)
    cover = settings.DOWNLOAD_DIR / ".covers" / f"{track_id}.jpg"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"jpg")

    cleanup_service.cleanup_downloads(dry_run=False)

    assert not audio.exists() and not sidecar.exists() and not cover.exists()
    assert track_repo.get(track_id) is None


def test_cleanup_keeps_young_unkept_tracks(sandbox, monkeypatch):
    monkeypatch.setattr(cleanup_settings, "RETENTION_HOURS", 24.0)
    audio, _, track_id = _old_track("young.mp3", kept=False, age_hours=1)

    cleanup_service.cleanup_downloads(dry_run=False)

    assert audio.exists() and track_repo.get(track_id) is not None


def test_dry_run_does_not_count_kept(sandbox, monkeypatch):
    monkeypatch.setattr(cleanup_settings, "RETENTION_HOURS", 1.0)
    kept_audio, kept_sidecar, _ = _old_track("kept.mp3", kept=True)
    temp_audio, temp_sidecar, temp_id = _old_track("temp.mp3", kept=False)

    stats = cleanup_service.cleanup_downloads(dry_run=True)

    assert stats.files_deleted == 2  # only the unkept audio and its sidecar
    assert all(f.exists() for f in (kept_audio, kept_sidecar, temp_audio, temp_sidecar))
    assert track_repo.get(temp_id) is not None


def test_cleanup_database_leaves_kept_tracks(sandbox, monkeypatch):
    monkeypatch.setattr(cleanup_settings, "RETENTION_HOURS", 1.0)
    audio, _, track_id = _old_track("kept.mp3", kept=True)

    cleanup_service.cleanup_database(max_age_hours=1.0, dry_run=False)

    assert track_repo.get(track_id) is not None
    assert download_index_repo.find_by_job_id("kept.mp3").status == "ready"
