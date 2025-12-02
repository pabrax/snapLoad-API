<div align="center">

# 🚀 SnapLoad API

**API REST para descargar contenido de YouTube y Spotify**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.103+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-red?style=flat&logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
[![spotdl](https://img.shields.io/badge/spotdl-4.4+-1DB954?style=flat&logo=spotify&logoColor=white)](https://github.com/spotDL/spotify-downloader)

*API asíncrona de alto rendimiento para descargas de medios con cola de trabajos, seguimiento de progreso y gestión automática de almacenamiento.*

[Cliente Web Oficial](https://github.com/pabrax/SnapLoad) | [Documentación API](#-referencia-de-api) | [Reportar Problemas](https://github.com/pabrax/SnapLoad/issues)

[🇬🇧 English](../README.md) | **🇪🇸 Español**

</div>

---

## 📋 Tabla de Contenidos

- [Descripción General](#-descripción-general)
- [Características](#-características)
- [Inicio Rápido](#-inicio-rápido)
- [Instalación](#-instalación)
- [Configuración](#-configuración)
- [Referencia de API](#-referencia-de-api)
- [Gestión de Almacenamiento](#-gestión-de-almacenamiento)
- [Desarrollo](#-desarrollo)
- [Despliegue con Docker](#-despliegue-con-docker)
- [Solución de Problemas](#-solución-de-problemas)
- [Aviso Legal](#%EF%B8%8F-aviso-legal)
- [Licencia](#-licencia)

---

## 🌟 Descripción General

**SnapLoad API** es una API REST lista para producción construida con FastAPI que proporciona descarga asíncrona de medios desde YouTube, Spotify y más de 1000 sitios. Diseñada para servidores con recursos limitados con limpieza automática, gestión de trabajos y manejo integral de errores.

### Características Principales

- ⚡ **Procesamiento Asíncrono**: Ejecución de trabajos en segundo plano con respuesta API inmediata
- 🎯 **Gestión Inteligente de Trabajos**: IDs únicos con seguimiento completo del ciclo de vida
- 🌐 **Multi-Plataforma**: YouTube, Spotify, SoundCloud y más vía yt-dlp
- 📊 **Seguimiento de Progreso**: Actualizaciones de estado en tiempo real y metadatos detallados
- 🧹 **Limpieza Automática**: Políticas de retención configurables para gestionar almacenamiento
- 🔒 **Listo para Producción**: Health checks, manejo de errores y registro completo
- 📦 **Gestión de Archivos**: Descarga archivos individuales o archivos completos (playlists/álbumes)

### Plataformas Soportadas

- **YouTube**: Videos, playlists, canales (audio/video)
- **Spotify**: Tracks, álbumes, playlists (descarga vía búsqueda en YouTube)
- **Más de 1000 sitios**: Todo lo soportado por [yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

---

## 🚀 Inicio Rápido

### Requisitos Previos

- Python 3.12+
- ffmpeg
- Conexión a Internet

### Instalación

```bash
# Clonar repositorio
git clone https://github.com/pabrax/SnapLoad.git
cd SnapLoad/snapLoad-API

# Instalar uv (gestor de paquetes recomendado)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instalar dependencias
uv sync

# Configurar entorno
cp .env.example .env
# Editar .env con tus configuraciones preferidas

# Ejecutar servidor
uv run python main.py
```

El servidor estará disponible en `http://localhost:8000`

### Prueba Rápida

```bash
# Descargar un video de YouTube
curl -X POST http://localhost:8000/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "quality": "192"}'

# Respuesta: {"job_id": "abc123", "status": "queued", "message": "Download queued"}

# Verificar estado
curl http://localhost:8000/status/abc123

# Descargar archivo cuando esté listo
curl http://localhost:8000/files/abc123/download/filename.mp3 -O
```

---

## 📦 Instalación

### Usando uv (Recomendado)

```bash
# Instalar uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clonar y configurar
git clone https://github.com/pabrax/SnapLoad.git
cd SnapLoad/snapLoad-API
uv sync
```

### Usando pip

```bash
# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### Dependencias del Sistema

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg python3-pip
```

**macOS:**
```bash
brew install ffmpeg python@3.12
```

**Windows:**
- Instalar [Python 3.12+](https://www.python.org/downloads/)
- Instalar [ffmpeg](https://www.gyan.dev/ffmpeg/builds/)
- Agregar ffmpeg al PATH

---

## ⚙️ Configuración

La configuración se gestiona mediante variables de entorno en el archivo `.env`:

```bash
# Configuración de Limpieza (Importante para VPS/Almacenamiento Limitado)
RETENTION_HOURS=3                    # Mantener archivos por 3 horas
TEMP_RETENTION_HOURS=0.5             # Limpiar archivos temporales después de 30 minutos
CLEANUP_SCHEDULE_ENABLED=true        # Habilitar limpieza automática
CLEANUP_CRON="0 * * * *"             # Limpiar cada hora
TEMP_CLEANUP_CRON="0 */2 * * *"      # Limpiar temporales cada 2 horas

# Endpoints Admin (Deshabilitar en producción)
ENABLE_ADMIN_ENDPOINTS=false         # Establecer en true solo para testing/desarrollo

# Logging
CLEANUP_LOG_LEVEL=INFO               # DEBUG, INFO, WARNING, ERROR
CLEANUP_LOG_RETENTION_DAYS=7         # Mantener logs de limpieza por 7 días

# Modo Testing
CLEANUP_DRY_RUN=false                # Establecer en true para simular sin eliminar
```

### Presets de Configuración

**Desarrollo (Limpieza Rápida para Testing):**
```bash
RETENTION_HOURS=0.08              # 5 minutos
CLEANUP_CRON="*/5 * * * *"        # Cada 5 minutos
ENABLE_ADMIN_ENDPOINTS=true
CLEANUP_DRY_RUN=true              # Solo simular
```

**Producción (Recomendado para VPS):**
```bash
RETENTION_HOURS=3                 # 3 horas
CLEANUP_CRON="0 * * * *"          # Cada hora
ENABLE_ADMIN_ENDPOINTS=false
```

**Producción (Más Almacenamiento Disponible):**
```bash
RETENTION_HOURS=24                # 24 horas
CLEANUP_CRON="0 */6 * * *"        # Cada 6 horas
ENABLE_ADMIN_ENDPOINTS=false
```

---

## 🔌 Referencia de API

### URL Base
```
http://localhost:8000
```

### Endpoints

#### 🏥 Health Check
```http
GET /health
```

**Respuesta:**
```json
{
  "status": "healthy",
  "timestamp": "2025-12-01T12:00:00Z",
  "binaries": {
    "yt-dlp": "available",
    "spotdl": "available",
    "ffmpeg": "available"
  }
}
```

---

#### 📥 Descargar Contenido
```http
POST /download
Content-Type: application/json
```

**Cuerpo de la Petición:**
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "quality": "192"  // "128", "192", "256", "320" para audio
}
```

**Respuesta:**
```json
{
  "job_id": "abc123",
  "status": "queued",
  "message": "Download queued successfully"
}
```

**Opciones de Calidad:**
- Audio: `"128"`, `"192"` (predeterminado), `"256"`, `"320"` (kbps)
- Video: `"480"`, `"720"`, `"1080"`, `"1440"`, `"2160"`

---

#### 📊 Verificar Estado del Trabajo
```http
GET /status/{job_id}
```

**Respuesta:**
```json
{
  "job_id": "abc123",
  "status": "success",  // queued, running, success, failed, cancelled
  "message": "Download completed",
  "meta": {
    "title": "Título del Video",
    "artist": "Nombre del Artista",
    "duration": "3:45",
    "progress": 100
  }
}
```

**Valores de Estado:**
- `queued`: Trabajo esperando para iniciar
- `running`: Descarga en progreso
- `success`: Completado exitosamente
- `failed`: Ocurrió un error
- `cancelled`: Usuario canceló

---

#### 📂 Listar Archivos
```http
GET /files/{job_id}
```

**Respuesta:**
```json
{
  "job_id": "abc123",
  "files": [
    {
      "name": "Artista - Canción.mp3",
      "size_bytes": 4567890,
      "size_mb": 4.36
    }
  ]
}
```

---

#### 💾 Descargar Archivo
```http
GET /files/{job_id}/download/{filename}
```

Descarga el archivo especificado.

---

#### 📦 Descargar Archivo (Playlists/Álbumes)
```http
GET /files/{job_id}/archive
```

Descarga todos los archivos como un archivo ZIP (para playlists/álbumes con múltiples tracks).

---

#### ❌ Cancelar Trabajo
```http
POST /cancel/{job_id}
```

**Respuesta:**
```json
{
  "job_id": "abc123",
  "status": "cancelled",
  "message": "Job cancelled successfully"
}
```

---

### Endpoints Admin (Solo Desarrollo)

Habilitar con `ENABLE_ADMIN_ENDPOINTS=true` en `.env`:

#### 🧹 Disparar Limpieza
```http
POST /admin/cleanup/trigger
Content-Type: application/json
```

**Petición:**
```json
{
  "targets": ["all"],  // "downloads", "logs", "metadata", "temp", "database", "all"
  "strategy": "age_based",
  "dry_run": false
}
```

---

#### 📊 Estadísticas de Almacenamiento
```http
GET /admin/storage/stats
```

---

#### ⏰ Programación de Limpieza
```http
GET /admin/cleanup/schedule
```

---

#### ⚙️ Configuración de Limpieza
```http
GET /admin/cleanup/config
```

---

## 🗂️ Gestión de Almacenamiento

SnapLoad incluye un sistema de limpieza automática diseñado para servidores con recursos limitados.

### Cómo Funciona

1. **Limpieza Basada en Edad**: Los archivos más antiguos que `RETENTION_HOURS` se eliminan
2. **Ejecución Programada**: Se ejecuta automáticamente basado en `CLEANUP_CRON`
3. **Integral**: Limpia descargas, logs, metadatos, archivos temporales y entradas de base de datos
4. **Segura**: Solo elimina trabajos completados/fallidos, nunca descargas activas

### Estructura de Directorios

```
snapLoad-API/
├── downloads/          # Archivos de medios descargados
│   ├── audio/         # Archivos de audio organizados por calidad
│   └── video/         # Archivos de video organizados por formato
├── logs/              # Logs de descarga y limpieza
│   ├── cleanup/       # Logs de operaciones de limpieza
│   ├── spotify/       # Logs de descargas de Spotify
│   └── yt/            # Logs de descargas de YouTube
├── meta/              # Metadatos de trabajos (JSON)
└── tmp/               # Archivos temporales durante el procesamiento
    ├── archives/      # Archivos ZIP temporales
    ├── spotify/       # Archivos temporales de Spotify
    └── yt/            # Archivos temporales de YouTube
```

### Limpieza Manual

```bash
# Disparar limpieza vía API (con endpoints admin habilitados)
curl -X POST http://localhost:8000/admin/cleanup/trigger \
  -H "Content-Type: application/json" \
  -d '{"targets": ["all"], "dry_run": false}'

# Verificar estadísticas de almacenamiento
curl http://localhost:8000/admin/storage/stats
```

---

## 🛠️ Desarrollo

### Estructura del Proyecto

```
snapLoad-API/
├── app/
│   ├── api.py                  # App FastAPI y lifespan
│   ├── routes/                 # Endpoints de API
│   ├── services/               # Lógica de negocio
│   ├── managers/               # Tareas en segundo plano
│   ├── storage/                # Persistencia de datos
│   ├── core/                   # Configuración y constantes
│   ├── schemas.py              # Modelos Pydantic
│   ├── repositories.py         # Capa de acceso a datos
│   └── validators.py           # Validación de entrada
├── main.py                     # Punto de entrada
├── pyproject.toml              # Dependencias (uv)
├── .env.example                # Plantilla de configuración
└── README.md
```

---

## 🐳 Despliegue con Docker

### Inicio Rápido

```bash
# Construir y ejecutar
docker-compose up -d

# Ver logs
docker-compose logs -f

# Detener contenedor
docker-compose down
```

La API estará disponible en `http://localhost:8000`

### Usar Docker sin Compose

```bash
# Construir imagen
docker build -t snapload-api:latest .

# Ejecutar contenedor
docker run -d \
  --name snapload-api \
  -p 8000:8000 \
  -v $(pwd)/downloads:/app/downloads \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/meta:/app/meta \
  -v $(pwd)/tmp:/app/tmp \
  -e RETENTION_HOURS=3 \
  -e CLEANUP_CRON="0 * * * *" \
  -e ENABLE_ADMIN_ENDPOINTS=false \
  snapload-api:latest
```

### Configuración de Docker

El `docker-compose.yml` proporciona una configuración lista para producción:

```yaml
services:
  snapload-api:
    container_name: snapload-api
    build: .
    image: snapload-api:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - PORT=8000
      - WORKERS=1
      - RETENTION_HOURS=3
      - CLEANUP_CRON=0 * * * *
      - ENABLE_ADMIN_ENDPOINTS=false
    volumes:
      - ./downloads:/app/downloads
      - ./logs:/app/logs
      - ./meta:/app/meta
      - ./tmp:/app/tmp
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Variables de Entorno para Docker

Crea un archivo `.env` o configura las variables en `docker-compose.yml`:

```bash
# Configuración del Servidor
PORT=8000
WORKERS=1

# Configuración de Limpieza (Valores por Defecto para Producción)
RETENTION_HOURS=3              # Mantener archivos por 3 horas
CLEANUP_CRON="0 * * * *"       # Limpiar cada hora
ENABLE_ADMIN_ENDPOINTS=false   # Deshabilitar endpoints admin en producción

# Logging
CLEANUP_LOG_LEVEL=INFO
```

### Construcción para Producción

```bash
# Construir imagen
docker build -t snapload-api:latest .

# Ejecutar contenedor
docker run -d \
  --name snapload-api \
  -p 8000:8000 \
  -v $(pwd)/downloads:/app/downloads \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/meta:/app/meta \
  -v $(pwd)/tmp:/app/tmp \
  -e RETENTION_HOURS=3 \
  -e CLEANUP_CRON="0 * * * *" \
  snapload-api:latest
```

### Dockerfile Multi-Etapa

El `Dockerfile` utiliza Python 3.12-slim con caché optimizado:

- **Etapa 1**: Instalar dependencias del sistema (ffmpeg, curl)
- **Etapa 2**: Instalar paquetes Python con `uv` para velocidad
- **Etapa 3**: Copiar código de la aplicación y configurar permisos
- **Health Check**: Monitoreo del endpoint `/health`

Características clave:
- Usuario sin privilegios de root (`appuser`)
- Volúmenes persistentes para downloads/logs/meta/tmp
- Health check con curl
- Caché de capas optimizado para builds más rápidos

---

## 🔧 Solución de Problemas

### Problemas Comunes

**1. Error "Binary not found"**
```bash
# Verificar que los binarios estén instalados
which yt-dlp spotdl ffmpeg

# Instalar binarios faltantes
pip install yt-dlp spotdl
brew install ffmpeg  # o apt-get install ffmpeg
```

**2. Advertencias "Jobs are being missed" (scheduler)**
```
Solución: Este es un comportamiento normal. El scheduler combina ejecuciones perdidas.
La limpieza aún se ejecutará, solo ligeramente retrasada.
```

**3. Descargas fallan con "403 Forbidden"**
```bash
# Actualizar yt-dlp a la última versión
pip install --upgrade yt-dlp
```

**4. La limpieza no funciona**
```bash
# Verificar que la configuración esté cargada
curl http://localhost:8000/admin/cleanup/config

# Verificar CLEANUP_SCHEDULE_ENABLED=true en .env
# Reiniciar el servidor después de cambiar .env
```

---

## ⚖️ Aviso Legal

**IMPORTANTE**: Este software se proporciona solo para uso educativo y personal.

- ✅ **Permitido**: Descargar contenido que posees o tienes permiso para descargar
- ✅ **Permitido**: Archivar contenido para uso personal, no comercial
- ❌ **Prohibido**: Descargar contenido con derechos de autor sin autorización
- ❌ **Prohibido**: Uso comercial o redistribución de contenido descargado
- ❌ **Prohibido**: Violar los Términos de Servicio de las plataformas

**Los usuarios son los únicos responsables** de asegurar que su uso cumple con:
- Leyes de derechos de autor en su jurisdicción
- Términos de Servicio de las plataformas (YouTube, Spotify, etc.)
- Regulaciones locales sobre descargas de medios

Los desarrolladores no asumen **ninguna responsabilidad** por el mal uso de este software.

---

## 📄 Licencia

Este proyecto está licenciado bajo la **Licencia MIT** - ver el archivo [LICENSE](../LICENSE) para más detalles.

---

## 🔗 Proyectos Relacionados

- **[SnapLoad UI](https://github.com/pabrax/SnapLoad/tree/main/snapLoad-UI)** - Cliente web oficial (Next.js)
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - Descargador de YouTube
- **[spotdl](https://github.com/spotDL/spotify-downloader)** - Descargador de Spotify

---

## 📞 Soporte

- 🐛 [Reportar Problemas](https://github.com/pabrax/SnapLoad/issues)
- 💬 [Discusiones](https://github.com/pabrax/SnapLoad/discussions)

---

<div align="center">

Hecho con ❤️ por [pabrax](https://github.com/pabrax)

⭐ Dale una estrella si te resulta útil!

</div>
