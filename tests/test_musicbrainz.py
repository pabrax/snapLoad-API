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


def rel(rid, title, status="Official", primary="Album", secondary=None, date="1997-05-21", number="6"):
    return {"id": rid, "title": title, "status": status, "date": date,
            "release-group": {"primary-type": primary, "secondary-types": secondary or []},
            "media": [{"track": [{"number": number}]}]}


def rec(rid, releases, length=264000, score=100, title="Karma Police"):
    return {"id": rid, "score": score, "title": title, "length": length,
            "artist-credit": [{"name": "Radiohead", "joinphrase": ""}], "releases": releases}


LIVE = rel("rel-live", "2012-03-13: 1st Bank Center", status="Bootleg", secondary=["Live"], date="2012")
OFFICIAL_LIVE = rel("rel-ol", "Live at Roundhouse", secondary=["Live"], date="2016")
COMP = rel("rel-comp", "The Best Of", secondary=["Compilation"], date="2008")
STUDIO = rel("rel-ok", "OK Computer")


def test_never_tags_with_live_bootleg_or_compilation_releases():
    """Real MusicBrainz returns many score-100 live bootlegs; tagging with their album would be wrong."""
    recordings = [rec("r1", [LIVE]), rec("r2", [OFFICIAL_LIVE]), rec("r3", [COMP])]
    assert client_with(ok(recordings)).lookup("Karma Police", "Radiohead", 264.0) is None


def test_studio_album_wins_among_many_candidates():
    recordings = [rec("r1", [LIVE]), rec("r2", [COMP]), rec("r3", [COMP, STUDIO]), rec("r4", [OFFICIAL_LIVE])]
    match = client_with(ok(recordings)).lookup("Karma Police", "Radiohead", 264.0)
    assert (match.recording_id, match.album, match.release_id) == ("r3", "OK Computer", "rel-ok")


def test_oldest_release_wins_then_closest_duration():
    """The original edition beats a reissue even when the reissue is a few ms closer in length."""
    reissue = rec("reissue", [rel("rel-new", "Reissue", date="2009")], length=264000)
    original = rec("original", [rel("rel-old", "Original", date="1997")], length=262500)
    assert client_with(ok([reissue, original])).lookup("Karma Police", "Radiohead", 264.0).album == "Original"
    same_track_far = rec("far", [rel("rel-a", "A", date="1997", number="6")], length=268000)
    same_track_near = rec("near", [rel("rel-b", "B", date="1997", number="6")], length=264200)
    assert client_with(ok([same_track_far, same_track_near])).lookup("Karma Police", "Radiohead", 264.0).recording_id == "near"


def test_track_number_is_the_consensus_of_the_editions_of_the_same_album():
    """One odd edition (bonus tracks, different numbering) must not decide the track number."""
    odd = rec("odd", [rel("r1", "OK Computer", date="1997-05-21", number="1")])
    a = rec("a", [rel("r2", "OK Computer", date="1997-06-01", number="6")])
    b = rec("b", [rel("r3", "OK Computer", date="1998-01-01", number="6")])
    match = client_with(ok([odd, a, b])).lookup("Karma Police", "Radiohead", 264.0)
    assert (match.album, match.track_no) == ("OK Computer", 6)
    assert match.release_id == "r1"          # the original (oldest) edition still supplies year and cover


def test_album_is_preferred_over_single_and_single_is_accepted_alone():
    single = rec("s", [rel("rel-s", "Karma Police", primary="Single", date="1997")])
    album = rec("a", [rel("rel-al", "OK Computer", date="1997")])
    assert client_with(ok([single, album])).lookup("Karma Police", "Radiohead", 264.0).album == "OK Computer"
    assert client_with(ok([single])).lookup("Karma Police", "Radiohead", 264.0).album == "Karma Police"


def test_title_must_match_the_requested_one():
    other = rec("x", [STUDIO], title="Karma Police (Live)")
    assert client_with(ok([other])).lookup("Karma Police", "Radiohead", 264.0) is None
    punct = rec("y", [STUDIO], title="Karma  Police!")
    assert client_with(ok([punct])).lookup("karma police", "Radiohead", 264.0) is not None


def test_query_asks_for_official_releases_and_a_wide_page():
    seen = {}

    def handler(request):
        seen["q"], seen["limit"] = request.url.params["query"], request.url.params["limit"]
        return httpx.Response(200, json={"recordings": []})

    client_with(handler).lookup("Karma Police", "Radiohead", None)
    assert "status:official" in seen["q"] and int(seen["limit"]) == 100


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


def test_busy_server_is_retried_and_then_succeeds():
    """MusicBrainz answers 503 "busy" often; one transient error must not lose the match."""
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"recordings": [RECORDING]})

    assert client_with(handler).lookup("Karma Police", "Radiohead", 264.0) is not None
    assert len(calls) == 3


def test_persistent_503_gives_up_after_three_attempts():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    assert client_with(handler).lookup("Karma Police", "Radiohead", 264.0) is None
    assert len(calls) == 3


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400)

    assert client_with(handler).lookup("Karma Police", "Radiohead", 264.0) is None
    assert len(calls) == 1


