"""
Rutas de health check y bienvenida.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..core.config import settings
from ..core.process import find_binary
from ..schemas import HealthResponse, BinaryInfo

router = APIRouter(tags=["Health"])


@router.get("/")
def read_root():
    """Endpoint de bienvenida."""
    return JSONResponse(content={"message": "Bienvenido a SnapLoad API"})


@router.get("/health", response_model=HealthResponse)
def health_check():
    """
    Healthcheck que valida presencia de binarios externos requeridos.
    
    Returns:
        200: Todos los binarios disponibles
        503: Falta algún binario requerido
    """
    binaries_status = {}
    all_ok = True
    
    for name, exe in settings.REQUIRED_BINARIES.items():
        path = find_binary(exe)
        ok = path is not None
        binaries_status[name] = {"installed": ok, "path": path}
        
        if not ok:
            all_ok = False
    
    status_code = 200 if all_ok else 503
    status = "ok" if all_ok else "degraded"
    
    return JSONResponse(
        status_code=status_code,
        content={"status": status, "binaries": binaries_status}
    )


