"""Download index must keep working after failed attempts and with legacy NULL rows."""
from app.repositories import download_index_repo as repo

URL = "https://youtu.be/x"


def test_lookup_returns_ready_after_an_earlier_failed_attempt(sandbox, tmp_path):
    f = tmp_path / "v.webm"
    f.write_bytes(b"x")
    repo.register_pending(URL, "video", None, "webm", "job1", "2026-01-01T00:00:00Z")
    repo.register_failed("job1", "boom")
    repo.register_pending(URL, "video", None, "webm", "job2", "2026-01-01T00:01:00Z")
    repo.register_success("job2", [str(f)])

    entry = repo.lookup(URL, "video", None, "webm")
    assert (entry.status, entry.job_id) == ("ready", "job2")


def test_lookup_prefers_newest_when_no_ready_row(sandbox):
    repo.register_pending(URL, "video", None, "webm", "job1", "2026-01-01T00:00:00Z")
    repo.register_failed("job1", "boom")
    repo.register_pending(URL, "video", None, "webm", "job2", "2026-01-01T00:01:00Z")

    assert repo.lookup(URL, "video", None, "webm").job_id == "job2"


def test_non_null_keys_upsert_instead_of_duplicating(sandbox):
    repo.register_pending(URL, "audio", "192", "mp3", "job1", "2026-01-01T00:00:00Z")
    repo.register_failed("job1", "boom")
    repo.register_pending(URL, "audio", "192", "mp3", "job2", "2026-01-01T00:01:00Z")

    con = repo._connect()
    try:
        assert con.execute("SELECT COUNT(*) FROM downloads").fetchone()[0] == 1
    finally:
        con.close()
    assert repo.lookup(URL, "audio", "192", "mp3").job_id == "job2"


def test_fail_pending_before_only_touches_older_pending_rows(sandbox, tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    repo.register_pending(URL, "audio", "192", "mp3", "old", "2026-01-01T00:00:00Z")
    repo.register_pending(URL, "audio", "128", "mp3", "new", "2026-01-02T00:00:00Z")
    repo.register_pending(URL, "audio", "best", "mp3", "done", "2026-01-01T00:00:00Z")
    repo.register_success("done", [str(f)])

    assert repo.fail_pending_before("2026-01-01T12:00:00Z", "interrupted") == 1

    old = repo.lookup(URL, "audio", "192", "mp3")
    assert (old.status, old.error) == ("failed", "interrupted")
    assert repo.lookup(URL, "audio", "128", "mp3").status == "pending"
    assert repo.lookup(URL, "audio", "best", "mp3").status == "ready"
