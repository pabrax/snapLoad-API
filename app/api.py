from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from .download_controller import download_sync


BASE_DIR = Path(__file__).resolve().parent.parent  # raíz del proyecto
DOWNLOAD_DIR = BASE_DIR / "downloads"

class DownloadRequest(BaseModel):
    url: str
    type: Optional[str] = None

app = FastAPI(
    title="SDAPI",
    description="API para descargar música de Spotify usando spotdl",
    version="1.0.0"
)

@app.post("/download")
def download_endpoint(payload: DownloadRequest, background_tasks: BackgroundTasks):
    try:
        # Encolar la tarea en el background task de FastAPI (usa threadpool internamente)
        background_tasks.add_task(download_sync, payload.url, DOWNLOAD_DIR, payload.type)

        return JSONResponse(content={
            "message": "Descarga iniciada",
            "url": payload.url
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return JSONResponse(content={"message": "Bienvenido a SDAPI"})