def test_retries_still_respect_the_one_second_spacing():
    now, gaps = [100.0], []

    def sleep(s):
        gaps.append(s)
        now[0] += s

    statuses = iter([503, 503, 200])
    client = client_with(lambda r: httpx.Response(next(statuses), json={"recordings": []}),
                         clock=lambda: now[0], sleep=sleep)
    client.lookup("a", "b", None)
    assert gaps and all(g >= 1.0 - 1e-6 for g in gaps)


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
                       ).fetch_cover(UUID) == jpg
    assert client_with(lambda r: httpx.Response(404)).fetch_cover(UUID) is None
    assert client_with(lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
                       ).fetch_cover(UUID) is None
    assert client_with(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))).fetch_cover(UUID) is None
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


# --- review fixes: lengths, fallbacks, collisions, artist-less lookups, bounded HTTP ---------------------

from app.helpers import FileNameHelper  # noqa: E402
from app.managers.file_manager import FileManager  # noqa: E402

UUID = "9eff0482-170f-3e93-8c65-73ce18e10ee7"


def test_long_titles_keep_their_extension_and_stay_within_the_limit():
    placement = enrichment.build_placement("A" * 300, "B" * 300, "T" * 400, 7, ".flac")
    assert placement.name.endswith(".flac") and placement.name.startswith("07 - ")
    assert len(placement.name) <= settings.MAX_FILENAME_LENGTH
    assert all(len(part) <= settings.MAX_FILENAME_LENGTH for part in placement.subdir.parts)
    assert FileNameHelper.sanitize_filename(placement.name).endswith(".flac")


def _tmp_audio(folder, name="a.mp3", data=b"x"):
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / name
    f.write_bytes(data)
    return f


def test_failed_layout_folder_falls_back_to_the_flat_destination(tmp_path, monkeypatch):
    src, dest = tmp_path / "tmp", tmp_path / "dest"
    _tmp_audio(src)
    real_mkdir = Path.mkdir

    def picky_mkdir(self, *a, **kw):
        if "Artist" in self.parts:
            raise OSError("path too long")
        return real_mkdir(self, *a, **kw)

    monkeypatch.setattr(Path, "mkdir", picky_mkdir)
    moved = FileManager.move_files_to_destination(
        src, dest, {".mp3"}, prepare=lambda f: enrichment.Placement(Path("Artist") / "Album", "01 - a.mp3"))

    assert len(moved) == 1 and Path(moved[0].path).parent == dest and Path(moved[0].path).exists()


def test_same_placement_twice_never_overwrites(tmp_path):
    dest = tmp_path / "dest"

    def prepare(f):
        return enrichment.Placement(Path("Artist") / "Album", "01 - Song.mp3")

    FileManager.move_files_to_destination(_tmp_audio(tmp_path / "t1", data=b"first").parent, dest, {".mp3"}, prepare=prepare)
    FileManager.move_files_to_destination(_tmp_audio(tmp_path / "t2", data=b"second").parent, dest, {".mp3"}, prepare=prepare)
    contents = sorted(p.read_bytes() for p in (dest / "Artist" / "Album").iterdir())
    assert contents == [b"first", b"second"]


def test_a_lost_race_on_the_chosen_name_does_not_overwrite(tmp_path, monkeypatch):
    """unique_path said 'free' but another job took it meanwhile: the claim must be exclusive."""
    dest = tmp_path / "dest"
    taken = _tmp_audio(dest, "a.mp3", b"other job")
    monkeypatch.setattr(FileNameHelper, "unique_path", staticmethod(lambda p: p))   # stale answer
    FileManager.move_files_to_destination(_tmp_audio(tmp_path / "tmp", data=b"mine").parent, dest, {".mp3"})
    assert taken.read_bytes() == b"other job"
    assert sorted(p.read_bytes() for p in dest.iterdir()) == [b"mine", b"other job"]


@needs_ffmpeg
def test_no_artist_means_no_musicbrainz_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", True)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "flat")
    audio = make_mp3(tmp_path / "Home.mp3", title="Home", artist="")
    fake = FakeClient(MATCH)
    monkeypatch.setattr(enrichment, "get_client", lambda: fake)
    assert enrichment.prepare_audio(audio) is None
    assert fake.queries == [], "a title-only search would tag a stranger's artist, album and cover"


@pytest.mark.parametrize("raw", ["CONIN$", "conout$", "CON .txt", "con.", "NUL .x", "LPT1"])
def test_more_windows_reserved_names_are_neutralised(raw):
    safe = enrichment.safe_component(raw)
    assert safe.endswith("_") or safe.split(".")[0].strip().upper() not in {"CON", "CONIN$", "CONOUT$", "NUL", "LPT1"}
    assert safe != raw


def test_release_id_must_be_a_uuid():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    client = client_with(handler)
    assert client.fetch_cover("../../etc/passwd") is None and client.fetch_cover("x?y=1") is None
    assert calls == []


