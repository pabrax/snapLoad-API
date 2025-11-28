
# CCAPI - Content Collector API

Este pequeño servicio ofrece una API local para encolar descargas con `spotdl` (Spotify) y `yt-dlp` (YouTube y otras fuentes), guardar registros y exponer metadatos que permiten comprobar el estado de cada trabajo (job). Está diseñado para uso en una infraestructura doméstica o laboratorio local — no está pensado para exponerse públicamente sin medidas de seguridad adicionales.

---

## Resumen rápido

- `POST /download` : encola una descarga (recibe una URL/URI de Spotify o una URL de YouTube/otras fuentes soportadas por `yt-dlp`) y devuelve un `job_id`.
- `GET /meta/{job_id}` : devuelve el fichero `meta` completo con información del job (status, ficheros movidos, trazas truncadas).
- `GET /status/{job_id}` : vista ligera del estado del job (`queued|running|success|failed`).
- `GET /download/{job_id}/status` : alias hacia el endpoint `status`.

Los archivos resultantes se mueven a la carpeta `downloads/`. Los logs y metadatos se guardan en el repositorio en las carpetas `logs/`, `meta/` y `tmp/`.

---

## Requisitos del sistema

Antes de usar este servicio necesitas estas dependencias instaladas en la máquina donde se ejecutará:

- Python 3.10+.
- `spotdl` (para descargas desde Spotify) — opcional si solo usas `yt-dlp`.
- `yt-dlp` (para YouTube y muchas otras plataformas).
- `ffmpeg` en `PATH` (usado para transcodificación por ambas herramientas).

En Debian/Ubuntu:

```bash
sudo apt update && sudo apt install -y ffmpeg
```

Instalar herramientas (ejemplo en virtualenv):

```bash
pip install -U yt-dlp
pip install spotdl    # opcional, necesario para Spotify vía spotdl
```

Nota: si `spotdl` o `yt-dlp` se instalan en un entorno virtual, arranca el servidor con el mismo entorno para que los binarios estén disponibles.

---

## Instalación y arranque

Desde la raíz del proyecto:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt || true
uvicorn main:app --reload
```

El servidor arranca por defecto en `http://127.0.0.1:8000`.

---

## Endpoints y uso

1) Encolar una descarga

`POST /download`

Payload JSON de ejemplo:

```json
{
	"url": "https://open.spotify.com/track/....",
	"type": "audio"        # "audio" | "video" | null
}
```

También puedes enviar URLs de YouTube:

```json
{
	"url": "https://www.youtube.com/watch?v=....",
	"type": "video"
}
```

Respuesta (ejemplo):

```json
{
	"message": "Descarga encolada",
	"job_id": "a1b2c3d4",
	"url": "https://..."
}
```

Usando `curl`:

```bash
curl -X POST -H "Content-Type: application/json" \
	-d '{"url":"https://www.youtube.com/watch?v=......","type":"audio"}' \
	http://127.0.0.1:8000/download
```

2) Consultar metadatos completos del job

`GET /meta/{job_id}`

Devuelve `meta/meta-<job_id>.json` con información detallada (`job_id`, `url`, `type`, timestamps, `status`, `files`, `log_path`, `error`).

```bash
curl http://127.0.0.1:8000/meta/a1b2c3d4
```

3) Estado ligero del job

`GET /status/{job_id}` (o `GET /download/{job_id}/status`)

Proporciona `queued`, `running`, `success` o `failed`. Lógica de comprobación basada en la existencia de `meta` y logs.

```bash
curl http://127.0.0.1:8000/status/a1b2c3d4
```

---

## Estructura de ficheros producida

- `downloads/` : ficheros finales (mp3, m4a, mp4, etc.).
- `logs/<job_id>/job-<job_id>.log` : log completo con la salida de `yt-dlp` o `spotdl`.
- `tmp/<job_id>/` : directorio temporal usado durante la descarga.
- `meta/meta-<job_id>.json` : metadatos del job.

---

## Comportamiento y garantías

- Las descargas se lanzan como tareas en segundo plano (FastAPI BackgroundTasks). `POST /download` responde inmediatamente con un `job_id`.
- La API valida que la URL sea una de las fuentes soportadas (p. ej. `open.spotify.com`, `spotify:track:...`, `youtube.com`, `youtu.be`) y rechazará otras con `400 Bad Request`.
- Para Spotify se utiliza `spotdl` cuando corresponde; para YouTube y otras plataformas se usa `yt-dlp`. El `meta` incluye un resumen/truncado del output y la ruta al log completo.
- Notificación: por ahora la "webhook" es una notificación por consola (print). Puedes cambiar el comportamiento pasando un `callback` en el código.

---

## Seguridad y uso recomendado

No se incluye autenticación por defecto. Si vas a exponer el servicio fuera de la red local, añade:

- Proxy inverso (nginx) con TLS.
- Autenticación (API keys, JWT) y control de acceso.
- Límites de concurrencia y limpieza de disco para evitar llenado de almacenamiento.

---

## Notas finales

- Respeta los términos de servicio de las plataformas al descargar contenido.
- Revisa `logs/` y `meta/` para diagnóstico cuando las descargas fallen.
- Si necesitas soporte para otras plataformas, `yt-dlp` cubre una gran cantidad de fuentes y puedes ajustar opciones en el payload `options`.

