<div align="center">

# 🚀 SnapLoad API

**REST API for downloading media from YouTube and Spotify**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.103+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-red?style=flat&logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
[![spotdl](https://img.shields.io/badge/spotdl-4.4+-1DB954?style=flat&logo=spotify&logoColor=white)](https://github.com/spotDL/spotify-downloader)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat)](../LICENSE)

*A high-performance asynchronous API for media downloads with job queuing, progress tracking, and comprehensive metadata management.*

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [API Reference](#-api-reference)
- [Job Lifecycle](#-job-lifecycle)
- [File Structure](#-file-structure)
- [Error Handling](#-error-handling)
- [Development](#-development)
- [Deployment](#-deployment)
- [Security Considerations](#-security-considerations)
- [Troubleshooting](#-troubleshooting)
- [Legal Disclaimer](#%EF%B8%8F-legal-disclaimer)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌟 Overview

**SnapLoad API** is a REST API built with FastAPI that provides asynchronous media downloading capabilities from YouTube (via `yt-dlp`) and Spotify (via `spotdl`). The API features a robust job management system with real-time status tracking, comprehensive error handling, and detailed metadata generation.

### Key Characteristics

- **Asynchronous Processing**: Downloads run as background tasks, providing immediate response
- **Job Management**: Full lifecycle tracking with unique job IDs
- **Multi-Platform Support**: YouTube, Spotify, and 1000+ sites supported by yt-dlp
- **Progress Tracking**: Real-time status updates and detailed logs
- **Metadata Generation**: Complete job information with timestamps and file details
- **Docker Ready**: Containerized deployment with Docker Compose
- **Cancellation Support**: Cancel running downloads via API

---

## ✨ Features

### Core Capabilities

- ✅ **Multi-Source Downloads**: YouTube, Spotify, and yt-dlp supported platforms
- ✅ **Audio & Video Formats**: MP3, M4A, MP4, and more
- ✅ **Playlist Support**: Download entire Spotify playlists or YouTube playlists
- ✅ **Quality Selection**: Choose audio/video quality preferences
- ✅ **Job Queuing**: Background task processing with FastAPI
- ✅ **Real-Time Status**: Check job status (`queued`, `running`, `success`, `failed`)
- ✅ **Comprehensive Logging**: Full download logs and error traces
- ✅ **Metadata Storage**: JSON metadata for every job
- ✅ **Download Cancellation**: Stop running jobs via API
- ✅ **Health Checks**: API health and readiness endpoints

### Technical Features

- **FastAPI Framework**: Modern async Python web framework
- **Background Tasks**: Non-blocking download processing
- **File Management**: Organized downloads, logs, and temporary files
- **Error Recovery**: Graceful error handling with detailed error messages
- **Process Management**: Job registry for tracking running processes
- **CORS Support**: Configurable CORS for frontend integration

---

## 🏗️ Architecture

### System Components

```
┌─────────────────┐
│   Client/UI     │
└────────┬────────┘
         │ HTTP Requests
         ▼
┌─────────────────┐
│   FastAPI App   │
│  (api.py)       │
└────────┬────────┘
         │
    ┌────┴────┬────────────┬──────────┐
    ▼         ▼            ▼          ▼
┌────────┐ ┌──────┐  ┌─────────┐ ┌────────┐
│Routes  │ │Models│  │Job Reg. │ │Utils   │
└───┬────┘ └──────┘  └────┬────┘ └────────┘
    │                      │
    └──────────┬───────────┘
               ▼
       ┌───────────────┐
       │ Controllers   │
       │ (sd/yt)       │
       └───────┬───────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│ spotdl │ │yt-dlp  │ │ffmpeg  │
└────────┘ └────────┘ └────────┘
```

### Request Flow

1. **Client Request**: POST to `/download` with URL and type
2. **Validation**: URL validation and job ID generation
3. **Job Creation**: Background task created, metadata initialized
4. **Processing**: spotdl/yt-dlp executes download
5. **Status Updates**: Metadata updated throughout process
6. **File Management**: Downloaded files moved to destination
7. **Completion**: Final status and metadata saved

---

## 📦 Requirements

### System Dependencies

- **Python**: 3.12 or higher
- **ffmpeg**: Required for audio/video processing
- **git**: For some installation processes

### Python Dependencies

All dependencies are managed via `pyproject.toml`:

```toml
fastapi >= 0.103.2
uvicorn >= 0.23.2
yt-dlp >= 2025.11.12
spotdl >= 4.4.3
```

### Installing System Dependencies

**Debian/Ubuntu:**
```bash
sudo apt update && sudo apt install -y ffmpeg git build-essential
```

**macOS (Homebrew):**
```bash
brew install ffmpeg git
```

**Windows:**
- Download ffmpeg from [ffmpeg.org](https://ffmpeg.org/download.html)
- Add to PATH

---

## 🚀 Installation

### Option 1: Local Development

1. **Clone Repository**
   ```bash
   cd CCAPI  # Backend directory
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # .venv\Scripts\activate  # Windows
   ```

3. **Install Dependencies**
   ```bash
   pip install --upgrade pip
   pip install -e .
   ```

4. **Run Development Server**
   ```bash
   python main.py
   # or
   uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
   ```

The API will be available at `http://localhost:8000`

### Option 2: Docker

1. **Build Image**
   ```bash
   docker build -t snapload-api .
   ```

2. **Run Container**
   ```bash
   docker run -d -p 8000:8000 \
     -v $(pwd)/downloads:/app/downloads \
     -v $(pwd)/logs:/app/logs \
     -v $(pwd)/meta:/app/meta \
     snapload-api
   ```

### Option 3: Docker Compose

```bash
docker-compose up -d
```

**Note**: The `docker-compose.yml` file is preconfigured with volume mounts and environment variables.

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Server Configuration
HOST=0.0.0.0
PORT=8000
WORKERS=1

# Paths (relative to project root)
DOWNLOADS_DIR=./downloads
LOGS_DIR=./logs
META_DIR=./meta
TMP_DIR=./tmp

# CORS Configuration
CORS_ORIGINS=http://localhost:3000,http://localhost:9023

# Download Settings
MAX_CONCURRENT_JOBS=5
CLEANUP_ON_SHUTDOWN=true
```

### Directory Structure

The API automatically creates these directories:

```
CCAPI/
├── downloads/          # Final downloaded files
│   ├── audio/         # Audio files (mp3, m4a)
│   └── video/         # Video files (mp4)
├── logs/              # Download logs
│   ├── spotify/       # Spotify download logs
│   └── yt/           # YouTube download logs
├── meta/              # Job metadata (JSON)
└── tmp/               # Temporary files during download
    ├── archives/
    ├── spotify/
    └── yt/
```

---

## 📡 API Reference

### Base URL

```
http://localhost:8000
```

### Endpoints

#### 1. Health Check

**GET** `/health`

Check API health status.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-11-28T12:00:00Z"
}
```

---

#### 2. Download Media

**POST** `/download`

Enqueue a new download job.

**Request Body:**
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "type": "audio"  // "audio" | "video" | null
}
```

**Supported URLs:**
- YouTube: `youtube.com`, `youtu.be`, `music.youtube.com`
- Spotify: `open.spotify.com`, `spotify:track:...`
- 1000+ other sites supported by yt-dlp

**Response:**
```json
{
  "message": "Descarga encolada",
  "job_id": "a1b2c3d4",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

**Status Codes:**
- `202 Accepted`: Job enqueued successfully
- `400 Bad Request`: Invalid URL or parameters
- `500 Internal Server Error`: Server error

**Example with curl:**
```bash
curl -X POST http://localhost:8000/download \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","type":"audio"}'
```

---

#### 3. Get Job Status

**GET** `/status/{job_id}`

Get lightweight status of a job.

**Response:**
```json
{
  "job_id": "a1b2c3d4",
  "status": "running"  // "queued" | "running" | "success" | "failed"
}
```

**Alternative Endpoint:** `GET /download/{job_id}/status`

**Status Codes:**
- `200 OK`: Status retrieved
- `404 Not Found`: Job ID not found

---

#### 4. Get Job Metadata

**GET** `/meta/{job_id}`

Get complete metadata for a job.

**Response:**
```json
{
  "job_id": "a1b2c3d4",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "type": "audio",
  "status": "success",
  "created_at": "2025-11-28T12:00:00Z",
  "started_at": "2025-11-28T12:00:05Z",
  "completed_at": "2025-11-28T12:01:30Z",
  "files": [
    {
      "path": "downloads/audio/Rick Astley - Never Gonna Give You Up.mp3",
      "size": 3245678,
      "format": "mp3"
    }
  ],
  "log_path": "logs/yt/a1b2c3d4/job-a1b2c3d4.log",
  "error": null,
  "output_truncated": "Download progress: 100%..."
}
```

**Status Codes:**
- `200 OK`: Metadata retrieved
- `404 Not Found`: Job ID not found

---

#### 5. Cancel Job

**POST** `/cancel/{job_id}`

Cancel a running download job.

**Response:**
```json
{
  "message": "Job a1b2c3d4 cancelled successfully",
  "job_id": "a1b2c3d4",
  "status": "cancelled"
}
```

**Status Codes:**
- `200 OK`: Job cancelled successfully
- `404 Not Found`: Job ID not found
- `400 Bad Request`: Job already completed or not running

---

#### 6. List Files

**GET** `/files`

List all downloaded files (future endpoint).

---

### Error Responses

All errors follow this structure:

```json
{
  "detail": "Error description",
  "job_id": "a1b2c3d4",  // if applicable
  "timestamp": "2025-11-28T12:00:00Z"
}
```

---

## 🔄 Job Lifecycle

### Status Progression

```
┌─────────┐
│ queued  │  Job created, waiting for processing
└────┬────┘
     │
     ▼
┌─────────┐
│ running │  Download in progress
└────┬────┘
     │
     ├─────────┐
     ▼         ▼
┌─────────┐ ┌────────┐
│ success │ │ failed │
└─────────┘ └────────┘
     │         │
     ▼         ▼
   (Cancelled status via /cancel)
```

### Status Determination Logic

The API determines job status by checking:

1. **Metadata file exists** (`meta/meta-{job_id}.json`)
   - Contains `status` field
2. **Log file exists** (`logs/{platform}/{job_id}/job-{job_id}.log`)
3. **Files downloaded** (presence in `downloads/` directory)

**Status Priority:**
- `failed`: Error in metadata or log indicates failure
- `success`: Files exist in downloads directory
- `running`: Log file exists but no files yet
- `queued`: Metadata exists but no log file

---

## 📂 File Structure

### Generated Files

#### Metadata File (`meta/meta-{job_id}.json`)

```json
{
  "job_id": "a1b2c3d4",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "type": "audio",
  "status": "success",
  "created_at": "2025-11-28T12:00:00.000Z",
  "started_at": "2025-11-28T12:00:05.123Z",
  "completed_at": "2025-11-28T12:01:30.456Z",
  "files": [
    {
      "path": "downloads/audio/Rick Astley - Never Gonna Give You Up.mp3",
      "size": 3245678,
      "format": "mp3",
      "title": "Rick Astley - Never Gonna Give You Up",
      "artist": "Rick Astley",
      "duration": 213
    }
  ],
  "log_path": "logs/yt/a1b2c3d4/job-a1b2c3d4.log",
  "error": null,
  "output_truncated": "First and last 500 chars of download output..."
}
```

#### Log File (`logs/{platform}/{job_id}/job-{job_id}.log`)

Contains complete stdout/stderr from yt-dlp or spotdl:

```
[youtube] dQw4w9WgXcQ: Downloading webpage
[youtube] dQw4w9WgXcQ: Downloading android player API JSON
[info] dQw4w9WgXcQ: Downloading 1 format(s): 251
[download] Destination: Rick Astley - Never Gonna Give You Up.webm
[download] 100% of 3.09MiB in 00:02
[ExtractAudio] Destination: Rick Astley - Never Gonna Give You Up.mp3
Deleting original file Rick Astley - Never Gonna Give You Up.webm
```

---

## ⚠️ Error Handling

### Common Error Scenarios

#### 1. Invalid URL

**Request:**
```json
{
  "url": "https://invalid-site.com/video",
  "type": "audio"
}
```

**Response:**
```json
{
  "detail": "URL not supported. Only YouTube and Spotify URLs are allowed."
}
```

#### 2. Download Failure

**Metadata:**
```json
{
  "status": "failed",
  "error": "ERROR: Video unavailable",
  "output_truncated": "..."
}
```

#### 3. Job Not Found

**Response:**
```json
{
  "detail": "Job ID not found: invalid-id"
}
```

### Error Recovery

- **Retry Logic**: Frontend should implement exponential backoff
- **Log Analysis**: Check log files for detailed error information
- **Metadata Review**: Error details stored in metadata file

---

## 🛠️ Development

### Project Structure

```
CCAPI/
├── app/
│   ├── api.py              # FastAPI application
│   ├── models.py           # Pydantic models
│   ├── utils.py            # Utility functions
│   ├── job_registry.py     # Job tracking
│   ├── controllers/
│   │   ├── sd_controller.py  # Spotify downloads
│   │   └── yt_controller.py  # YouTube downloads
│   └── routes/
│       ├── download.py     # Download endpoints
│       ├── files.py        # File management
│       └── health.py       # Health checks
├── main.py                 # Application entry point
├── pyproject.toml          # Project dependencies
├── Dockerfile              # Container image
└── docker-compose.yml      # Docker orchestration
```

### Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

### Code Style

```bash
# Install formatting tools
pip install black isort flake8

# Format code
black app/
isort app/

# Lint
flake8 app/
```

### Hot Reload

Development server with auto-reload:

```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

---

## 🚢 Deployment

### Production Recommendations

#### 1. Use Gunicorn + Uvicorn

```bash
pip install gunicorn
gunicorn app.api:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

#### 2. Environment Variables

```bash
# Production settings
export ENV=production
export WORKERS=4
export LOG_LEVEL=warning
```

#### 3. Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name api.snapload.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### 4. SSL/TLS

```bash
# Using Certbot
sudo certbot --nginx -d api.snapload.example.com
```

#### 5. Docker Production

```bash
docker build -t snapload-api:latest .
docker run -d \
  --name snapload-api \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /data/downloads:/app/downloads \
  -v /data/logs:/app/logs \
  -v /data/meta:/app/meta \
  snapload-api:latest
```

### Performance Tuning

- **Workers**: Set to `2 * CPU_CORES + 1`
- **Concurrency**: Limit concurrent downloads based on system resources
- **Disk Cleanup**: Implement periodic cleanup of old files
- **Log Rotation**: Use logrotate for log management

---

## 🔒 Security Considerations

### ⚠️ Important Security Notes

**This API is designed for LOCAL USE ONLY and does not include authentication by default.**

If you need to expose this API beyond your local network:

1. **Add Authentication**
   - Implement API keys or JWT tokens
   - Use FastAPI dependencies for auth
   ```python
   from fastapi import Depends, HTTPException, Security
   from fastapi.security import APIKeyHeader
   
   api_key_header = APIKeyHeader(name="X-API-Key")
   
   async def verify_api_key(api_key: str = Security(api_key_header)):
       if api_key != os.getenv("API_KEY"):
           raise HTTPException(status_code=403, detail="Invalid API Key")
   ```

2. **Use HTTPS**
   - Never expose over plain HTTP
   - Use reverse proxy (Nginx) with TLS
   - Obtain SSL certificate (Let's Encrypt)

3. **Rate Limiting**
   ```python
   from slowapi import Limiter, _rate_limit_exceeded_handler
   from slowapi.util import get_remote_address
   
   limiter = Limiter(key_func=get_remote_address)
   app.state.limiter = limiter
   
   @app.post("/download")
   @limiter.limit("10/minute")
   async def download_endpoint(request: Request, ...):
       ...
   ```

4. **Input Validation**
   - URL whitelist/blacklist
   - File size limits
   - Timeout limits

5. **CORS Configuration**
   ```python
   from fastapi.middleware.cors import CORSMiddleware
   
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://your-frontend.com"],
       allow_credentials=True,
       allow_methods=["GET", "POST"],
       allow_headers=["*"],
   )
   ```

6. **Resource Limits**
   - Implement max concurrent jobs
   - Disk space monitoring
   - Memory usage limits

---

## 🐛 Troubleshooting

### Common Issues

#### 1. ffmpeg not found

**Error:**
```
ERROR: ffmpeg not found. Please install ffmpeg
```

**Solution:**
```bash
# Linux
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Verify installation
ffmpeg -version
```

#### 2. Permission Denied

**Error:**
```
PermissionError: [Errno 13] Permission denied: 'downloads/'
```

**Solution:**
```bash
# Check directory permissions
ls -la downloads/

# Fix permissions
chmod -R 755 downloads/ logs/ meta/ tmp/
```

#### 3. Download Stuck in "running"

**Possible Causes:**
- Process crashed without updating metadata
- Network timeout
- Disk full

**Solution:**
```bash
# Check logs
cat logs/{platform}/{job_id}/job-{job_id}.log

# Check disk space
df -h

# Cancel job via API
curl -X POST http://localhost:8000/cancel/{job_id}
```

#### 4. Port Already in Use

**Error:**
```
OSError: [Errno 48] Address already in use
```

**Solution:**
```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>

# Or use different port
uvicorn app.api:app --port 8001
```

#### 5. Docker Container Exits Immediately

**Solution:**
```bash
# Check logs
docker logs <container_id>

# Run with debug
docker run -it snapload-api bash
python main.py
```

### Debug Mode

Enable debug logging:

```python
# In main.py or api.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Health Diagnostics

```bash
# Check API health
curl http://localhost:8000/health

# Check if services are running
ps aux | grep uvicorn

# Check disk usage
du -sh downloads/ logs/ meta/ tmp/
```

---

## ⚖️ Legal Disclaimer

**IMPORTANT LEGAL NOTICE**

This software is provided for **educational and personal use only**. Users are **solely responsible** for ensuring their use complies with applicable laws and the terms of service of content platforms.

### User Responsibilities

- ✅ **You must have the legal right** to download content
- ✅ **Respect copyright laws** in your jurisdiction
- ✅ **Follow platform Terms of Service** (YouTube, Spotify, etc.)
- ✅ **Use for personal, non-commercial purposes only**

### Prohibited Uses

- ❌ Downloading copyrighted content without permission
- ❌ Commercial redistribution of downloaded content
- ❌ Bypassing technological protection measures
- ❌ Violating platform Terms of Service
- ❌ Any illegal activity

### No Warranty

This software is provided "AS IS" without warranty of any kind. The authors are not responsible for misuse, legal consequences, or damages resulting from use of this software.

By using SnapLoad API, you acknowledge and accept full responsibility for your actions and agree to use this tool in compliance with all applicable laws and regulations.

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

### Reporting Issues

1. Check existing issues first
2. Provide detailed description
3. Include system information (OS, Python version)
4. Attach relevant logs or error messages

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Guidelines

- Follow PEP 8 style guide
- Add type hints
- Include docstrings
- Write tests for new features
- Update documentation

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](../LICENSE) file for details.

### MIT License Summary

- ✅ Commercial use allowed
- ✅ Modification allowed
- ✅ Distribution allowed
- ✅ Private use allowed
- ⚠️ License and copyright notice required
- ⚠️ No liability or warranty

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/pabrax/LocalSongs/issues)
- **Documentation**: This README
- **Logs**: Check `logs/` directory for detailed error information

---

## 🙏 Acknowledgments

This project is built on top of excellent open-source tools:

- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube downloader
- [spotdl](https://github.com/spotDL/spotify-downloader) - Spotify downloader
- [ffmpeg](https://ffmpeg.org/) - Media processing
- [uvicorn](https://www.uvicorn.org/) - ASGI server

---

<div align="center">

**Made with ❤️ for the SnapLoad Project**

[⬆ Back to Top](#-snapload-api)

</div>

