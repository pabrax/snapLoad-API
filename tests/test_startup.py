"""On startup, pending rows left by a previous process are failed so their URLs can be requested again."""
from fastapi.testclient import TestClient

from app.api import app
from app.core.config import cleanup_settings
from app.repositories import download_index_repo as repo

URL = "https://www.youtube.com/watch?v=abc"


def test_orphan_pending_rows_are_failed_on_startup(sandbox, monkeypatch):
    monkeypatch.setattr(cleanup_settings, "CLEANUP_SCHEDULE_ENABLED", False)
    repo.register_pending(URL, "audio", "192", "mp3", "crashed", "2020-01-01T00:00:00Z")
    assert repo.lookup(URL, "audio", "192", "mp3").status == "pending"

    with TestClient(app):
        pass  # entering the context runs the lifespan startup

    entry = repo.lookup(URL, "audio", "192", "mp3")
    assert entry.status == "failed" and "interrupted" in entry.error.lower()
