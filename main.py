
from dotenv import load_dotenv
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    # Cargar variables de entorno desde .env
    load_dotenv()
    
    # Usar configuración centralizada
    uvicorn.run(
        "app.api:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        workers=settings.WORKERS if not settings.RELOAD else 1
    )

