
# SDAPI — Servicio ligero para descargar desde Spotify (spotdl)

Este pequeño servicio ofrece una API local para encolar descargas con `spotdl`, guardar registros y exponer metadatos que permiten comprobar el estado de cada trabajo (job). Está diseñado para uso en una infraestructura doméstica o laboratorio local — no está pensado para exponerse públicamente sin medidas de seguridad adicionales.

---

## Resumen rápido

- `POST /download` : encola una descarga (recibe una URL/URI de Spotify) y devuelve un `job_id`.
- `GET /meta/{job_id}` : devuelve el fichero `meta` completo con información del job (status, ficheros movidos, trazas truncadas).
- `GET /status/{job_id}` : vista ligera del estado del job (`queued|running|success|failed`).
- `GET /download/{job_id}/status` : alias hacia el endpoint `status`.

Los archivos resultantes se mueven a la carpeta `downloads/`. Los logs y metadatos se guardan en el repositorio en las carpetas `logs/`, `meta/` y `tmp/`.

---

## Requisitos del sistema

Antes de usar este servicio necesitas estas dependencias instaladas en la máquina donde se ejecutará:

- Python 3.10+ (compatible con los ficheros del proyecto).
- `spotdl` disponible en `PATH` (instalado globalmente o en el entorno virtual). spotdl a su vez requiere `ffmpeg` y `yt-dlp`.
- `ffmpeg` en `PATH` (usado por spotdl para la transcodificación).

En sistemas tipo Debian/Ubuntu puedes instalar `ffmpeg` así:

```bash
sudo apt update && sudo apt install ffmpeg -y
```

Instalar `spotdl` (ejemplo con pip):

```bash
pip install spotdl
```

Nota: si `spotdl` se instala en un entorno virtual, arranca el servidor con el mismo entorno para que el binario esté disponible.

---

## Instalación y arranque

Desde la raíz del proyecto (`/home/pablo/desarrollos` en este repo):

```bash
# crear y activar virtualenv (opcional pero recomendado)
python -m venv .venv
source .venv/bin/activate

# instalar dependencias del proyecto (si las declaraste en pyproject/requirements)
pip install -r requirements.txt || true

# arrancar el servidor (modo desarrollo con autoreload)
uvicorn main:app --reload
```

El servidor arranca por defecto en `http://127.0.0.1:8000` (puedes ajustar host/puerto con las opciones de `uvicorn`).

---

## Endpoints y uso

1) Encolar una descarga

`POST /download`

Payload JSON de ejemplo:

```json
{
	"url": "https://open.spotify.com/track/....",
	"type": null
}
```

Respuesta (ejemplo):

```json
{
	"message": "Descarga encolada",
	"job_id": "a1b2c3d4",
	"url": "https://open.spotify.com/track/..."
}
```

Usando `curl`:

```bash
curl -X POST -H "Content-Type: application/json" \
	-d '{"url":"https://open.spotify.com/track/......"}' \
	http://127.0.0.1:8000/download
```

2) Consultar metadatos completos del job

`GET /meta/{job_id}`

Devuelve el fichero `meta/meta-<job_id>.json` con información detallada:

- `job_id`, `url`, `type` (si fue provisto), `created_at`, `started_at`, `finished_at`.
- `status` : `queued | running | success | failed`.
- `files` : lista de ficheros movidos a `downloads/` con `name`, `path` y `size_bytes`.
- `log_path` : ruta al `job-<job_id>.log` dentro de `logs/`.
- `error` : si falló, contiene las últimas líneas relevantes del output de `spotdl` (truncado para evitar JSON gigantes).

Ejemplo de consulta con `curl`:

```bash
curl http://127.0.0.1:8000/meta/a1b2c3d4
```

3) Estado ligero del job

`GET /status/{job_id}` (o `GET /download/{job_id}/status`)

Este endpoint es una vista rápida que permite saber si el job está `queued`, `running` o ya terminó (`success`/`failed`).

Comprobaciones internas que realiza:

- Si existe `meta/meta-<job_id>.json` devuelve su `status` y la `meta` (fuente de verdad).
- Si no existe meta pero existe `logs/<job_id>/job-<job_id>.log` devuelve `running` (la tarea ha arrancado o está produciendo log).
- Si existe `logs/<job_id>/` pero no log ni meta devuelve `queued`.

Ejemplo con `curl`:

```bash
curl http://127.0.0.1:8000/status/a1b2c3d4
```

---

## Estructura de ficheros producida

- `downloads/` : destino final de los archivos de audio descargados.
- `logs/<job_id>/job-<job_id>.log` : log completo (texto) con la salida de `spotdl`.
- `tmp/<job_id>/` : directorio temporal donde `spotdl` escribe antes de mover archivos.
- `meta/meta-<job_id>.json` : metadatos del job, utilizado para polling.

Si quieres recuperar manualmente un log o un fichero generado, revisa `logs/` y `downloads/`.

---

## Comportamiento y garantías

- Las descargas se lanzan como tareas en segundo plano (FastAPI BackgroundTasks). El endpoint `POST /download` responde inmediatamente con un `job_id` y la descarga continúa en background.
- La API valida que la URL sea una `open.spotify.com` o una URI de Spotify y rechazará otras URLs con `400 Bad Request`.
- Los logs completos se guardan en disco. El `meta` incluye una versión truncada del output para facilitar lectura por parte de clientes.
- Notificación: por ahora la "webhook" es una notificación por consola (print). Puedes cambiar el comportamiento pasando un `callback` en el código.

---

## Seguridad y uso recomendado

Este servicio no añade autenticación ni control de acceso. Recomendaciones si lo vas a exponer fuera de una máquina local:

- Añade un proxy inverso (nginx) y HTTPS.
- Implementa un mecanismo de autenticación (API key / JWT).
- Limita la tasa de peticiones y el tamaño de cola estableciendo políticas antes de aceptar nuevos jobs.

