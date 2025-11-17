from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from pydantic import BaseModel
from pathlib import Path
from .utils import notify

from .download_controller import download


BASE_DIR = Path(__file__).resolve().parent.parent  # raíz del proyecto
DOWNLOAD_DIR = BASE_DIR / "downloads"

class DownloadRequest(BaseModel):
    url: str

app = FastAPI(
    title="SDAPI",
    description="API para descargar música de Spotify usando spotdl",
    version="1.0.0"
)

@app.post("/download")
def download_endpoint(payload: DownloadRequest):
    try:
        # Llamamos a la función download pasando la URL recibida y el directorio definido
        download(
            url=payload.url, 
            download_dir=DOWNLOAD_DIR,
            callback=notify
        )

        return JSONResponse(content={
            "message": "Descarga iniciada",
            "url": payload.url
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return JSONResponse(content={"message": "Bienvenido a SDAPI"})