<div align="center">

# 🚀 SnapLoad API

**REST API for downloading media from YouTube and Spotify**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.103+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-red?style=flat&logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
[![spotdl](https://img.shields.io/badge/spotdl-4.4+-1DB954?style=flat&logo=spotify&logoColor=white)](https://github.com/spotDL/spotify-downloader)

*High-performance asynchronous API for media downloads with job queuing, progress tracking, and automatic storage management.*

[Official Web Client](https://github.com/pabrax/SnapLoad) | [API Documentation](#-api-reference) | [Report Issues](https://github.com/pabrax/SnapLoad/issues)

**🇬🇧 English** | [🇪🇸 Español](docs/README.es.md)

</div>

---

## 🚀 Quick Start (Full Stack)

**Want to run the complete application (Backend + Frontend)?** Use the monorepo:

```bash
curl -fsSL https://raw.githubusercontent.com/pabrax/SnapLoad/main/install.sh | bash
```

This will install and run both the API and the web interface together. **[See full documentation](https://github.com/pabrax/SnapLoad)**

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [API Reference](#-api-reference)
- [Storage Management](#-storage-management)
- [Development](#-development)
- [Docker Deployment](#-docker-deployment)
- [Troubleshooting](#-troubleshooting)
- [Legal Disclaimer](#%EF%B8%8F-legal-disclaimer)
- [License](#-license)

---

## 🌟 Overview

**SnapLoad API** is a production-ready REST API built with FastAPI that provides asynchronous media downloading from YouTube, Spotify, and 1000+ sites. Designed for resource-constrained servers with automatic cleanup, job management, and comprehensive error handling.

### Key Features

- ⚡ **Async Processing**: Background job execution with immediate API response
- 🎯 **Smart Job Management**: Unique job IDs with full lifecycle tracking
- 🌐 **Multi-Platform**: YouTube, Spotify, SoundCloud, and more via yt-dlp
- 📊 **Progress Tracking**: Real-time status updates and detailed metadata
- 🧹 **Auto Cleanup**: Configurable retention policies to manage storage
- 🔒 **Production Ready**: Health checks, error handling, and comprehensive logging
- 📦 **File Management**: Download individual files or complete archives (playlists/albums)

### Supported Platforms

- **YouTube**: Videos, playlists, channels (audio/video)
- **Spotify**: Tracks, albums, playlists (downloads via YouTube search)
- **1000+ sites**: Anything supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- ffmpeg
- Internet connection

### Installation

```bash
# Clone repository
git clone https://github.com/pabrax/SnapLoad.git
cd SnapLoad/snapLoad-API

# Install uv (recommended package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your preferred settings

# Run server
uv run python main.py
```

Server will be available at `http://localhost:8000`

### Quick Test

```bash
# Download a YouTube video
curl -X POST http://localhost:8000/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "quality": "192"}'

# Response: {"job_id": "abc123", "status": "queued", "message": "Download queued"}

# Check status
curl http://localhost:8000/status/abc123

# Download file when ready
curl http://localhost:8000/files/abc123/download/filename.mp3 -O
```

---

## 📦 Installation

### Using uv (Recommended)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone https://github.com/pabrax/SnapLoad.git
cd SnapLoad/snapLoad-API
uv sync
```

### Using pip

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### System Dependencies

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
- Install [Python 3.12+](https://www.python.org/downloads/)
- Install [ffmpeg](https://www.gyan.dev/ffmpeg/builds/)
- Add ffmpeg to PATH

---

## ⚙️ Configuration

Configuration is managed via environment variables in `.env` file:

```bash
# Cleanup Configuration (Important for VPS/Limited Storage)
RETENTION_HOURS=3                    # Keep files for 3 hours
TEMP_RETENTION_HOURS=0.5             # Clean temp files after 30 minutes
CLEANUP_SCHEDULE_ENABLED=true        # Enable automatic cleanup
CLEANUP_CRON="0 * * * *"             # Clean every hour
TEMP_CLEANUP_CRON="0 */2 * * *"      # Clean temp every 2 hours

# Admin Endpoints (Disable in production)
ENABLE_ADMIN_ENDPOINTS=false         # Set to true only for testing/development

# Logging
CLEANUP_LOG_LEVEL=INFO               # DEBUG, INFO, WARNING, ERROR
CLEANUP_LOG_RETENTION_DAYS=7         # Keep cleanup logs for 7 days

# Testing Mode
CLEANUP_DRY_RUN=false                # Set to true to simulate without deleting
```

### Configuration Presets

**Development (Fast Cleanup for Testing):**
```bash
RETENTION_HOURS=0.08              # 5 minutes
CLEANUP_CRON="*/5 * * * *"        # Every 5 minutes
ENABLE_ADMIN_ENDPOINTS=true
CLEANUP_DRY_RUN=true              # Simulate only
```

**Production (Recommended for VPS):**
```bash
RETENTION_HOURS=3                 # 3 hours
CLEANUP_CRON="0 * * * *"          # Every hour
ENABLE_ADMIN_ENDPOINTS=false
```

**Production (More Storage Available):**
```bash
RETENTION_HOURS=24                # 24 hours
CLEANUP_CRON="0 */6 * * *"        # Every 6 hours
ENABLE_ADMIN_ENDPOINTS=false
```

---

## 🔌 API Reference

### Base URL
```
http://localhost:8000
```

### Endpoints

#### 🏥 Health Check
```http
GET /health
```

**Response:**
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

#### 📥 Download Media
```http
POST /download
Content-Type: application/json
```

**Request Body:**
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "quality": "192",  // kbps or "best" (audio)
  "format": "mp3"    // mp3, m4a, opus, ogg, flac, wav (audio)
}
```

**Response:**
```json
{
  "job_id": "abc123",
  "status": "queued",
  "message": "Download queued successfully"
}
```

**Audio options** (`POST /download`):
- `quality`: bitrate in kbps (`32`, `40`, `48`, `64`, `80`, `96`, `112`, `128`, `160`, `192`, `224`, `256`, `320`) or `best`. Anything else returns `400`.
- `format`: `mp3` (default), `m4a`, `opus`, `ogg`, `flac`, `wav`. (`aac` is not offered: yt-dlp delivers it inside an `.m4a` identical to `m4a`.)
- The response echoes the canonical `quality`/`format`, and files are stored in `downloads/audio/<format>/<quality>/`.

| Format | Behavior | Bitrate |
|--------|----------|---------|
| `mp3`, `ogg` | Re-encoded | applied (`best` = highest VBR) |
| `m4a` | `best` copies the original AAC stream; an explicit bitrate re-encodes | applied |
| `opus` | Copies YouTube's original Opus stream (no re-encoding) | not applicable (`quality` = `source`) |
| `flac`, `wav` | Lossless container around a lossy source: bigger file, no fidelity gain | not applicable (`quality` = `lossless`) |

> YouTube audio tops out around 128-130 kbps, so bitrates above that only re-encode (verified with `ffprobe`).

**Video options** (`POST /download/video`):
- `format`: `webm` (default, VP9 + Opus), `mp4` (H.264 + AAC), `mkv` (best quality, any codec), `mov` and `avi` (H.264 + AAC).
- `resolution`: `best` (default), `2160p`, `1440p`, `1080p`, `720p`, `480p`, `360p`. If the video does not have that height, the highest one below it is used.
- `mp4` prefers H.264 (up to 1080p) for compatibility; VP9/AV1 inside mp4 are only used when `1440p`/`2160p` is requested.
- `mov` and `avi` are produced by remuxing (stream copy, no re-encoding, fast) and are limited to `1080p`; higher values return `400`.
- Files are stored in `downloads/video/<format>/<resolution>/`.

---

#### 📊 Check Job Status
```http
GET /status/{job_id}
```

**Response:**
```json
{
  "job_id": "abc123",
  "status": "success",  // queued, running, success, failed, cancelled
  "message": "Download completed",
  "meta": {
    "title": "Video Title",
    "artist": "Artist Name",
    "duration": "3:45",
    "progress": 100
  }
}
```

**Status Values:**
- `queued`: Job waiting to start
- `running`: Download in progress
- `success`: Completed successfully
- `failed`: Error occurred
- `cancelled`: User cancelled

---

#### 📂 List Files
```http
GET /files/{job_id}
```

**Response:**
```json
{
  "job_id": "abc123",
  "files": [
    {
      "name": "Artist - Song.mp3",
      "size_bytes": 4567890,
      "size_mb": 4.36
    }
  ]
}
```

---

#### 💾 Download File
```http
GET /files/{job_id}/download/{filename}
```

Downloads the specified file.

---

#### 📦 Download Archive (Playlists/Albums)
```http
GET /files/{job_id}/archive
```

Downloads all files as a ZIP archive (for playlists/albums with multiple tracks).

---

#### ❌ Cancel Job
```http
POST /cancel/{job_id}
```

**Response:**
```json
{
  "job_id": "abc123",
  "status": "cancelled",
  "message": "Job cancelled successfully"
}
```

---

### Admin Endpoints (Development Only)

Enable with `ENABLE_ADMIN_ENDPOINTS=true` in `.env`:

#### 🧹 Trigger Cleanup
```http
POST /admin/cleanup/trigger
Content-Type: application/json
```

**Request:**
```json
{
  "targets": ["all"],  // "downloads", "logs", "metadata", "temp", "database", "all"
  "strategy": "age_based",
  "dry_run": false
}
```

---

#### 📊 Storage Stats
```http
GET /admin/storage/stats
```

---

#### ⏰ Cleanup Schedule
```http
GET /admin/cleanup/schedule
```

---

#### ⚙️ Cleanup Config
```http
GET /admin/cleanup/config
```

---

## 🗂️ Storage Management

SnapLoad includes an automatic cleanup system designed for resource-constrained servers.

### How It Works

1. **Age-Based Cleanup**: Files older than `RETENTION_HOURS` are deleted
2. **Scheduled Execution**: Runs automatically based on `CLEANUP_CRON`
3. **Comprehensive**: Cleans downloads, logs, metadata, temp files, and database entries
4. **Safe**: Only removes completed/failed jobs, never active downloads

### Directory Structure

```
snapLoad-API/
├── downloads/          # Downloaded media files
│   ├── audio/         # Audio files organized by quality
│   └── video/         # Video files organized by format
├── logs/              # Download and cleanup logs
│   ├── cleanup/       # Cleanup operation logs
│   ├── spotify/       # Spotify download logs
│   └── yt/            # YouTube download logs
├── meta/              # Job metadata (JSON)
└── tmp/               # Temporary files during processing
    ├── archives/      # Temporary ZIP files
    ├── spotify/       # Spotify temp files
    └── yt/            # YouTube temp files
```

### Manual Cleanup

```bash
# Trigger cleanup via API (with admin endpoints enabled)
curl -X POST http://localhost:8000/admin/cleanup/trigger \
  -H "Content-Type: application/json" \
  -d '{"targets": ["all"], "dry_run": false}'

# Check storage stats
curl http://localhost:8000/admin/storage/stats
```

---

## 🛠️ Development

### Project Structure

```
snapLoad-API/
├── app/
│   ├── api.py                  # FastAPI app and lifespan
│   ├── routes/                 # API endpoints
│   │   ├── download.py         # Download endpoints
│   │   ├── files.py            # File management
│   │   ├── health.py           # Health checks
│   │   └── admin.py            # Admin endpoints (optional)
│   ├── services/               # Business logic
│   │   ├── base_download_service.py
│   │   ├── spotify_service.py
│   │   ├── youtube_service.py
│   │   ├── download_orchestrator.py
│   │   └── cleanup_service.py
│   ├── managers/               # Background tasks
│   │   ├── job_manager.py
│   │   ├── file_manager.py
│   │   └── cleanup_scheduler.py
│   ├── storage/                # Data persistence
│   │   ├── index.py            # SQLite job index
│   │   └── media.py            # File system operations
│   ├── core/                   # Configuration and constants
│   │   ├── config.py
│   │   ├── enums.py
│   │   ├── constants.py
│   │   └── exceptions.py
│   ├── schemas.py              # Pydantic models
│   ├── repositories.py         # Data access layer
│   └── validators.py           # Input validation
├── main.py                     # Entry point
├── pyproject.toml              # Dependencies (uv)
├── .env.example                # Configuration template
└── README.md
```

### Running Tests

```bash
# Manual testing with admin endpoints
cp .env.example .env
# Set ENABLE_ADMIN_ENDPOINTS=true
# Set RETENTION_HOURS=0.08 (5 minutes) for quick testing
# Set CLEANUP_CRON="*/5 * * * *"

uv run python main.py

# In another terminal
./test_env.sh  # Verifies env variables are loaded correctly
```

### Code Style

The project follows:
- **Type hints** for all functions
- **Docstrings** for public APIs
- **Async/await** for I/O operations
- **Repository pattern** for data access
- **Service layer** for business logic

---

## 🐳 Docker Deployment

### Quick Start

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop container
docker-compose down
```

The API will be available at `http://localhost:8000`

### Using Docker without Compose

```bash
# Build image
docker build -t snapload-api:latest .

# Run container
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

### Docker Configuration

The `docker-compose.yml` provides a production-ready setup:

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

### Environment Variables for Docker

Create a `.env` file or set environment variables in `docker-compose.yml`:

```bash
# Server Configuration
PORT=8000
WORKERS=1

# Cleanup Configuration (Production Defaults)
RETENTION_HOURS=3              # Keep files for 3 hours
CLEANUP_CRON="0 * * * *"       # Clean every hour
ENABLE_ADMIN_ENDPOINTS=false   # Disable admin endpoints in production

# Logging
CLEANUP_LOG_LEVEL=INFO
```

### Building for Production

```bash
# Build image
docker build -t snapload-api:latest .

# Run container
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

### Multi-Stage Dockerfile

The `Dockerfile` uses Python 3.12-slim with optimized caching:

- **Stage 1**: Install system dependencies (ffmpeg, curl)
- **Stage 2**: Install Python packages with `uv` for speed
- **Stage 3**: Copy application code and set permissions
- **Health Check**: `/health` endpoint monitoring

Key features:
- Non-root user (`appuser`)
- Persistent volumes for downloads/logs/meta/tmp
- Health check with curl
- Optimized layer caching for faster builds

---

## 🔧 Troubleshooting

### Common Issues

**1. "Binary not found" error**
```bash
# Verify binaries are installed
which yt-dlp spotdl ffmpeg

# Install missing binaries
pip install yt-dlp spotdl
brew install ffmpeg  # or apt-get install ffmpeg
```

**2. "Jobs are being missed" (scheduler warnings)**
```
Solution: This is normal behavior. The scheduler combines missed executions.
The cleanup will still run, just slightly delayed.
```

**3. Downloads fail with "403 Forbidden"**
```bash
# Update yt-dlp to latest version
pip install --upgrade yt-dlp
```

**4. Cleanup not working**
```bash
# Check configuration is loaded
curl http://localhost:8000/admin/cleanup/config

# Verify CLEANUP_SCHEDULE_ENABLED=true in .env
# Restart server after changing .env
```

**5. Files not being cleaned after retention time**
```bash
# Files are cleaned on the next scheduled run, not exactly at retention time
# If RETENTION_HOURS=3 and CLEANUP_CRON="0 * * * *":
#   - File created at 10:30
#   - Becomes old at 13:30  
#   - Will be deleted at 14:00 (next hourly run)
```

### Debug Mode

Enable detailed logging:

```bash
# In .env
CLEANUP_LOG_LEVEL=DEBUG
ENABLE_ADMIN_ENDPOINTS=true
```

Check logs:
```bash
tail -f logs/cleanup/cleanup-*.log
```

---

## ⚖️ Legal Disclaimer

**IMPORTANT**: This software is provided for educational and personal use only.

- ✅ **Permitted**: Downloading content you own or have permission to download
- ✅ **Permitted**: Archiving content for personal, non-commercial use
- ❌ **Prohibited**: Downloading copyrighted content without authorization
- ❌ **Prohibited**: Commercial use or redistribution of downloaded content
- ❌ **Prohibited**: Violating platform Terms of Service

**Users are solely responsible** for ensuring their use complies with:
- Copyright laws in their jurisdiction
- Platform Terms of Service (YouTube, Spotify, etc.)
- Local regulations regarding media downloads

The developers assume **no liability** for misuse of this software.

### Responsible Use Guidelines

1. Only download content you have rights to
2. Respect copyright and intellectual property
3. Do not redistribute downloaded content
4. Use for personal, educational, or archival purposes only
5. Support content creators through official channels

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
git clone https://github.com/pabrax/SnapLoad.git
cd SnapLoad/snapLoad-API
uv sync
cp .env.example .env
# Edit .env for development
uv run python main.py
```

---

## 📄 License

This project is licensed under the **GPL-3.0 License** - see the [LICENSE](LICENSE) file for details.

### Third-Party Licenses

This project uses third-party software that is subject to their own licenses:

- **[spotdl](https://github.com/spotDL/spotify-downloader)** - MIT License (required attribution)
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - Unlicense
- **[FastAPI](https://github.com/tiangolo/fastapi)** - MIT License
- **[ffmpeg](https://ffmpeg.org/)** - LGPL/GPL

**Important:** spotdl is licensed under the MIT License, which requires that the copyright notice and license text be included in all copies or substantial portions of the software. The full text of the MIT License for spotdl and other third-party dependencies can be found in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## 🔗 Related Projects

- **[SnapLoad UI](https://github.com/pabrax/SnapLoad/tree/main/snapLoad-UI)** - Official web client (Next.js)
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - YouTube downloader
- **[spotdl](https://github.com/spotDL/spotify-downloader)** - Spotify downloader

---

## 📞 Support

- 🐛 [Report Issues](https://github.com/pabrax/SnapLoad/issues)
- 💬 [Discussions](https://github.com/pabrax/SnapLoad/discussions)

---

<div align="center">

Made with ❤️ by [pabrax](https://github.com/pabrax)

⭐ Star this repo if you find it useful!

</div>
