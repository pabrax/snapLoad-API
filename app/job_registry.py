import threading
import os
import signal
from typing import Optional

_lock = threading.Lock()
# Map job_id -> subprocess.Popen
_registry: dict[str, object] = {}


def register_job(job_id: str, proc) -> None:
    with _lock:
        _registry[job_id] = proc


def unregister_job(job_id: str) -> None:
    with _lock:
        _registry.pop(job_id, None)


def get_job_proc(job_id: str):
    with _lock:
        return _registry.get(job_id)


def terminate_job(job_id: str, timeout: float = 5.0) -> bool:
    """Attempt to terminate the process for job_id. Returns True if a process was signalled."""
    proc = get_job_proc(job_id)
    if not proc:
        return False
    try:
        # try graceful
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

        # wait for it to exit briefly
        try:
            proc.wait(timeout=timeout)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    finally:
        unregister_job(job_id)
    return True


def terminate_all():
    with _lock:
        ids = list(_registry.keys())
    for jid in ids:
        try:
            terminate_job(jid)
        except Exception:
            pass
