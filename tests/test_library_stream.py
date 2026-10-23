"""GET /library/tracks/{id}/stream: inline audio with HTTP Range (spec library/track-streaming)."""
import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient

from app.api import app
from app.core.http_range import parse_range
from app.repositories import track_repo

DATA = bytes(range(256)) * 40  # 10240 bytes


@pytest.fixture
def client(sandbox):
    return TestClient(app)


@pytest.fixture
def track(sandbox):
    audio = sandbox / "download" / "audio" / "song.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(DATA)
    return track_repo.upsert(path=audio, job_id="job1", fmt="mp3", size_bytes=len(DATA))


def test_installed_fileresponse_ignores_range(tmp_path):
    """Characterization (design decision 7): starlette 0.27 FileResponse has no Range support.

    If this starts failing after an upgrade, the custom streamer can shrink to headers + MIME.
    """
    audio = tmp_path / "a.mp3"
    audio.write_bytes(DATA)
    plain = FastAPI()
    plain.get("/f")(lambda: FileResponse(audio, media_type="audio/mpeg"))

    res = TestClient(plain).get("/f", headers={"Range": "bytes=1000-1999"})

    assert res.status_code == 200
    assert len(res.content) == len(DATA)
    assert "content-range" not in res.headers and "accept-ranges" not in res.headers


def test_full_response_headers(client, track):
    res = client.get(f"/library/tracks/{track}/stream")

    assert res.status_code == 200
    assert res.content == DATA
    assert res.headers["content-type"] == "audio/mpeg"
    assert res.headers["accept-ranges"] == "bytes"
    assert res.headers["content-length"] == str(len(DATA))
    assert res.headers["content-disposition"].startswith("inline")


@pytest.mark.parametrize("ext,mime", [
    ("m4a", "audio/mp4"), ("ogg", "audio/ogg"), ("opus", "audio/ogg; codecs=opus"),
    ("flac", "audio/flac"), ("wav", "audio/wav"),
])
def test_mime_type_follows_the_extension(client, sandbox, ext, mime):
    audio = sandbox / "download" / "audio" / f"song.{ext}"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(DATA)
    track_id = track_repo.upsert(path=audio, fmt=ext, size_bytes=len(DATA))

    assert client.get(f"/library/tracks/{track_id}/stream").headers["content-type"] == mime


def test_unknown_or_missing_file_404(client, sandbox, track):
    assert client.get(f"/library/tracks/{'0' * 16}/stream").status_code == 404

    (sandbox / "download" / "audio" / "song.mp3").unlink()
    assert client.get(f"/library/tracks/{track}/stream").status_code == 404


def test_range_middle_206(client, track):
    res = client.get(f"/library/tracks/{track}/stream", headers={"Range": "bytes=1000-1999"})

    assert res.status_code == 206
    assert res.headers["content-range"] == "bytes 1000-1999/10240"
    assert res.headers["content-length"] == "1000"
    assert res.content == DATA[1000:2000]


def test_range_open_ended_and_suffix(client, track):
    url = f"/library/tracks/{track}/stream"

    open_ended = client.get(url, headers={"Range": "bytes=9240-"})
    suffix = client.get(url, headers={"Range": "bytes=-500"})

    assert (open_ended.status_code, open_ended.content) == (206, DATA[9240:])
    assert open_ended.headers["content-range"] == "bytes 9240-10239/10240"
    assert (suffix.status_code, suffix.content) == (206, DATA[-500:])
    assert suffix.headers["content-range"] == "bytes 9740-10239/10240"


def test_range_end_beyond_size_is_clamped(client, track):
    res = client.get(f"/library/tracks/{track}/stream", headers={"Range": "bytes=10000-99999"})

    assert res.status_code == 206
    assert res.headers["content-range"] == "bytes 10000-10239/10240"


def test_range_unsatisfiable_416(client, track):
    res = client.get(f"/library/tracks/{track}/stream", headers={"Range": "bytes=10240-"})

    assert res.status_code == 416
    assert res.headers["content-range"] == "bytes */10240"


@pytest.mark.parametrize("header", ["bytes=0-1,5-9", "items=0-5", "bytes=abc", "bytes=5-2"])
def test_unsupported_or_malformed_range_serves_the_whole_file(client, track, header):
    res = client.get(f"/library/tracks/{track}/stream", headers={"Range": header})

    assert res.status_code == 200 and res.content == DATA


def test_record_outside_downloads_403(client, sandbox):
    outside = sandbox / "outside" / "secret.mp3"
    outside.parent.mkdir()
    outside.write_bytes(b"secret")
    track_id = track_repo.upsert(path=outside, fmt="mp3", size_bytes=6)

    res = client.get(f"/library/tracks/{track_id}/stream")

    assert res.status_code == 403
    assert b"secret" not in res.content


@pytest.mark.parametrize("bad_id", ["..%2F..%2Fetc%2Fpasswd", "..", "A" * 16, "abc"])
def test_id_with_separators_404(client, bad_id):
    assert client.get(f"/library/tracks/{bad_id}/stream").status_code == 404


@pytest.mark.parametrize("header,size,expected", [
    (None, 100, None),
    ("bytes=0-0", 100, (0, 0)),
    ("bytes=10-", 100, (10, 99)),
    ("bytes=-10", 100, (90, 99)),
    ("bytes=-500", 100, (0, 99)),
    ("bytes=90-500", 100, (90, 99)),
    ("bytes=100-", 100, "unsatisfiable"),
    ("bytes=-0", 100, "unsatisfiable"),
    ("bytes=0-", 0, "unsatisfiable"),
    ("BYTES=1-2", 100, (1, 2)),
])
def test_parse_range(header, size, expected):
    assert parse_range(header, size) == expected
