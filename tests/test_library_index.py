"""Track repository: ids, upsert, paging/search, kept flag (spec library/track-index, track-retention)."""
from app.core.config import settings
from app.repositories import TrackRepository, track_id_for, track_repo


def _add(name, **kwargs):
    path = settings.DOWNLOAD_DIR / "audio" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * kwargs.pop("size", 10))
    return track_repo.upsert(path=path, job_id=name, fmt="mp3", size_bytes=path.stat().st_size, **kwargs)


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
