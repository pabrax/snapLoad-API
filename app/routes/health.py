from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Health"])

@router.get("/")
def read_root():
    return JSONResponse(content={"message": "Bienvenido a CCAPI"})


@router.get("/health")
def health_check():
    """Healthcheck que valida presencia de binarios externos requeridos.

    Devuelve 200 cuando todos los binarios están disponibles, 503 si falta alguno.
    """
    from shutil import which

    binaries = {
        "yt-dlp": "yt-dlp",
        "spotdl": "spotdl",
        "ffmpeg": "ffmpeg",
    }
    result = {}
    all_ok = True
    for name, exe in binaries.items():
        path = which(exe)
        ok = path is not None
        result[name] = {"installed": ok, "path": path}
        if not ok:
            all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(status_code=status_code, content={"status": "ok" if all_ok else "degraded", "binaries": result})

