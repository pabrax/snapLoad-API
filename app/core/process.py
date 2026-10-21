"""
Helpers de subprocesos multiplataforma.
Agrupa el proceso hijo (yt-dlp/spotdl lanzan ffmpeg) para poder terminarlo completo
tanto en POSIX (Docker/Linux) como en Windows.
"""
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional


def popen_kwargs(windows: Optional[bool] = None) -> dict:
    """
    Argumentos de Popen que crean un nuevo grupo de procesos.

    Args:
        windows: Fuerza la plataforma (solo para tests); por defecto detecta el SO

    Returns:
        Dict para expandir en subprocess.Popen(**kwargs)
    """
    if windows is None:
        windows = os.name == "nt"
    if windows:
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)}
    return {"start_new_session": True}


def terminate_process(
    process: subprocess.Popen,
    timeout: float = 5.0,
    windows: Optional[bool] = None,
) -> None:
    """
    Termina un proceso y sus hijos. No falla si el proceso ya terminó.

    POSIX: SIGTERM al grupo, SIGKILL si no sale a tiempo.
    Windows: taskkill /T /F sobre el árbol de procesos.

    Args:
        process: Proceso a terminar
        timeout: Segundos de espera antes de forzar (POSIX)
        windows: Fuerza la plataforma (solo para tests); por defecto detecta el SO
    """
    if process.poll() is not None:
        return

    if windows is None:
        windows = os.name == "nt"

    if windows:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
        )
        try:
            process.wait(timeout=timeout)
        except Exception:
            pass
        return

    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass

    try:
        process.wait(timeout=timeout)
    except Exception:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


def find_binary(name: str) -> Optional[str]:
    """
    Localiza un ejecutable (yt-dlp, spotdl, ffmpeg) sin depender de que el venv esté activado.

    Busca en PATH y, si no está, junto al intérprete actual (Scripts/ en Windows, bin/ en POSIX).

    Args:
        name: Nombre del ejecutable

    Returns:
        Ruta absoluta o None si no se encuentra
    """
    found = shutil.which(name)
    if found:
        return found
    return shutil.which(name, path=str(Path(sys.executable).parent))


def resolve_binary(name: str) -> str:
    """
    Igual que find_binary pero devuelve el nombre tal cual si no se encuentra,
    de modo que Popen falle luego con un error claro.
    """
    return find_binary(name) or name
