"""MusicBrainz client, enrichment pipeline and artist/album layout (feature library-quality-dedup-tags, S2)."""
import functools
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import pytest

from app.core.config import settings
from app.core.process import find_binary, resolve_binary
from app.repositories import download_index_repo, track_repo
from app.services import enrichment, track_metadata
from app.services.musicbrainz import MBMatch, MusicBrainzClient
from app.services.youtube_service import YouTubeAudioService

needs_ffmpeg = pytest.mark.skipif(
    not (find_binary("ffmpeg") and find_binary("ffprobe")), reason="ffmpeg/ffprobe not installed"
)

RECORDING = {
    "id": "rec-1", "score": 100, "title": "Karma Police", "length": 264000,
    "artist-credit": [{"name": "Radiohead", "joinphrase": ""}],
    "releases": [
        {"id": "rel-comp", "title": "Greatest Hits", "status": "Official", "date": "2008-01-01",
         "release-group": {"primary-type": "Album", "secondary-types": ["Compilation"]},
         "media": [{"track": [{"number": "3"}]}]},
        {"id": "rel-ok", "title": "OK Computer", "status": "Official", "date": "1997-05-21",
         "release-group": {"primary-type": "Album", "secondary-types": []},
         "media": [{"track": [{"number": "6"}]}]},
    ],
}


def client_with(handler, **kw):
    kw.setdefault("sleep", lambda s: None)
    return MusicBrainzClient(transport=httpx.MockTransport(handler), **kw)


def ok(recordings):
    return lambda request: httpx.Response(200, json={"recordings": recordings})


def test_lookup_picks_the_official_album_release():
    match = client_with(ok([RECORDING])).lookup("Karma Police", "Radiohead", 264.0)
    assert match == MBMatch(title="Karma Police", artist="Radiohead", album="OK Computer", year="1997",
                            track_no=6, recording_id="rec-1", release_id="rel-ok")


def test_lookup_rejects_low_score_and_duration_mismatch():
    low = dict(RECORDING, score=60)
    assert client_with(ok([low])).lookup("Karma Police", "Radiohead", 264.0) is None
    assert client_with(ok([RECORDING])).lookup("Karma Police", "Radiohead", 300.0) is None   # 36 s off
    assert client_with(ok([RECORDING])).lookup("Karma Police", "Radiohead", 266.0) is not None  # within 5 s


def test_lookup_without_known_duration_still_matches_on_score():
    assert client_with(ok([RECORDING])).lookup("Karma Police", "Radiohead", None) is not None


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(503),
    lambda r: httpx.Response(200, text="not json"),
    lambda r: httpx.Response(200, json={"unexpected": 1}),
    lambda r: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
])
def test_lookup_never_raises(handler):
    assert client_with(handler).lookup("Karma Police", "Radiohead", 264.0) is None


def test_lookup_requires_a_title():
    assert client_with(ok([RECORDING])).lookup("", "Radiohead", 264.0) is None
    assert client_with(ok([RECORDING])).lookup(None, None, None) is None


def test_query_escapes_quotes_and_lucene_specials():
    seen = {}

    def handler(request):
        seen["q"] = request.url.params["query"]
        return httpx.Response(200, json={"recordings": []})

    client_with(handler).lookup('He said "hi" \\ AND (x)', 'A"B', None)
    assert '\\"hi\\"' in seen["q"] and 'artist:"A\\"B"' in seen["q"]


def test_user_agent_is_generic_unless_a_contact_is_configured(monkeypatch):
    seen = []
    handler = lambda r: (seen.append(r.headers["user-agent"]), httpx.Response(200, json={"recordings": []}))[1]  # noqa: E731
    monkeypatch.setattr(settings, "MUSICBRAINZ_CONTACT", "")
    client_with(handler).lookup("t", "a", None)
    monkeypatch.setattr(settings, "MUSICBRAINZ_CONTACT", "https://example.org/me")
    client_with(handler).lookup("t", "a", None)
    assert seen[0].startswith("SnapLoad/") and "@" not in seen[0] and "(" not in seen[0]
    assert seen[1].startswith("SnapLoad/") and "https://example.org/me" in seen[1]


