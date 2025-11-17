# SDAPI — MVP Specification

Fecha: 2025-11-16

Este documento resume las decisiones y el diseño del MVP para el servicio de descargas (usando `spotdl`), incluyendo el formato de `meta.json`, reglas de inferencia desde URLs de Spotify, estructura final de ficheros, logs y comportamiento esperado.

## Objetivo

Proveer un servicio local que reciba peticiones para descargar contenido desde Spotify (tracks, albums, playlists), ejecute `spotdl` y almacene los ficheros en una jerarquía organizada por artista y álbum. Para la primera versión (MVP):

- No habrá persistencia externa (todo en memoria y ficheros); no se usará Redis/Celery.
- No habrá cola compleja; cada petición iniciará la descarga (podemos añadir límites luego).
- La API aceptará únicamente URLs/URIs de Spotify (`open.spotify.com` y `spotify:`).
- La "notificación" al completar será simulada por consola (más tarde se añadirá webhook real).
- Se generará `job.log` (registro humano) y `meta.json` (consumo programático) por descarga.

## Estructura de ficheros

Raíz de descargas: `downloads/`
# SDAPI — MVP Specification

Fecha: 2025-11-16

Este documento resume las decisiones y el diseño del MVP para el servicio de descargas (usando `spotdl`), incluyendo el formato de `meta.json`, reglas de operación para la primera versión, estructura final de ficheros, logs y comportamiento esperado.

## Objetivo

Proveer un servicio local que reciba peticiones para descargar contenido desde Spotify (tracks, albums, playlists), ejecute `spotdl` y almacene los ficheros en una ubicación compartida `downloads/`. Para la primera versión (MVP):

- No habrá persistencia externa (todo en memoria y ficheros); no se usará Redis/Celery.
- No habrá cola compleja; cada petición iniciará la descarga (podemos añadir límites luego).
- La API aceptará únicamente URLs/URIs de Spotify (`open.spotify.com` y `spotify:`).
- La "notificación" al completar será simulada por consola (más tarde se añadirá webhook real).
- Se generará `job.log` (registro humano) y `meta.json` (consumo programático) por descarga.

## Estructura de ficheros (MVP)

Raíz de descargas: `downloads/`

- Todos los ficheros descargados se colocarán en la raíz `downloads/` (o en un directorio temporal `downloads/tmp-<job_id>` durante la descarga y después movidos a `downloads/`).
- No se realizará agrupamiento por `artist`/`album` en esta versión funcional. La organización por artista/álbum queda para la versión 2.

Notas:
- Los nombres de fichero se "sanitizan": se reemplazan o eliminan caracteres no permitidos (`/`, `\0`, etc.), se normaliza Unicode y se limitan longitudes para evitar problemas.
- Mantener los ficheros en la raíz `downloads/` facilita el consumo por otros servicios que leen desde ese directorio compartido.

## Formato de `meta.json`

`meta.json` es un archivo JSON con metadata programática sobre el job y los resultados. Debe ser legible por otros servicios para automatización.

Campos propuestos:

- `job_id` (string): identificador interno.
- `url` (string): la URL/URI de Spotify solicitada.
- `type` (string): `track | album | playlist | unknown` — inferido desde la URL o provisto en el payload.
- `source_id` (string|null): id extraída de la URL (por ejemplo `3K8xpeyxqmNeInA7WcLgII`).
- `artist` (string|null): nombre inferido (en esta versión normalmente `null`).
- `album` (string|null): nombre inferido (en esta versión normalmente `null`).
- `created_at`, `started_at`, `finished_at` (ISO timestamps): marcas temporales.
- `status` (string): `queued | running | success | failed`.
- `files` (array of objects): lista de ficheros resultantes con datos mínimos:
  - `name` (string)
  - `path` (string)
  - `size_bytes` (number)
- `log_path` (string): ruta al `job.log`.
- `error` (string|null): texto de error (stderr o resumen) si ocurrió.
- `inferred_from_filenames` (boolean): indica si `artist`/`album` se obtuvieron a partir de los nombres de fichero (en MVP será `false`).
- `raw_spotdl_summary` (string|null): resumen breve extraído de la salida de `spotdl` (opcional).

Ejemplo:

```json
{
  "job_id": "a1b2c3d4",
  "url": "https://open.spotify.com/album/1llfWsTfOoTmG3vK0cdyNr",
  "type": "album",
  "source_id": "1llfWsTfOoTmG3vK0cdyNr",
  "artist": null,
  "album": null,
  "created_at": "2025-11-16T12:00:00Z",
  "started_at": "2025-11-16T12:00:05Z",
  "finished_at": "2025-11-16T12:02:10Z",
  "status": "success",
  "files": [
    {"name": "01 - Título.mp3", "path": "downloads/01 - Título.mp3", "size_bytes": 4523456}
  ],
  "log_path": "downloads/job-a1b2c3d4.log",
  "error": null,
  "inferred_from_filenames": false,
  "raw_spotdl_summary": "Downloaded 10 tracks"
}
```

