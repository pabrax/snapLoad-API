"""Track repository: ids, upsert, paging/search, kept flag (spec library/track-index, track-retention)."""
from app.core.config import settings
from app.repositories import TrackRepository, track_id_for, track_repo


def _add(name, **kwargs):
    path = settings.DOWNLOAD_DIR / "audio" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * kwargs.pop("size", 10))
    kwargs.setdefault("job_id", name)
    return track_repo.upsert(path=path, fmt="mp3", size_bytes=path.stat().st_size, **kwargs)


def test_track_id_is_stable_short_hex(sandbox):
    path = settings.DOWNLOAD_DIR / "audio" / "a.mp3"
    first = track_id_for(path)

    assert first == track_id_for(path)
    assert len(first) == 16 and all(c in "0123456789abcdef" for c in first)
    assert first != track_id_for(settings.DOWNLOAD_DIR / "audio" / "b.mp3")


def test_ensure_schema_is_idempotent(sandbox):
    track_repo.ensure_schema()
    track_repo.ensure_schema()
    assert track_repo.list() == ([], 0)


def test_upsert_returns_the_id_and_updates_tags_without_duplicating(sandbox):
    first = _add("a.mp3", title="Old")
    second = _add("a.mp3", title="New", artist="Band")

    assert first == second
    tracks, total = track_repo.list()
    assert total == 1
    assert (tracks[0].title, tracks[0].artist) == ("New", "Band")


def test_upsert_keeps_the_kept_flag_unless_given(sandbox):
    track_id = _add("a.mp3", kept=True)
    _add("a.mp3", title="Retagged")
    assert track_repo.get(track_id).kept is True

    _add("a.mp3", kept=False)
    assert track_repo.get(track_id).kept is False


def test_get_unknown_returns_none(sandbox):
    assert track_repo.get("0" * 16) is None


def test_list_pages_newest_first_and_reports_total(sandbox):
    for i in range(5):
        _add(f"{i}.mp3", title=f"t{i}", mtime=1000.0 + i)

    page, total = track_repo.list(limit=2, offset=1)

    assert total == 5
    assert [t.title for t in page] == ["t3", "t2"]


def test_list_search_matches_title_or_artist_ignoring_case(sandbox):
    _add("a.mp3", title="One More Time", artist="Daft Punk")
    _add("b.mp3", title="DAFT song", artist="Other")
    _add("c.mp3", title="Unrelated", artist="Nobody")

    found, total = track_repo.list(q="daft")

    assert total == 2
    assert {t.title for t in found} == {"One More Time", "DAFT song"}


def test_search_treats_like_wildcards_literally(sandbox):
    _add("a.mp3", title="100% pure")
    _add("b.mp3", title="1000 pure")

    found, total = track_repo.list(q="100%")

    assert total == 1 and found[0].title == "100% pure"


def test_kept_bytes_sums_only_kept_tracks(sandbox):
    _add("a.mp3", size=4, kept=True)
    _add("b.mp3", size=6, kept=True)
    _add("c.mp3", size=100, kept=False)

    assert track_repo.kept_bytes() == 10
    assert len(track_repo.kept_paths()) == 2


def test_set_kept_and_delete(sandbox):
    track_id = _add("a.mp3", kept=True)

    assert track_repo.set_kept(track_id, False).kept is False
    assert track_repo.set_kept("f" * 16, True) is None
    assert track_repo.delete(track_id) is True
    assert track_repo.delete(track_id) is False
    assert track_repo.get(track_id) is None


def test_repository_works_on_a_fresh_database(tmp_path):
    repo = TrackRepository(tmp_path / "fresh.db")
    assert repo.list() == ([], 0)


# --- GET /library/tracks (spec library/track-index, track-retention kept_bytes) ---

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.repositories import download_index_repo


@pytest.fixture
def client(sandbox):
    return TestClient(app)


def _ready(name, job=None, **kwargs):
    """A downloaded audio file that is both in the downloads index and in the library."""
    track_id = _add(name, job_id=job or name, **kwargs)
    path = settings.DOWNLOAD_DIR / "audio" / name
    download_index_repo.upsert_ready(
        f"https://youtu.be/{name}", "audio", "best", "mp3", [str(path)], "2026-01-01T00:00:00Z", job_id=job or name
    )
    return track_id


def test_ready_audio_listed(client):
    track_id = _ready("a.mp3", title="Song", artist="Band", album="LP", duration_s=61.5, kept=True)

    body = client.get("/library/tracks").json()

    assert body["total"] == 1 and body["limit"] == 50 and body["offset"] == 0
    assert body["tracks"][0] == {
        "id": track_id, "title": "Song", "artist": "Band", "album": "LP", "duration_s": 61.5,
        "format": "mp3", "size_bytes": 10, "has_cover": False, "kept": True,
    }


def test_listing_never_exposes_server_paths(client):
    _ready("a.mp3", title="Song")

    assert "path" not in client.get("/library/tracks").json()["tracks"][0]
    assert str(settings.DOWNLOAD_DIR) not in client.get("/library/tracks").text


def test_video_and_failed_excluded(client):
    _ready("a.mp3", title="Audio")
    video = settings.DOWNLOAD_DIR / "video" / "clip.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"x")
    download_index_repo.upsert_ready("https://youtu.be/v", "video", "best", "mp4", [str(video)], "2026-01-01T00:00:00Z", job_id="v")
    download_index_repo.register_pending("https://youtu.be/f", "audio", "best", "mp3", "f", "2026-01-01T00:00:00Z")
    download_index_repo.register_failed("f", "boom")

    titles = [t["title"] for t in client.get("/library/tracks").json()["tracks"]]

    assert titles == ["Audio"]


def test_missing_file_not_listed_and_marked_failed(client):
    _ready("gone.mp3", job="jobgone", title="Gone")
    _ready("here.mp3", title="Here")
    (settings.DOWNLOAD_DIR / "audio" / "gone.mp3").unlink()

    body = client.get("/library/tracks").json()

    assert [t["title"] for t in body["tracks"]] == ["Here"] and body["total"] == 1
    assert download_index_repo.find_by_job_id("jobgone").status == "failed"
    assert track_repo.list()[1] == 1


def test_paging_limit_offset_total(client):
    for i in range(120):
        _add(f"{i:03}.mp3", title=f"t{i}", mtime=1000.0 + i)

    body = client.get("/library/tracks", params={"limit": 50, "offset": 100}).json()

    assert len(body["tracks"]) == 20 and body["total"] == 120 and body["offset"] == 100


def test_search_title_artist_case_insensitive(client):
    _add("a.mp3", title="One More Time", artist="Daft Punk")
    _add("b.mp3", title="Other", artist="Nobody")

    body = client.get("/library/tracks", params={"q": "DAFT"}).json()

    assert [t["title"] for t in body["tracks"]] == ["One More Time"] and body["total"] == 1


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_invalid_paging_422(client, params):
    assert client.get("/library/tracks", params=params).status_code == 422


def test_kept_bytes_sum(client):
    _add("a.mp3", size=4_000_000, kept=True)
    _add("b.mp3", size=6_000_000, kept=True)
    _add("c.mp3", size=1_000, kept=False)

    assert client.get("/library/tracks").json()["kept_bytes"] == 10_000_000
