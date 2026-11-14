"""Canonical source ids and duplicate detection (feature library-quality-dedup-tags, S1)."""
import pytest

from app.core.source_id import canonical_source_id

YT = "youtube:dQw4w9WgXcQ"


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "http://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
    "https://music.youtube.com/watch?v=dQw4w9WgXcQ&si=abc123",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ?si=tracking&t=42",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
    "https://www.youtube.com/live/dQw4w9WgXcQ?feature=share",
    "HTTPS://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ",
])
def test_youtube_variants_share_one_id(url):
    assert canonical_source_id(url) == YT


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123",   # yt-dlp would download the whole list
    "https://www.youtube.com/playlist?list=PL123",
    "https://www.youtube.com/@channel",
    "https://www.youtube.com/watch?v=short",
    "https://www.youtube.com/watch",
    "https://youtu.be/",
])
def test_playlists_and_non_tracks_have_no_id(url):
    assert canonical_source_id(url) is None


@pytest.mark.parametrize("url", [
    "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
    "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC?si=abcdef",
    "https://open.spotify.com/intl-es/track/4uLU6hMCjMI75M1A2tKUQC",
])
def test_spotify_track_variants_share_one_id(url):
    assert canonical_source_id(url) == "spotify:4uLU6hMCjMI75M1A2tKUQC"


@pytest.mark.parametrize("url", [
    "https://open.spotify.com/album/4uLU6hMCjMI75M1A2tKUQC",
    "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
])
def test_spotify_collections_have_no_id(url):
    assert canonical_source_id(url) is None


@pytest.mark.parametrize("url", ["", None, "not a url", "https://example.com/watch?v=dQw4w9WgXcQ", "ftp://x"])
def test_unknown_input_has_no_id(url):
    assert canonical_source_id(url) is None


# --- T3: reuse across URL variants -------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from app.repositories import download_index_repo, track_repo  # noqa: E402
from app.services import download_orchestrator, library_service  # noqa: E402

URL_A = "https://youtu.be/dQw4w9WgXcQ?si=share"
URL_B = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _ready(tmp_path, url, quality="best", fmt="mp3", name="song.mp3", media="audio"):
    f = tmp_path / name
    f.write_bytes(b"x" * 10)
    download_index_repo.upsert_ready(url, media, quality, fmt, [str(f)], "2026-01-01T00:00:00Z", job_id="job1")
    return str(f)


def test_variant_url_reuses_existing_file(sandbox):
    path = _ready(sandbox, URL_A)

    res = download_orchestrator.check_availability(URL_B, "audio", "best", "mp3")

    assert res.status == "ready" and res.files == [path] and res.source == "dedup"
    assert res.job_id == "job1"


def test_exact_url_still_reports_cache(sandbox):
    _ready(sandbox, URL_A)
    assert download_orchestrator.check_availability(URL_A, "audio", "best", "mp3").source == "cache"


def test_different_quality_or_format_is_not_a_duplicate(sandbox):
    _ready(sandbox, URL_A, quality="best", fmt="mp3")
    assert download_orchestrator.check_availability(URL_B, "audio", "192", "mp3").status == "miss"
    assert download_orchestrator.check_availability(URL_B, "audio", "best", "ogg").status == "miss"


def test_video_and_audio_do_not_mix(sandbox):
    _ready(sandbox, URL_A, name="clip.mp4", media="video")
    assert download_orchestrator.check_availability(URL_B, "audio", "best", "mp3").status == "miss"


def test_playlist_url_never_dedups(sandbox):
    _ready(sandbox, URL_A)
    assert download_orchestrator.check_availability(URL_B + "&list=PL1", "audio", "best", "mp3").status == "miss"


def test_missing_file_is_not_reused(sandbox):
    path = _ready(sandbox, URL_A)
    import os
    os.remove(path)
    assert download_orchestrator.check_availability(URL_B, "audio", "best", "mp3").status == "miss"


def test_in_progress_variant_is_reported_pending(sandbox):
    download_index_repo.register_pending(URL_A, "audio", "best", "mp3", "jobP", "2026-01-01T00:00:00Z")
    res = download_orchestrator.check_availability(URL_B, "audio", "best", "mp3")
    assert res.status == "pending" and res.job_id == "jobP"


