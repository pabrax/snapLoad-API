"""POST /download and GET /lookup for audio: validation, canonical options and cache reuse."""
import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.repositories import download_index_repo
from app.services import download_orchestrator

YT = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
SP = "https://open.spotify.com/track/" + "a" * 22


@pytest.fixture
def client(sandbox, monkeypatch):
    calls = []

    def fake_initiate(**kwargs):
        calls.append(kwargs)
        return {"job_id": "job1", "status": "pending", "source": "youtube_audio"}

    monkeypatch.setattr(download_orchestrator, "initiate_download", fake_initiate)
    test_client = TestClient(app)
    test_client.calls = calls
    return test_client


def test_download_without_quality_uses_canonical_defaults(client):
    res = client.post("/download", json={"url": YT})
    assert res.status_code == 202
    assert client.calls[0]["quality"] == "best" and client.calls[0]["format_"] == "mp3"


def test_download_passes_bitrate_and_format(client):
    client.post("/download", json={"url": YT, "quality": "192k", "format": "OPUS"})
    assert (client.calls[0]["quality"], client.calls[0]["format_"]) == ("192", "opus")


def test_download_lossless_ignores_bitrate(client):
    client.post("/download", json={"url": YT, "quality": "320", "format": "flac"})
    assert (client.calls[0]["quality"], client.calls[0]["format_"]) == ("lossless", "flac")


@pytest.mark.parametrize(
    "payload",
    [
        {"url": YT, "quality": "999"},
        {"url": YT, "quality": "bestaudio2"},
        {"url": YT, "format": "mp4"},
        {"url": SP, "format": "aac"},
        {"url": "https://example.com/x"},
    ],
)
def test_invalid_requests_are_400_and_never_start_a_job(client, payload):
    res = client.post("/download", json=payload)
    assert res.status_code == 400, res.text
    assert client.calls == []


def test_spotify_url_is_not_confused_by_substring(client):
    # a YouTube URL that merely contains the word "spotify" must use YouTube rules (aac allowed)
    res = client.post("/download", json={"url": YT + "&t=spotify", "format": "aac"})
    assert res.status_code == 202


def test_ready_entry_is_reused_without_starting_a_job(client, tmp_path):
    f = tmp_path / "song.opus"
    f.write_bytes(b"x")
    download_index_repo.upsert_ready(YT, "audio", "192", "opus", [str(f)], "2026-01-01T00:00:00Z", job_id="old")

    res = client.post("/download", json={"url": YT, "quality": "192", "format": "opus"})
    assert res.status_code == 200 and res.json()["status"] == "ready"
    assert client.calls == []


def test_different_format_is_a_cache_miss(client, tmp_path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    download_index_repo.upsert_ready(YT, "audio", "192", "mp3", [str(f)], "2026-01-01T00:00:00Z", job_id="old")

    client.post("/download", json={"url": YT, "quality": "192", "format": "flac"})
    assert len(client.calls) == 1


def test_lookup_reports_canonical_audio_options(client):
    res = client.get("/lookup", params={"url": YT, "type": "audio", "quality": "192k", "format": "OPUS"})
    assert res.status_code == 200
    body = res.json()
    assert (body["status"], body["quality"], body["format"]) == ("miss", "192", "opus")


def test_lookup_rejects_invalid_audio_format(client):
    assert client.get("/lookup", params={"url": YT, "type": "audio", "format": "mp4"}).status_code == 400
