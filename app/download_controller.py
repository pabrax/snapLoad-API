import subprocess
import threading
import uuid
import json
import shutil
from pathlib import Path

from .utils import sanitize_filename, list_audio_files, now_iso, is_spotify_url


def _unique_dest(dest: Path) -> Path:
    """Return a non-colliding path by appending a counter if needed."""
    candidate = dest
    i = 1
    while candidate.exists():
        candidate = dest.with_name(f"{dest.stem}-{i}{dest.suffix}")
        i += 1
    return candidate


def download(url: str, download_dir: str, callback=None, forced_type: str = None, job_id: str = None, logs_dir: str | Path = None):
    """
    Wrapper que lanza la descarga en un thread.
    Para uso con la API (BackgroundTasks) se recomienda llamar a `download_sync` directamente.
    """

    thread = threading.Thread(target=download_sync, args=(url, download_dir, forced_type, callback, job_id, logs_dir))
    thread.start()


def download_sync(url: str, download_dir: str, forced_type: str = None, callback=None, job_id: str = None, logs_dir: str | Path = None):
    """Ejecución síncrona de la descarga (no lanza threads).

    Esta función realiza todo el flujo: validación, ejecución de `spotdl`, registro en `job.log`,
    movimiento de archivos y escritura de `meta-<job_id>.json`.
    """
    BASE_DIR = Path(__file__).resolve().parent.parent

    download_path = Path(download_dir)
    download_path.mkdir(parents=True, exist_ok=True)

    # Prepare job id and logs directory
    if not job_id:
        job_id = uuid.uuid4().hex[:8]

    if logs_dir:
        logs_base = Path(logs_dir)
    else:
        # default logs directory at repo/logs
        logs_base = Path(__file__).resolve().parent.parent / "logs"

    job_logs_dir = logs_base / job_id
    job_logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = job_logs_dir / f"job-{job_id}.log"

    # Use a tmp directory separated from downloads and logs: <repo>/tmp/<job_id>/
    tmp_base = BASE_DIR / "tmp"
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
            "type": forced_type or "unknown",
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
            process = subprocess.run(
                ["spotdl", url, "--output", str(tmp_dir)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            # dump output to log (full output kept in the job log)
            raw_output = process.stdout or ""
            logf.write(raw_output)

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
            "type": forced_type or "unknown",
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
            "type": forced_type or "unknown",
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