def test_requests_are_spaced_at_least_one_second():
    now = [100.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    client = client_with(ok([]), clock=lambda: now[0], sleep=sleep)
    client.lookup("a", "b", None)
    client.lookup("a", "b", None)
    client.lookup("a", "b", None)

    assert len(slept) == 2 and all(abs(s - 1.0) < 1e-6 for s in slept)


def test_fetch_cover():
    jpg = b"\xff\xd8\xff\xe0" + b"x" * 100
    assert client_with(lambda r: httpx.Response(200, content=jpg, headers={"content-type": "image/jpeg"})
                       ).fetch_cover("rel-ok") == jpg
    assert client_with(lambda r: httpx.Response(404)).fetch_cover("rel-ok") is None
    assert client_with(lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
                       ).fetch_cover("rel-ok") is None
    assert client_with(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))).fetch_cover("r") is None
    assert client_with(ok([])).fetch_cover(None) is None


# --- enrichment pipeline ---------------------------------------------------------------------------


def make_mp3(path, title="Karma Police - Radiohead (Official Video)", artist="RadioheadVEVO"):
    subprocess.run(
        [resolve_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=264",
         "-t", "264", "-c:a", "libmp3lame", "-b:a", "32k", "-metadata", f"title={title}",
         "-metadata", f"artist={artist}", str(path)],
        check=True,
    )
    return path


@functools.lru_cache(maxsize=1)
def real_jpeg() -> bytes:
    """A real (decodable) JPEG, so ffprobe recognises it as an attached picture."""
    out = Path(tempfile.mkdtemp()) / "c.jpg"
    subprocess.run(
        [resolve_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=green:s=64x64:d=1",
         "-frames:v", "1", str(out)],
        check=True,
    )
    return out.read_bytes()


class FakeClient:
    def __init__(self, match=None):
        self.match, self.queries = match, []

    def lookup(self, title, artist, duration_s):
        self.queries.append((title, artist, duration_s))
        return self.match

    def fetch_cover(self, release_id):
        return real_jpeg()


MATCH = MBMatch(title="Karma Police", artist="Radiohead", album="OK Computer", year="1997", track_no=6,
                recording_id="rec-1", release_id="rel-ok")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@needs_ffmpeg
def test_disabled_pipeline_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", False)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "flat")
    audio = make_mp3(tmp_path / "a.mp3")
    before = sha(audio)
    fake = FakeClient(MATCH)
    monkeypatch.setattr(enrichment, "get_client", lambda: fake)

    assert enrichment.prepare_audio(audio) is None
    assert sha(audio) == before and fake.queries == []