def test_cover_redirect_to_another_host_is_refused():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.host == "coverartarchive.org":
            return httpx.Response(307, headers={"location": "http://169.254.169.254/latest/meta-data"})
        return httpx.Response(200, content=b"secret", headers={"content-type": "image/jpeg"})

    assert client_with(handler).fetch_cover(UUID) is None
    assert all("169.254" not in u for u in seen)


def test_cover_redirect_to_archive_org_is_followed():
    jpg = b"\xff\xd8\xff" + b"x" * 50

    def handler(request):
        if request.url.host == "coverartarchive.org":
            return httpx.Response(307, headers={"location": "https://archive.org/download/x/y.jpg"})
        if request.url.host == "archive.org":
            return httpx.Response(302, headers={"location": "https://dn1.ca.archive.org/0/items/x/y.jpg"})
        return httpx.Response(200, content=jpg, headers={"content-type": "image/jpeg"})

    assert client_with(handler).fetch_cover(UUID) == jpg


def test_oversized_bodies_are_rejected():
    big = b"\xff\xd8\xff" + b"x" * 6_000_000
    assert client_with(lambda r: httpx.Response(200, content=big, headers={"content-type": "image/jpeg"})
                       ).fetch_cover(UUID) is None
    huge_json = b'{"recordings": [' + b'{"id": "x"},' * 600_000 + b'{}]}'
    assert client_with(lambda r: httpx.Response(200, content=huge_json, headers={"content-type": "application/json"})
                       ).lookup("Karma Police", "Radiohead", None) is None


def test_contact_cannot_inject_headers(monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_CONTACT", "me@example.org\r\nX-Evil: 1")
    ua = MusicBrainzClient._user_agent()
    assert "\r" not in ua and "\n" not in ua and ua.startswith("SnapLoad/")


@needs_ffmpeg
def test_job_tags_replaygain_before_publishing(sandbox, monkeypatch):
    monkeypatch.setattr(settings, "MUSICBRAINZ_ENABLED", False)
    monkeypatch.setattr(settings, "LIBRARY_LAYOUT", "flat")
    entry = run_job("jobRG")
    tags = track_metadata._embedded(track_metadata.probe(Path(entry.files[0])))
    assert "replaygain_track_gain" in tags
    assert track_repo.list()[0][0].replaygain_db is not None


# --- re-review fixes: no copy on same-volume moves, reserved names with dots, no empty leftovers -------


def test_same_volume_move_is_a_rename_not_a_copy(tmp_path):
    """On Windows shutil.move onto the reserved placeholder falls back to copy+delete: huge files would be copied.
    A rename keeps the file identity; a copy creates a new file."""
    import os
    src = _tmp_audio(tmp_path / "tmp", data=b"big")
    identity = os.stat(src).st_ino

    moved = FileManager.move_files_to_destination(src.parent, tmp_path / "dest", {".mp3"})

    assert len(moved) == 1 and Path(moved[0].path).read_bytes() == b"big"
    assert os.stat(moved[0].path).st_ino == identity, "the file was copied instead of renamed"
    assert not src.exists()


def test_failed_move_leaves_no_placeholder_or_empty_folders(tmp_path, monkeypatch):
    import importlib
    fm = importlib.import_module("app.managers.file_manager")   # the package re-exports an instance under the same name
    dest = tmp_path / "dest"
    real_claim = fm._claim_path

    def claim(path):
        if "Artist" in path.parts:
            raise OSError("disk says no")
        return real_claim(path)

    monkeypatch.setattr(fm, "_claim_path", claim)
    moved = FileManager.move_files_to_destination(
        _tmp_audio(tmp_path / "tmp").parent, dest, {".mp3"},
        prepare=lambda f: enrichment.Placement(Path("Artist") / "Album", "01 - a.mp3"))

    assert Path(moved[0].path).parent == dest
    assert not (dest / "Artist").exists(), "empty Artist/Album folders must not be left behind"
    assert [p.name for p in dest.iterdir()] == ["a.mp3"]


@pytest.mark.parametrize("raw", ["CON .txt", "CON.x", "con.", "NUL .x", "CONIN$", "aux.tar.gz", "COM1.txt"])
def test_reserved_device_names_are_not_reserved_after_sanitizing(raw):
    """Windows treats CON.x and 'CON .txt' as the CON device: the guard must sit before the first dot."""
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    safe = enrichment.safe_component(raw)
    assert safe.split(".")[0].strip().upper() not in reserved, safe


@pytest.mark.parametrize("raw", ["COM0", "LPT0", "COM¹", "LPT².txt", "COM³"])
def test_remaining_documented_device_names_are_neutralised(raw):
    safe = enrichment.safe_component(raw)
    assert safe.split(".")[0].strip() != raw.split(".")[0].strip() and "_" in safe


def test_prune_never_climbs_out_of_or_removes_the_destination(tmp_path):
    import importlib
    fm = importlib.import_module("app.managers.file_manager")
    dest = tmp_path / "dest"
    (dest / "a").mkdir(parents=True)
    fm._prune_empty(dest / "a" / ".." / "b", dest)           # textual path that resolves to dest/b
    fm._prune_empty(dest / "a" / "..", dest)                 # resolves to dest itself
    assert dest.exists() and (dest / "a").exists()
