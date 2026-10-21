"""Cross-platform subprocess helpers: spawn flags and process-tree termination."""
import subprocess
import sys
import time

from app.core.process import popen_kwargs, terminate_process


def test_popen_kwargs_posix_uses_new_session():
    assert popen_kwargs(windows=False) == {"start_new_session": True}


def test_popen_kwargs_windows_uses_new_process_group():
    kwargs = popen_kwargs(windows=True)
    assert "start_new_session" not in kwargs and "preexec_fn" not in kwargs
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)


def test_terminate_process_kills_a_running_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **popen_kwargs())
    assert proc.poll() is None
    started = time.time()
    terminate_process(proc, timeout=5)
    assert proc.poll() is not None
    assert time.time() - started < 10


def test_terminate_process_is_idempotent_on_finished_process():
    proc = subprocess.Popen([sys.executable, "-c", "pass"], **popen_kwargs())
    proc.wait()
    terminate_process(proc, timeout=1)  # must not raise


def test_resolve_binary_finds_venv_script_without_path(monkeypatch):
    from app.core.process import resolve_binary

    monkeypatch.setenv("PATH", "")
    resolved = resolve_binary("yt-dlp")
    assert resolved != "yt-dlp" and "yt-dlp" in resolved.lower()


def test_resolve_binary_falls_back_to_bare_name(monkeypatch):
    from app.core.process import resolve_binary

    monkeypatch.setenv("PATH", "")
    assert resolve_binary("definitely-not-a-binary") == "definitely-not-a-binary"
