"""Cancelling a running job must end as 'cancelled' (not 'failed') and free the cache key."""
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.core.enums import MediaType
from app.managers import job_manager, metadata_manager
from app.repositories import download_index_repo
from app.services.base_download_service import BaseDownloadService

URL = "https://www.youtube.com/watch?v=abc"


class SlowService(BaseDownloadService):
    def get_source_name(self):
        return "yt"

    def get_media_type(self):
        return MediaType.AUDIO

    def get_file_extensions(self):
        return {".mp3"}

    def validate_url(self, url):
        pass

    def build_command(self, url, output_path: Path, **kwargs):
        return [sys.executable, "-c", "import time; time.sleep(60)"]


@pytest.fixture
def running_job(sandbox):
    download_index_repo.register_pending(URL, "audio", "192", "mp3", "jc", "2026-01-01T00:00:00Z")
    thread = threading.Thread(
        target=SlowService().download_sync, args=(URL,), kwargs={"job_id": "jc", "quality": "192", "format": "mp3"}
    )
    thread.start()
    for _ in range(50):
        if job_manager.has_job("jc"):
            break
        time.sleep(0.1)
    assert job_manager.has_job("jc")
    yield thread
    job_manager.terminate_job("jc")
    thread.join(10)


def test_terminate_job_ends_as_cancelled(running_job):
    assert job_manager.terminate_job("jc") is True
    running_job.join(15)
    assert not running_job.is_alive()

    meta = metadata_manager.read_metadata("jc")
    assert meta.status == "cancelled" and meta.files == []
    entry = download_index_repo.lookup(URL, "audio", "192", "mp3")
    assert entry.status == "failed" and "cancel" in entry.error.lower()


def test_cancel_endpoint_cancels_running_job(running_job):
    res = TestClient(app).post("/cancel/jc")
    assert res.status_code == 200 and res.json() == {"job_id": "jc", "cancelled": True}
    running_job.join(15)
    assert metadata_manager.read_metadata("jc").status == "cancelled"


def test_cancel_unknown_job_is_404(sandbox):
    assert TestClient(app).post("/cancel/nope").status_code == 404
