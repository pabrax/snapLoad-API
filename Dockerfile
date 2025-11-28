# Dockerfile for SnapLoad API (FastAPI app)
# - Based on Python 3.12 slim
# - Installs system deps (ffmpeg) required by yt-dlp / spotdl
# - Installs Python deps and common CLI tools (yt-dlp, spotdl)
# - Runs uvicorn as the container entrypoint

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (ffmpeg is required for audio/video processing)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       git \
       build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd --create-home --shell /bin/bash appuser || true

WORKDIR /app

# Copy only dependency files first for better caching
COPY pyproject.toml poetry.lock* /app/ 2>/dev/null || true

# Upgrade pip and install build tools
RUN pip install --upgrade pip setuptools wheel

# Ensure some expected common tools are available
# yt-dlp and spotdl are installed via pip so they are available in PATH
RUN pip install --no-cache-dir yt-dlp spotdl uvicorn[standard]

# Install project package (if pyproject defines it). If project uses poetry/poetry.lock,
# pip will use the PEP 517 build system to install the project.
RUN if [ -f pyproject.toml ]; then pip install --no-cache-dir . || true; fi

# Copy application sources
COPY . /app
RUN chown -R appuser:appuser /app
USER appuser

# Expose default port
EXPOSE 8000
ENV PORT=8000
ENV WORKERS=1

# Default command (can be overridden by Coolify start command)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