### Consumo programático

- Otros servicios pueden `GET /download/<job_id>/meta` (endpoint que añadiremos) o leer directamente el `meta.json` si comparten el filesystem.
- `meta.json` permite comprobar estado, rutas de ficheros y errores sin parsear logs.
- Con `status` y `files` se puede automatizar el siguiente paso (por ejemplo mover, indexar o notificar a otro servicio).

## job.log

`job.log` contiene la salida completa (stdout+stderr) de `spotdl` y eventos importantes (timestamps, inicio/fin, movimientos de ficheros). Se guarda en la carpeta temporal o en la raíz `downloads/` y su ruta aparece en `meta.json`.

Ejemplo de entradas en `job.log`:

```
[2025-11-16T12:00:05Z] JOB a1b2c3d4 START url=https://open.spotify.com/album/...
[2025-11-16T12:00:06Z] RUN: spotdl https://open.spotify.com/album/... --output /tmp/...
[... spotdl stdout/stderr ...]
[2025-11-16T12:02:10Z] JOB a1b2c3d4 FINISH status=success files=10
```

Se recomienda guardar la salida completa para debugging; `meta.json` contiene sólo un resumen estructurado.

## Inferencia de `artist` / `album`

- Para esta primera entrega (MVP) la inferencia automática de `artist` y `album` queda aplazada. Aunque `spotdl` suele generar ficheros con patrones como `Artist - Title.ext`, en la versión inicial no se usará esa heurística para reorganizar ficheros.
- La inferencia y reordenación por artista/álbum se implementará en la versión 2, donde se podrá optar por heurísticas locales o por consultar la API de Spotify para metadatos precisos.

## Sanitización de nombres

Reglas básicas aplicadas a los nombres de fichero y a los nombres de carpeta temporales:
- Reemplazar barras `/` por `-` o espacio, eliminar caracteres de control.
- Limitar longitud de cada componente (ej. 150 chars) para evitar límites del sistema de ficheros.
- Normalizar Unicode (NFC).
- Eliminar caracteres no imprimibles.

Nota: dado que los ficheros se quedarán en la raíz `downloads/` en esta versión, la sanitización de nombres de fichero es especialmente importante para evitar conflictos y caracteres inválidos en el sistema de ficheros.

## Verificación de existencia de ficheros para marcar success

- Tras finalizar `spotdl`, listar archivos de audio comunes: `*.mp3`, `*.m4a`, `*.flac`, `*.wav`, `*.aac`.
- Si se encuentra al menos un archivo válido → `success`.
- Registrar en `meta.json` la lista completa con tamaños.

En esta versión, la confirmación de la descarga se basa en la presencia de los ficheros descargados en `downloads/` (o en el directorio temporal usado durante la descarga). No se requerirá haber inferido `artist`/`album`.

## Reglas de URLs/Inferencia desde Spotify

- Detectar tipo por la ruta del URL:
  - `/track/` → `track`
  - `/album/` → `album`
  - `/playlist/` → `playlist`
  - `spotify:track:<id>` o `spotify:album:<id>` → similar
- Extraer `source_id` para poder referenciarlo en futuras integraciones.

## Notificación (MVP)

- Al terminar, imprimir en consola: `JOB <job_id> STATUS <status> FILES <n> PATH <path>`; esto simula el webhook.
- En el futuro, añadiremos `webhook_url` y reintentos con backoff.

## Ejemplos de payloads (API)

- Request mínima para descargar (MVP):

```json
{ "url": "https://open.spotify.com/track/3K8xpeyxqmNeInA7WcLgII" }
```

- Opcionalmente se puede enviar `type` para forzar interpretación:

```json
{ "url": "https://open.spotify.com/album/...", "type": "album" }
```

## Siguientes pasos para la implementación (ordenados)

1. Refactorizar `download_controller` para:
   - Crear `tmp` dir por job (ej. `downloads/tmp-<job_id>`).
   - Ejecutar `spotdl` apuntando a ese `tmp` y volcar stdout/stderr en `job.log`.
   - Tras finalizar, mover los ficheros descargados directamente a `downloads/` (o dejar en `downloads/tmp-<job_id>` si prefieres mantener la separación).
   - Generar `meta.json` con el esquema arriba descrito (con `artist` y `album` posiblemente `null`) y notificar por consola.

2. Añadir validación básica de URLs en `app/api.py`.
3. Probar localmente con ejemplos `track` y `album`.
4. Documentar requisitos del sistema (`ffmpeg`, `spotdl` en PATH) y comandos para correr la app. (queda para la version 2)

---

Este documento será usado como referencia para la versión 2 cuando integremos persistencia, webhooks reales, cola/limites y (opcionalmente) la API de Spotify para metadatos más precisos.
