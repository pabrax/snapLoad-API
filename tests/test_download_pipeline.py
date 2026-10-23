"""End-to-end of BaseDownloadService.download_sync with a fake command (no network)."""
import sys
from pathlib import Path

from app.core.enums import MediaType
from app.managers import metadata_manager
from app.services.base_download_service import BaseDownloadService


class FakeService(BaseDownloadService):
    def get_source_name(self):
        return "yt"

    def get_media_type(self):
        return MediaType.AUDIO

    def get_file_extensions(self):
        return {".mp3"}

    def validate_url(self, url):
        pass

    def build_command(self, url, output_path: Path, **kwargs):
        code = f"from pathlib import Path; Path(r'{output_path}', 'song.mp3').write_bytes(b'x' * 10)"
        return [sys.executable, "-c", code]


def test_download_sync_produces_file_on_this_platform(sandbox):
    FakeService().download_sync("https://youtu.be/abc", job_id="job1", quality="192K")

    meta = metadata_manager.read_metadata("job1")
    assert meta.status == "success", meta.error
    assert [f.name for f in meta.files] == ["song.mp3"]
    assert Path(meta.files[0].path).read_bytes() == b"x" * 10


class FailingService(FakeService):
    def build_command(self, url, output_path: Path, **kwargs):
        code = "import sys; print('[download] 8.0% of 1MiB'); print('ERROR: unable to download: HTTP Error 403'); sys.exit(1)"
        return [sys.executable, "-c", code]


def test_failed_job_stores_a_one_line_error_and_keeps_the_full_log(sandbox):
    FailingService().download_sync("https://youtu.be/abc", job_id="job2")

    meta = metadata_manager.read_metadata("job2")
    assert meta.status == "failed"
    assert meta.error == "unable to download: HTTP Error 403"
    assert "[download] 8.0%" in Path(meta.log_path).read_text(encoding="utf-8")


# --- audio metadata (spec downloads/audio-metadata) ---

import json

from app.repositories import download_index_repo
from app.services.youtube_service import YouTubeAudioService

INFO = {"title": "Song", "uploader": "Band", "duration": 19, "thumbnail": "https://i.example/t.jpg",
        "webpage_url": "https://youtu.be/abc", "id": "abc", "description": "x" * 5000, "formats": [{"a": 1}]}


class FakeYtAudio(YouTubeAudioService):
    """Real YouTubeAudioService post-processing with a scripted command instead of yt-dlp."""

    def __init__(self, ext="wav", stderr="", code=0, write_audio=True):
        super().__init__()
        self._script = (ext, stderr, code, write_audio)

    def validate_url(self, url):
        pass

    def build_command(self, url, output_path: Path, **kwargs):
        ext, stderr, code, write_audio = self._script
        audio = f"Path(r'{output_path}', 'Song.{ext}').write_bytes(b'x' * 10);" if write_audio else ""
        info = f"Path(r'{output_path}', 'Song.info.json').write_text({json.dumps(INFO)!r}, encoding='utf-8');"
        script = (
            "import sys; from pathlib import Path; " + audio + info
            + (f"print({stderr!r});" if stderr else "") + f"sys.exit({code})"
        )
        return [sys.executable, "-c", script]


def test_sidecar_written_for_wav(sandbox):
    FakeYtAudio("wav").download_sync("https://youtu.be/abc", job_id="job3", quality="lossless", format="wav")

    meta = metadata_manager.read_metadata("job3")
    assert meta.status == "success", meta.error
    sidecar = Path(meta.files[0].path + ".meta.json")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data == {
        "title": "Song", "artist": "Band", "album": None, "duration_s": 19,
        "thumbnail_url": "https://i.example/t.jpg", "source_url": "https://youtu.be/abc", "source_id": "abc",
    }


def test_sidecar_not_in_job_files_nor_cache_key(sandbox):
    download_index_repo.register_pending("https://youtu.be/abc", "audio", "best", "mp3", "job4", "2026-01-01T00:00:00Z")
    FakeYtAudio("mp3").download_sync("https://youtu.be/abc", job_id="job4", quality="best", format="mp3")

    meta = metadata_manager.read_metadata("job4")
    assert [f.name for f in meta.files] == ["Song.mp3"]
    entry = download_index_repo.lookup("https://youtu.be/abc", "audio", "best", "mp3")
    assert entry.status == "ready" and all(not p.endswith(".json") for p in entry.files)
    assert (entry.quality, entry.format) == ("best", "mp3")


def test_embed_failure_warning_keeps_job_ready(sandbox):
    err = "ERROR: Postprocessing: Supported filetypes for thumbnail embedding are: mp3, mkv/mka"
    FakeYtAudio("wav", stderr=err, code=1).download_sync("https://youtu.be/abc", job_id="job5", format="wav")

    meta = metadata_manager.read_metadata("job5")
    assert meta.status == "success", meta.error
    assert [f.name for f in meta.files] == ["Song.wav"]


def test_other_nonzero_exit_still_fails_even_if_a_file_exists(sandbox):
    FakeYtAudio("mp3", stderr="ERROR: unable to download: HTTP Error 403", code=1).download_sync(
        "https://youtu.be/abc", job_id="job6", format="mp3"
    )

    assert metadata_manager.read_metadata("job6").status == "failed"


def test_missing_info_json_does_not_break_the_job(sandbox):
    class NoInfo(FakeYtAudio):
        def build_command(self, url, output_path, **kwargs):
            return [sys.executable, "-c", f"from pathlib import Path; Path(r'{output_path}', 'Song.mp3').write_bytes(b'x')"]

    NoInfo().download_sync("https://youtu.be/abc", job_id="job7", format="mp3")

    meta = metadata_manager.read_metadata("job7")
    assert meta.status == "success" and not Path(meta.files[0].path + ".meta.json").exists()