@needs_ffmpeg
def test_enabled_pipeline_writes_musicbrainz_tags_and_cover(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", True)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "flat")
    audio = make_mp3(tmp_path / "a.mp3")
    fake = FakeClient(MATCH)
    monkeypatch.setattr(enrichment, "get_client", lambda: fake)

    assert enrichment.prepare_audio(audio) is None   # flat layout: no placement change

    # the query used the cleaned title/artist, not the raw YouTube strings
    assert fake.queries[0][:2] == ("Karma Police", "Radiohead")
    tags = track_metadata.read_tags(audio)
    assert (tags.title, tags.artist, tags.album, tags.has_cover) == ("Karma Police", "Radiohead", "OK Computer", True)


@needs_ffmpeg
def test_musicbrainz_miss_leaves_the_file_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", True)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "flat")
    audio = make_mp3(tmp_path / "a.mp3")
    before = sha(audio)
    monkeypatch.setattr(enrichment, "get_client", lambda: FakeClient(None))

    assert enrichment.prepare_audio(audio) is None
    assert sha(audio) == before


@needs_ffmpeg
def test_client_failure_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", True)
    audio = make_mp3(tmp_path / "a.mp3")

    class Boom:
        def lookup(self, *a):
            raise RuntimeError("boom")

    monkeypatch.setattr(enrichment, "get_client", lambda: Boom())
    assert enrichment.prepare_audio(audio) is None


@needs_ffmpeg
def test_layout_uses_musicbrainz_values(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", True)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "artist-album")
    audio = make_mp3(tmp_path / "a.mp3")
    monkeypatch.setattr(enrichment, "get_client", lambda: FakeClient(MATCH))

    placement = enrichment.prepare_audio(audio)

    assert placement.subdir == Path("Radiohead") / "OK Computer"
    assert placement.name == "06 - Karma Police.mp3"


@needs_ffmpeg
def test_layout_without_musicbrainz_uses_cleaned_tags(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", False)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "artist-album")
    audio = make_mp3(tmp_path / "a.mp3", title="Karma Police (Official Video)", artist="Radiohead - Topic")

    placement = enrichment.prepare_audio(audio)

    assert placement.subdir == Path("Radiohead") / "Singles"
    assert placement.name == "Karma Police.mp3"


@needs_ffmpeg
def test_layout_without_artist_stays_flat(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", False)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "artist-album")
    audio = make_mp3(tmp_path / "a.mp3", title="Something", artist="")
    assert enrichment.prepare_audio(audio) is None


@pytest.mark.parametrize("raw,expected", [
    ("AC/DC", "AC-DC"),
    ('What?: "Now" <1>', "What_ _Now_ _1_"),
    ("..", "_"),
    ("name. ", "name"),
    ("", "_"),
    ("CON", "CON_"),
])
def test_folder_component_is_safe_on_windows_and_posix(raw, expected):
    assert enrichment.safe_component(raw) == expected


def test_layout_can_never_escape_the_destination(tmp_path):
    placement = enrichment.build_placement("../../etc", "../passwd", "x/../y", 1, ".mp3")
    assert ".." not in placement.subdir.parts and ".." not in Path(placement.name).parts
    resolved = (tmp_path / placement.subdir / placement.name).resolve()
    resolved.relative_to(tmp_path.resolve())


# --- end to end through the real download flow -------------------------------------------------------


class FfmpegAudio(YouTubeAudioService):
    """Real post-download flow with a scripted command that writes a real mp3 in the temp dir."""

    def validate_url(self, url):
        pass

    def build_command(self, url, output_path: Path, **kwargs):
        code = (
            "import subprocess,sys;"
            f"subprocess.run([r'{resolve_binary('ffmpeg')}','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=5',"
            "'-c:a','libmp3lame','-b:a','64k','-metadata','title=Karma Police (Official Video)',"
            f"'-metadata','artist=RadioheadVEVO',r'{output_path / 'Karma Police.mp3'}'],check=True);"
            # yt-dlp also leaves an info.json next to the audio; the library sidecar is built from it
            "import json,pathlib;"
            f"pathlib.Path(r'{output_path / 'Karma Police.info.json'}').write_text(json.dumps("
            "{'title':'Karma Police (Official Video)','uploader':'RadioheadVEVO','duration':5,"
            "'webpage_url':'https://www.youtube.com/watch?v=dQw4w9WgXcQ','id':'dQw4w9WgXcQ'}))"
        )
        return [sys.executable, "-c", code]


URL = "https://youtu.be/dQw4w9WgXcQ"


def run_job(job="jobE2E"):
    download_index_repo.register_pending(URL, "audio", "best", "mp3", job, "2026-01-01T00:00:00Z")
    FfmpegAudio().download_sync(URL, job_id=job, quality="best", format="mp3")
    return download_index_repo.find_by_job_id(job)


@needs_ffmpeg
def test_job_with_musicbrainz_and_layout_lands_in_artist_album_folder(sandbox, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", True)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "artist-album")
    monkeypatch.setattr(enrichment, "get_client", lambda: FakeClient(MATCH))

    entry = run_job()

    assert entry.status == "ready" and len(entry.files) == 1
    final = Path(entry.files[0])
    assert final.parents[2] == settings.DOWNLOAD_DIR / "audio" / "mp3" / "best"
    assert final.name == "06 - Karma Police.mp3" and final.parent.name == "OK Computer"
    assert final.parent.parent.name == "Radiohead" and final.is_file()
    # library knows the corrected tags and the sidecar sits next to the moved file
    track = track_repo.list()[0][0]
    assert (track.title, track.artist, track.album) == ("Karma Police", "Radiohead", "OK Computer")
    assert track.source_id == "youtube:dQw4w9WgXcQ"
    assert track_metadata.sidecar_path(final).exists()


@needs_ffmpeg
def test_job_succeeds_flat_when_musicbrainz_is_down(sandbox, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", True)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "flat")

    class Down:
        def lookup(self, *a):
            raise httpx.ConnectError("offline")

        def fetch_cover(self, *a):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(enrichment, "get_client", lambda: Down())

    entry = run_job("jobDown")

    assert entry.status == "ready" and Path(entry.files[0]).name == "Karma Police.mp3"


@needs_ffmpeg
def test_job_with_features_off_behaves_as_before(sandbox, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", False)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "flat")
    monkeypatch.setattr(enrichment, "get_client", lambda: (_ for _ in ()).throw(AssertionError("must not be used")))

    entry = run_job("jobOff")

    assert entry.status == "ready" and Path(entry.files[0]).name == "Karma Police.mp3"
    assert track_repo.list()[0][0].artist == "RadioheadVEVO"
