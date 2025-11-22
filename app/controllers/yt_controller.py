import subprocess
import uuid
import json
import shutil
from pathlib import Path
from datetime import datetime

from ..utils import sanitize_filename, list_audio_files, now_iso, is_youtube_url


def _unique_dest(dest: Path) -> Path:
    """Return a non-colliding path by appending a counter if needed."""
    candidate = dest
    i = 1
    while candidate.exists():
        candidate = dest.with_name(f"{dest.stem}-{i}{dest.suffix}")
        i += 1
    return candidate


def _list_media_files(folder: Path, kinds: str = "audio"):
    """List files produced by yt-dlp in `folder`.

    kinds: 'audio' or 'video' - for audio use AUDIO_EXTS from utils, for video accept common video extensions.
    """
    if not folder.exists():
        return []
    exts = set()
    if kinds == "audio":
        exts = {".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg"}
    else:
        exts = {".webm", ".mp4", ".mkv", ".mov", ".avi"}
    files = []
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(p)
    return files


def _truncate_output(text: str, max_lines: int = 200) -> str:
    if not text:
        return ""
    lines = text.strip().splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[-max_lines:])


def download_audio_sync(url: str, download_dir: str, forced_type: str = None, callback=None, job_id: str = None, logs_dir: str | Path = None):
    """Síncrono: descarga audio con `yt-dlp -x --audio-format mp3` y sigue la convención de `sd_controller`.

    Nota: usa el binario `yt-dlp` — asegúrate que esté en `PATH`.
    """
    # Root of the project (controllers -> app -> project)
    BASE_DIR = Path(__file__).resolve().parents[2]

    # downloads organized by type
    download_path = Path(download_dir) / "audio"
    download_path.mkdir(parents=True, exist_ok=True)

    if not job_id:
        job_id = uuid.uuid4().hex[:8]

    # store logs under logs/yt/<job_id> for YouTube jobs
    if logs_dir:
        logs_base = Path(logs_dir)
    else:
        logs_base = BASE_DIR / "logs" / "yt"

    job_logs_dir = logs_base / job_id
    job_logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = job_logs_dir / f"job-{job_id}.log"
    # tmp separated by type to avoid collisions and keep structure tidy
    tmp_base = BASE_DIR / "tmp" / "yt" / "audio"
    tmp_dir = tmp_base / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    meta_base = BASE_DIR / "meta"
    meta_base.mkdir(parents=True, exist_ok=True)
    meta_path = meta_base / f"meta-{job_id}.json"

    created_at = now_iso()

    if not is_youtube_url(url):
        err = "URL no válida: solo se aceptan enlaces de YouTube"
        meta = {
            "job_id": job_id,
            "url": url,
            "type": forced_type or "audio",
            "source_id": None,
            "artist": None,
            "album": None,
            "created_at": created_at,
            "started_at": None,
            "finished_at": now_iso(),
            "status": "failed",
            "files": [],
            "log_path": str(log_path),
            "error": err,
            "inferred_from_filenames": False,
            "raw_yt_summary": None,
        }
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=2, ensure_ascii=False)
        print(f"JOB {job_id} STATUS failed reason=invalid_url")
        if callback:
            callback(None, None)
        return

    started_at = now_iso()
    try:
        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write(f"[{started_at}] JOB {job_id} START url={url}\n")
            output_template = str(tmp_dir / "%(title)s.%(ext)s")
            process = subprocess.run(
                [
                    "yt-dlp",
                    "-x",
                    "--audio-format",
                    "mp3",
                    "--audio-quality",
                    "0",
                    "-o",
                    output_template,
                    url,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            raw_output = process.stdout or ""
            logf.write(raw_output)

        finished_at = now_iso()
        status = "success" if process.returncode == 0 else "failed"

        media_files = _list_media_files(tmp_dir, kinds="audio")
        moved_files = []

        for p in media_files:
            safe_name = sanitize_filename(p.name)
            dest = download_path / safe_name
            dest = _unique_dest(dest)
            shutil.move(str(p), str(dest))
            moved_files.append({
                "name": dest.name,
                "path": str(dest),
                "size_bytes": dest.stat().st_size,
            })

        # If yt-dlp returned success but no files were produced, mark as failed and extract message
        if status == "success" and len(moved_files) == 0:
            status = "failed"
            if raw_output:
                # attempt to find a relevant error line
                lines = [l for l in raw_output.splitlines() if l.strip()]
                extracted = None
                for line in reversed(lines[-200:]):
                    if "Error" in line or "AudioProviderError" in line or "Traceback" in line:
                        extracted = line
                        break
                if not extracted and lines:
                    extracted = lines[-1]
            else:
                extracted = "No files produced by yt-dlp (no output)"

        # Cleanup tmp
        try:
            for sub in tmp_dir.glob("*"):
                if sub.is_dir():
                    shutil.rmtree(sub)
            if tmp_dir.exists():
                tmp_dir.rmdir()
        except Exception:
            pass

        # try to extract summary
        raw_yt_summary = None
        import re

        m = re.search(r"Downloaded\s+\d+\s+files?|Merged|Destination:\s+", raw_output)
        if m:
            raw_yt_summary = m.group(0)

        meta = {
            "job_id": job_id,
            "url": url,
            "type": forced_type or "audio",
            "source_id": None,
            "artist": None,
            "album": None,
            "created_at": created_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "files": moved_files,
            "log_path": str(log_path),
            "error": None if status == "success" else _truncate_output(raw_output, max_lines=200),
            "inferred_from_filenames": False,
            "raw_yt_summary": raw_yt_summary,
        }

        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=2, ensure_ascii=False)

        print(f"JOB {job_id} STATUS {status} FILES {len(moved_files)} PATH {download_path}")

        if callback:
            if status == "success":
                callback([f["name"] for f in moved_files], [f["path"] for f in moved_files])
            else:
                callback(None, None)

    except Exception as e:
        finished_at = now_iso()
        meta = {
            "job_id": job_id,
            "url": url,
            "type": forced_type or "audio",
            "source_id": None,
            "artist": None,
            "album": None,
            "created_at": created_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": "failed",
            "files": [],
            "log_path": str(log_path),
            "error": str(e),
            "inferred_from_filenames": False,
            "raw_yt_summary": None,
        }
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=2, ensure_ascii=False)
        print(f"JOB {job_id} STATUS failed exception={e}")
        if callback:
            callback(None, None)


