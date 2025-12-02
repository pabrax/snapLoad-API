
from dotenv import load_dotenv
import uvicorn

if __name__ == "__main__":
    # Cargar variables de entorno desde .env
    load_dotenv()
    
    # uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=True) # for development
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000)

