FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/downloads /app/logs /app/meta /app/tmp \
    && chown -R appuser:appuser /app

WORKDIR /app

COPY --chown=appuser:appuser pyproject.toml /app/

RUN uv pip install --system --no-cache \
    fastapi==0.115.12 \
    uvicorn[standard]==0.34.0 \
    python-multipart==0.0.20 \
    pydantic==2.10.6 \
    pydantic-settings==2.7.1 \
    python-dotenv==1.0.1 \
    aiofiles==24.1.0 \
    apscheduler==3.11.1 \
    yt-dlp \
    spotdl

COPY --chown=appuser:appuser . /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