def test_post_download_variant_does_not_enqueue(sandbox, monkeypatch):
    calls = []
    monkeypatch.setattr(download_orchestrator, "initiate_download", lambda **kw: calls.append(kw))
    path = _ready(sandbox, URL_A)

    res = TestClient(app).post("/download", json={"url": URL_B})

    assert res.status_code == 200 and res.json()["status"] == "ready" and res.json()["files"] == [path]
    assert calls == []


# --- possible duplicates in the library (never deletes) ----------------------------------------


def _track(sandbox, name, title, artist, duration):
    f = sandbox / name
    f.write_bytes(b"x" * 10)
    return track_repo.upsert(f, title=title, artist=artist, duration_s=duration)


def test_duplicates_group_same_song_ignoring_case_and_small_duration_gap(sandbox):
    a = _track(sandbox, "a.mp3", "Song One", "The Band", 200.0)
    b = _track(sandbox, "b.mp3", " song one ", "the band", 201.5)
    _track(sandbox, "c.mp3", "Song Two", "The Band", 200.0)

    groups = library_service.find_duplicates()

    assert [sorted(g) for g in groups] == [sorted([a, b])]


def test_duplicates_need_artist_and_title_and_close_duration(sandbox):
    _track(sandbox, "a.mp3", "Song", "Band", 200.0)
    _track(sandbox, "b.mp3", "Song", "Band", 260.0)      # different duration: a live/extended version
    _track(sandbox, "c.mp3", "Untitled", None, 100.0)    # no artist: not enough to claim a duplicate
    _track(sandbox, "d.mp3", "Untitled", None, 100.0)
    assert library_service.find_duplicates() == []


def test_duplicates_by_same_source_id(sandbox):
    f1, f2 = sandbox / "x1.mp3", sandbox / "x2.mp3"
    f1.write_bytes(b"x"); f2.write_bytes(b"x")
    a = track_repo.upsert(f1, title="A", source_id="youtube:dQw4w9WgXcQ")
    b = track_repo.upsert(f2, title="B", source_id="youtube:dQw4w9WgXcQ")
    assert [sorted(g) for g in library_service.find_duplicates()] == [sorted([a, b])]


def test_duplicates_endpoint_and_nothing_is_deleted(sandbox):
    a = _track(sandbox, "a.mp3", "Song", "Band", 200.0)
    b = _track(sandbox, "b.mp3", "Song", "Band", 200.5)

    res = TestClient(app).get("/library/duplicates")

    assert res.status_code == 200
    groups = res.json()["groups"]
    assert len(groups) == 1 and {t["id"] for t in groups[0]} == {a, b}
    assert "path" not in groups[0][0]
    assert (sandbox / "a.mp3").exists() and (sandbox / "b.mp3").exists()
    assert track_repo.get(a) and track_repo.get(b)


def test_register_track_stores_canonical_source_id_from_sidecar(sandbox):
    from app.services import track_metadata
    from app.core.config import settings
    folder = settings.DOWNLOAD_DIR / "audio"
    folder.mkdir(parents=True)
    audio = folder / "Song.mp3"
    audio.write_bytes(b"x" * 10)
    track_metadata.write_sidecar(audio, {"title": "Song", "source_url": URL_B, "source_id": "dQw4w9WgXcQ"})

    track_id = library_service.register_track(audio, job_id="job1")

    assert track_repo.get(track_id).source_id == YT


def test_register_track_source_id_from_job_url_for_spotify(sandbox):
    from app.core.config import settings
    sp = "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC?si=x"
    download_index_repo.register_pending(sp, "audio", "best", "mp3", "jobS", "2026-01-01T00:00:00Z")
    folder = settings.DOWNLOAD_DIR / "audio"
    folder.mkdir(parents=True)
    audio = folder / "Sp.mp3"
    audio.write_bytes(b"x" * 10)

    track_id = library_service.register_track(audio, job_id="jobS")

    assert track_repo.get(track_id).source_id == "spotify:4uLU6hMCjMI75M1A2tKUQC"
