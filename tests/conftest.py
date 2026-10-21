"""Shared fixtures: isolate every test from the real downloads/, meta/, logs/ and SQLite files."""
import pytest

from app.core.config import settings
from app.repositories import download_index_repo, media_repo


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect storage directories and both SQLite repositories to a temp dir."""
    for name in ("DOWNLOAD_DIR", "LOGS_DIR", "META_DIR", "TMP_DIR"):
        monkeypatch.setattr(settings, name, tmp_path / name.lower().removesuffix("_dir"))
    db = tmp_path / "downloads.db"
    for repo in (download_index_repo, media_repo):
        monkeypatch.setattr(repo, "db_path", db)
        repo.ensure_schema()
    return tmp_path
