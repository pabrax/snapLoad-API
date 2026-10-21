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
