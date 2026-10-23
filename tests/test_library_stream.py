"""GET /library/tracks/{id}/stream: inline audio with HTTP Range (spec library/track-streaming)."""
import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient


def test_installed_fileresponse_ignores_range(tmp_path):
    """Characterization (design decision 7): starlette 0.27 FileResponse has no Range support.

    If this starts failing after an upgrade, the custom streamer can shrink to headers + MIME.
    """
    audio = tmp_path / "a.mp3"
    audio.write_bytes(bytes(range(256)) * 40)
    app = FastAPI()
    app.get("/f")(lambda: FileResponse(audio, media_type="audio/mpeg"))

    res = TestClient(app).get("/f", headers={"Range": "bytes=1000-1999"})

    assert res.status_code == 200
    assert len(res.content) == 10240
    assert "content-range" not in res.headers and "accept-ranges" not in res.headers


@pytest.mark.xfail(strict=True, reason="stream route lands in task 1.3")
def test_range_middle_206(sandbox):
    from app.api import app
    from app.repositories import track_repo

    audio = sandbox / "download" / "audio" / "a.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(bytes(range(256)) * 40)
    track_id = track_repo.upsert(path=audio, job_id="job1", fmt="mp3", size_bytes=audio.stat().st_size)

    res = TestClient(app).get(f"/library/tracks/{track_id}/stream", headers={"Range": "bytes=1000-1999"})

    assert res.status_code == 206
    assert res.headers["content-range"] == "bytes 1000-1999/10240"
    assert res.content == audio.read_bytes()[1000:2000]
