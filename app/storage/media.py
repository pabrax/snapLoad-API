"""
Catálogo de media (compatibilidad hacia atrás).
Este módulo re-exporta desde repositories para mantener compatibilidad.
Para nuevo código, importar directamente desde repositories.
"""
from pathlib import Path
from typing import Optional
from ..repositories import media_repo


def ensure_schema():
    """Asegura que el esquema existe."""
    media_repo.ensure_schema()


def compute_sha256(path: Path) -> str:
    """Calcula el hash SHA256 de un archivo."""
    return media_repo.compute_hash(path)


def upsert_media(
    path: Path,
    created_at: str,
    quality: Optional[str],
    format: Optional[str],
    display_name: Optional[str]
) -> str:
    """Inserta o actualiza un archivo de media."""
    return media_repo.upsert_media(path, created_at, quality, format, display_name)


def map_url_to_hash(url: str, file_hash: str, added_at: str):
    """Mapea una URL a un hash de archivo."""
    media_repo.map_url_to_hash(url, file_hash, added_at)


def get_by_url(url: str):
    """Obtiene información de media por URL."""
    result = media_repo.get_by_url(url)
    if result:
        return result.dict()
    return None