def download_video_sync(url: str, download_dir: str, forced_type: str = None, callback=None, job_id: str = None, logs_dir: str | Path = None):
    """Síncrono: descarga video con `yt-dlp` y produce `webm` como formato de salida preferente.
    Sigue la convención de `sd_controller` para logs/meta/tmp.
    """
    BASE_DIR = Path(__file__).resolve().parents[2]

    # downloads organized by type
    download_path = Path(download_dir) / "video"
    download_path.mkdir(parents=True, exist_ok=True)

    if not job_id:
        job_id = uuid.uuid4().hex[:8]

    # store logs under logs/yt/<job_id> for YouTube jobs
    if logs_dir:
        logs_base = Path(logs_dir)
    else:
        logs_base = BASE_DIR / "logs" / "yt"

    job_logs_dir = logs_base / job_id
    job_logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = job_logs_dir / f"job-{job_id}.log"
    # tmp separated by type
    tmp_base = BASE_DIR / "tmp" / "yt" / "video"
    tmp_dir = tmp_base / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    meta_base = BASE_DIR / "meta"
    meta_base.mkdir(parents=True, exist_ok=True)
    meta_path = meta_base / f"meta-{job_id}.json"

    created_at = now_iso()

    if not is_youtube_url(url):
        err = "URL no válida: solo se aceptan enlaces de YouTube"
        meta = {
            "job_id": job_id,
            "url": url,
            "type": forced_type or "video",
            "source_id": None,
            "artist": None,
            "album": None,
            "created_at": created_at,
            "started_at": None,
            "finished_at": now_iso(),
            "status": "failed",
            "files": [],
            "log_path": str(log_path),
            "error": err,
            "inferred_from_filenames": False,
            "raw_yt_summary": None,
        }
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=2, ensure_ascii=False)
        print(f"JOB {job_id} STATUS failed reason=invalid_url")
        if callback:
            callback(None, None)
        return

    started_at = now_iso()
    try:
        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write(f"[{started_at}] JOB {job_id} START url={url}\n")
            output_template = str(tmp_dir / "%(title)s.%(ext)s")
            process = subprocess.run(
                [
                    "yt-dlp",
                    "-f",
                    "bestvideo+bestaudio/best",
                    "--merge-output-format",
                    "webm",
                    "-o",
                    output_template,
                    url,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            raw_output = process.stdout or ""
            logf.write(raw_output)

        finished_at = now_iso()
        status = "success" if process.returncode == 0 else "failed"

        media_files = _list_media_files(tmp_dir, kinds="video")
        moved_files = []

        for p in media_files:
            safe_name = sanitize_filename(p.name)
            dest = download_path / safe_name
            dest = _unique_dest(dest)
            shutil.move(str(p), str(dest))
            moved_files.append({
                "name": dest.name,
                "path": str(dest),
                "size_bytes": dest.stat().st_size,
            })

        # Cleanup tmp
        try:
            for sub in tmp_dir.glob("*"):
                if sub.is_dir():
                    shutil.rmtree(sub)
            if tmp_dir.exists():
                tmp_dir.rmdir()
        except Exception:
            pass

        # try to extract summary
        raw_yt_summary = None
        import re

        m = re.search(r"Downloaded\s+\d+\s+files?|Merged|Destination:\s+", raw_output)
        if m:
            raw_yt_summary = m.group(0)

        meta = {
            "job_id": job_id,
            "url": url,
            "type": forced_type or "video",
            "source_id": None,
            "artist": None,
            "album": None,
            "created_at": created_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "files": moved_files,
            "log_path": str(log_path),
            "error": None if status == "success" else _truncate_output(raw_output, max_lines=200),
            "inferred_from_filenames": False,
            "raw_yt_summary": raw_yt_summary,
        }

        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=2, ensure_ascii=False)

        print(f"JOB {job_id} STATUS {status} FILES {len(moved_files)} PATH {download_path}")

        if callback:
            if status == "success":
                callback([f["name"] for f in moved_files], [f["path"] for f in moved_files])
            else:
                callback(None, None)

    except Exception as e:
        finished_at = now_iso()
        meta = {
            "job_id": job_id,
            "url": url,
            "type": forced_type or "video",
            "source_id": None,
            "artist": None,
            "album": None,
            "created_at": created_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": "failed",
            "files": [],
            "log_path": str(log_path),
            "error": str(e),
            "inferred_from_filenames": False,
            "raw_yt_summary": None,
        }
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=2, ensure_ascii=False)
        print(f"JOB {job_id} STATUS failed exception={e}")
        if callback:
            callback(None, None)
