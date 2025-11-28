import subprocess
import os
import threading
import uuid
import json
import shutil
from pathlib import Path

from ..utils import sanitize_filename, list_audio_files, now_iso, is_spotify_url
from ..job_registry import register_job, unregister_job

def _unique_dest(dest: Path) -> Path:
    """Return a non-colliding path by appending a counter if needed."""
    candidate = dest
    i = 1
    while candidate.exists():
        candidate = dest.with_name(f"{dest.stem}-{i}{dest.suffix}")
        i += 1
    return candidate

def download(url: str, download_dir: str, callback=None, job_id: str = None, logs_dir: str | Path = None, quality: str | None = None):
    """Wrapper que lanza la descarga en un thread.

    Ahora acepta `quality` (bitrate) para que el endpoint `/download` pueda pasarla.
    Mantiene compatibilidad si se omite.
    """

    thread = threading.Thread(target=download_sync, args=(url, download_dir, callback, job_id, logs_dir, quality))
    thread.daemon = True
    thread.start()

def download_sync(url: str, download_dir: str, callback=None, job_id: str = None, logs_dir: str | Path = None, quality: str = None):
    """Ejecución síncrona de la descarga (no lanza threads).

    Esta función realiza todo el flujo: validación, ejecución de `spotdl`, registro en `job.log`,
    movimiento de archivos y escritura de `meta-<job_id>.json`.
    """
    # Root of the project (two levels up from controllers -> app -> project)
    BASE_DIR = Path(__file__).resolve().parents[2]

    download_path = Path(download_dir)
    download_path.mkdir(parents=True, exist_ok=True)

    # store spotify downloads under downloads/audio for consistency with YouTube
    download_path = Path(download_dir) / "audio"
    download_path.mkdir(parents=True, exist_ok=True)

    # Prepare job id and logs directory
    if not job_id:
        job_id = uuid.uuid4().hex[:8]

    if logs_dir:
        logs_base = Path(logs_dir)
    else:
        # default logs directory at repo/logs/spotify
        logs_base = BASE_DIR / "logs" / "spotify"

    job_logs_dir = logs_base / job_id
    job_logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = job_logs_dir / f"job-{job_id}.log"

    # Use a tmp directory separated from downloads and logs: <repo>/tmp/<job_id>/
    # tmp separated by origin/type: tmp/spotify/audio/<job_id>
    tmp_base = BASE_DIR / "tmp" / "spotify" / "audio"
    tmp_dir = tmp_base / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Store meta centrally under <repo>/meta/meta-<job_id>.json
    meta_base = BASE_DIR / "meta"
    meta_base.mkdir(parents=True, exist_ok=True)
    meta_path = meta_base / f"meta-{job_id}.json"


    created_at = now_iso()

    # Basic validation: ensure it's a Spotify URL/URI
    if not is_spotify_url(url):
        err = "URL no válida: solo se aceptan enlaces/URIs de Spotify"
        # write meta with failure
        meta = {
            "job_id": job_id,
            "url": url,
            "type": "audio",
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
            "raw_spotdl_summary": None,
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
            # Run spotdl writing stdout+stderr to capture everything
            cmd = ["spotdl", url, "--output", str(tmp_dir)]
            # If a bitrate/quality is provided, pass it to spotdl
            if quality:
                cmd.extend(["--bitrate", str(quality)])

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                preexec_fn=os.setsid,
            )
            register_job(job_id, process)

            raw_lines = []
            try:
                if process.stdout:
                    for line in process.stdout:
                        raw_lines.append(line)
                        logf.write(line)
            except Exception:
                pass
            try:
                process.wait()
            finally:
                unregister_job(job_id)

            # dump output to log (full output kept in the job log)
            raw_output = "".join(raw_lines)

        finished_at = now_iso()
        status = "success" if process.returncode == 0 else "failed"

        # Find audio files in tmp_dir
        audio_files = list_audio_files(tmp_dir)
        moved_files = []

        for p in audio_files:
            safe_name = sanitize_filename(p.name)
            dest = download_path / safe_name
            dest = _unique_dest(dest)
            shutil.move(str(p), str(dest))
            moved_files.append({
                "name": dest.name,
                "path": str(dest),
                "size_bytes": dest.stat().st_size,
            })

        # If spotdl returned success but no files were produced, mark as failed
        # and try to extract a relevant error line from the output.
        if status == "success" and len(moved_files) == 0:
            status = "failed"
            if raw_output:
                lines = [l for l in raw_output.splitlines() if l.strip()]
                extracted = None
                for line in reversed(lines[-200:]):
                    if "Error" in line or "AudioProviderError" in line or "Traceback" in line:
                        extracted = line
                        break
                if not extracted and lines:
                    extracted = lines[-1]
            else:
                extracted = "No files produced by spotdl (no output)"


        # Cleanup tmp directory (remove empty dirs)
        try:
            for sub in tmp_dir.glob("*"):
                if sub.is_dir():
                    shutil.rmtree(sub)
            if tmp_dir.exists():
                tmp_dir.rmdir()
        except Exception:
            pass

        # Build meta (truncate error to last N lines to avoid huge JSON payloads)
        raw_spotdl_summary = None
        if raw_output:
            # try to extract a short summary like 'Downloaded X tracks'
            import re

            m = re.search(r"Downloaded\s+\d+\s+tracks", raw_output)
            if m:
                raw_spotdl_summary = m.group(0)

        def _truncate_output(text: str, max_lines: int = 200) -> str:
            if not text:
                return ""
            lines = text.strip().splitlines()
            if len(lines) <= max_lines:
                return "\n".join(lines)
            return "\n".join(lines[-max_lines:])

        meta = {
            "job_id": job_id,
            "url": url,
            "type": "audio",
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
            "raw_spotdl_summary": raw_spotdl_summary,
        }

        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=2, ensure_ascii=False)

        # Console notification simulating webhook
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
            "type": "audio",
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
            "raw_spotdl_summary": None,
        }
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(meta, mf, indent=2, ensure_ascii=False)
        print(f"JOB {job_id} STATUS failed exception={e}")
        if callback:
            callback(None, None)