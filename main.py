
from dotenv import load_dotenv

# app.core.config lee os.environ al importarse: el .env debe cargarse antes
load_dotenv()

import uvicorn  # noqa: E402
from app.core.config import settings  # noqa: E402

if __name__ == "__main__":
    # Usar configuración centralizada
    uvicorn.run(
        "app.api:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        workers=settings.WORKERS if not settings.RELOAD else 1
    )

