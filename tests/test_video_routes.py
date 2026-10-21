"""POST /download/video and GET /lookup?type=video: validation, canonical options, cache keys."""
import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.repositories import download_index_repo
from app.services import download_orchestrator

YT = "https://www.youtube.com/watch?v=2PuFyjAs7JA"


@pytest.fixture
def client(sandbox, monkeypatch):
    calls = []

    def fake_initiate(**kwargs):
        calls.append(kwargs)
        return {"job_id": "job1", "status": "pending", "source": "youtube_video"}

    monkeypatch.setattr(download_orchestrator, "initiate_download", fake_initiate)
    test_client = TestClient(app)
    test_client.calls = calls
    return test_client


def test_default_request_is_canonical_and_never_null(client):
    res = client.post("/download/video", json={"url": YT})
    assert res.status_code == 202
    assert (client.calls[0]["quality"], client.calls[0]["format_"]) == ("best", "webm")
    assert (res.json()["resolution"], res.json()["format"]) == ("best", "webm")


def test_resolution_and_format_are_passed_on(client):
    client.post("/download/video", json={"url": YT, "format": "MP4", "resolution": "1080"})
    assert (client.calls[0]["quality"], client.calls[0]["format_"]) == ("1080p", "mp4")


@pytest.mark.parametrize(
    "payload",
    [
        {"url": YT, "resolution": "999p"},
        {"url": YT, "format": "flv"},
        {"url": YT, "format": "mov", "resolution": "2160p"},
        {"url": "https://open.spotify.com/track/" + "a" * 22},
    ],
)
def test_invalid_video_requests_are_400(client, payload):
    assert client.post("/download/video", json=payload).status_code == 400
    assert client.calls == []


def test_ready_entry_is_reused_per_resolution(client, tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    download_index_repo.upsert_ready(YT, "video", "720p", "mp4", [str(f)], "2026-01-01T00:00:00Z", job_id="old")

    hit = client.post("/download/video", json={"url": YT, "format": "mp4", "resolution": "720p"})
    assert hit.status_code == 200 and hit.json()["status"] == "ready" and client.calls == []

    client.post("/download/video", json={"url": YT, "format": "mp4", "resolution": "1080p"})
    assert len(client.calls) == 1


def test_lookup_video_reports_canonical_options(client):
    res = client.get("/lookup", params={"url": YT, "type": "video", "format": "MKV", "resolution": "720"})
    assert res.status_code == 200
    body = res.json()
    assert (body["status"], body["format"], body["resolution"]) == ("miss", "mkv", "720p")


def test_lookup_video_rejects_invalid_resolution(client):
    assert client.get("/lookup", params={"url": YT, "type": "video", "resolution": "9p"}).status_code == 400
