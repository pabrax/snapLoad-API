"""
Repositorios de almacenamiento con patrón Repository.
Abstrae la lógica de acceso a datos de SQLite.
"""
import sqlite3
import json
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

from .core.config import settings
from .schemas import DownloadIndexEntry, MediaInfo


class BaseRepository(ABC):
    """Clase base abstracta para repositorios."""
    
    def __init__(self, db_path: Path):
        """
        Inicializa el repositorio.
        
        Args:
            db_path: Ruta a la base de datos SQLite
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()
    
    def _connect(self) -> sqlite3.Connection:
        """
        Crea una conexión a la base de datos.
        
        Returns:
            Conexión SQLite
        """
        return sqlite3.connect(str(self.db_path), check_same_thread=False)
    
    @abstractmethod
    def ensure_schema(self) -> None:
        """Asegura que el esquema de la base de datos existe."""
        pass


class DownloadIndexRepository(BaseRepository):
    """
    Repositorio para el índice de descargas.
    Gestiona el cache de descargas previas.
    """
    
    def ensure_schema(self) -> None:
        """Crea la tabla downloads si no existe."""
        con = self._connect()
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                  url TEXT NOT NULL,
                  type TEXT NOT NULL,
                  quality TEXT,
                  format TEXT,
                  files_json TEXT,
                  status TEXT NOT NULL,
                  job_id TEXT,
                  created_at TEXT NOT NULL,
                  last_access TEXT,
                  error TEXT,
                  PRIMARY KEY (url, type, quality, format)
                )
                """
            )
            con.commit()
        finally:
            con.close()
    
    def lookup(
        self,
        url: str,
        media_type: str,
        quality: Optional[str] = None,
        format_: Optional[str] = None
    ) -> Optional[DownloadIndexEntry]:
        """
        Busca una descarga en el índice.
        
        Args:
            url: URL a buscar
            media_type: Tipo de media
            quality: Calidad opcional
            format_: Formato opcional
            
        Returns:
            DownloadIndexEntry si se encuentra, None si no
        """
        con = self._connect()
        try:
            cur = con.execute(
                """SELECT url, type, quality, format, files_json, status, job_id, 
                          created_at, last_access, error 
                   FROM downloads 
                   WHERE url=? AND type=? 
                     AND IFNULL(quality,'')=IFNULL(?, '') 
                     AND IFNULL(format,'')=IFNULL(?, '')""",
                (url, media_type, quality, format_),
            )
            row = cur.fetchone()
            if not row:
                return None
            
            entry = DownloadIndexEntry(
                url=row[0],
                type=row[1],
                quality=row[2],
                format=row[3],
                files=json.loads(row[4]) if row[4] else [],
                status=row[5],
                job_id=row[6],
                created_at=row[7],
                last_access=row[8],
                error=row[9],
            )
            
            # Verificar que los archivos existen
            if entry.status == "ready":
                missing = [p for p in entry.files if not Path(p).exists()]
                if missing:
                    # Marcar como fallido si faltan archivos
                    self._mark_as_failed(url, media_type, quality, format_, f"missing_files:{missing}")
                    return None
            
            return entry
        finally:
            con.close()
    
    def find_by_job_id(self, job_id: str) -> Optional[DownloadIndexEntry]:
        """
        Busca una descarga por job_id.
        
        Args:
            job_id: ID del job a buscar
            
        Returns:
            DownloadIndexEntry si se encuentra, None si no
        """
        con = self._connect()
        try:
            cur = con.execute(
                """SELECT url, type, quality, format, files_json, status, job_id, 
                          created_at, last_access, error 
                   FROM downloads 
                   WHERE job_id=?""",
                (job_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            
            return DownloadIndexEntry(
                url=row[0],
                type=row[1],
                quality=row[2],
                format=row[3],
                files=json.loads(row[4]) if row[4] else [],
                status=row[5],
                job_id=row[6],
                created_at=row[7],
                last_access=row[8],
                error=row[9],
            )
        finally:
            con.close()
    
    def _mark_as_failed(
        self,
        url: str,
        media_type: str,
        quality: Optional[str],
        format_: Optional[str],
        error: str
    ) -> None:
        """Marca una entrada como fallida (uso interno)."""
        con = self._connect()
        try:
            con.execute(
                """UPDATE downloads SET status='failed', error=? 
                   WHERE url=? AND type=? 
                     AND IFNULL(quality,'')=IFNULL(?, '') 
                     AND IFNULL(format,'')=IFNULL(?, '')""",
                (error, url, media_type, quality, format_),
            )
            con.commit()
        finally:
            con.close()
    
    def register_pending(
        self,
        url: str,
        media_type: str,
        quality: Optional[str],
        format_: Optional[str],
        job_id: str,
        created_at: str
    ) -> None:
        """
        Registra una descarga pendiente.
        
        Args:
            url: URL de la descarga
            media_type: Tipo de media
            quality: Calidad opcional
            format_: Formato opcional
            job_id: ID del job
            created_at: Timestamp de creación
        """
        con = self._connect()
        try:
            con.execute(
                """INSERT INTO downloads(url, type, quality, format, files_json, status, 
                                        job_id, created_at, last_access, error)
                   VALUES (?,?,?,?,?, 'pending', ?, ?, NULL, NULL)
                   ON CONFLICT(url, type, quality, format) DO UPDATE SET
                       job_id=excluded.job_id,
                       status='pending',
                       files_json=excluded.files_json,
                       error=NULL,
                       created_at=excluded.created_at,
                       last_access=NULL
                   WHERE downloads.status != 'pending'""",
                (url, media_type, quality, format_, json.dumps([]), job_id, created_at),
            )
            con.commit()
        finally:
            con.close()
    
    def register_success(self, job_id: str, files: List[str]) -> None:
        """
        Marca un job como exitoso.
        
        Args:
            job_id: ID del job
            files: Lista de archivos resultantes
        """
        con = self._connect()
        try:
            con.execute(
                """UPDATE downloads SET files_json=?, status='ready', error=NULL 
                   WHERE job_id=?""",
                (json.dumps(files), job_id),
            )
            con.commit()
        finally:
            con.close()
    
    def register_failed(self, job_id: str, error: str) -> None:
        """
        Marca un job como fallido.
        
        Args:
            job_id: ID del job
            error: Mensaje de error
        """
        con = self._connect()
        try:
            con.execute(
                "UPDATE downloads SET status='failed', error=? WHERE job_id=?",
                (error, job_id),
            )
            con.commit()
        finally:
            con.close()
    
    def touch(
        self,
        url: str,
        media_type: str,
        quality: Optional[str],
        format_: Optional[str],
        last_access: str
    ) -> None:
        """
        Actualiza el timestamp de último acceso.
        
        Args:
            url: URL
            media_type: Tipo de media
            quality: Calidad opcional
            format_: Formato opcional
            last_access: Timestamp de acceso
        """
        con = self._connect()
        try:
            con.execute(
                """UPDATE downloads SET last_access=? 
                   WHERE url=? AND type=? 
                     AND IFNULL(quality,'')=IFNULL(?, '') 
                     AND IFNULL(format,'')=IFNULL(?, '')""",
                (last_access, url, media_type, quality, format_),
            )
            con.commit()
        finally:
            con.close()
    
    def upsert_ready(
        self,
        url: str,
        media_type: str,
        quality: Optional[str],
        format_: Optional[str],
        files: List[str],
        created_at: str,
        job_id: Optional[str] = None
    ) -> None:
        """
        Inserta o actualiza una entrada como lista (ready).
        
        Args:
            url: URL
            media_type: Tipo de media
            quality: Calidad opcional
            format_: Formato opcional
            files: Lista de archivos
            created_at: Timestamp
            job_id: ID del job opcional
        """
        con = self._connect()
        try:
            con.execute(
                """INSERT INTO downloads(url, type, quality, format, files_json, status, 
                                        job_id, created_at, last_access, error)
                   VALUES (?,?,?,?,?, 'ready', ?, ?, ?, NULL)
                   ON CONFLICT(url, type, quality, format) DO UPDATE SET
                      files_json=excluded.files_json,
                      status='ready',
                      job_id=COALESCE(excluded.job_id, downloads.job_id),
                      created_at=COALESCE(downloads.created_at, excluded.created_at),
                      last_access=excluded.last_access,
                      error=NULL""",
                (url, media_type, quality, format_, json.dumps(files), job_id, created_at, created_at),
            )
            con.commit()
        finally:
            con.close()
    
    def find_by_job_id(self, job_id: str) -> Optional[DownloadIndexEntry]:
        """
        Busca una entrada por job_id.
        
        Args:
            job_id: ID del job
            
        Returns:
            DownloadIndexEntry si se encuentra
        """
        con = self._connect()
        try:
            cur = con.execute(
                """SELECT url, type, quality, format, files_json, status, job_id,
                          created_at, last_access, error
                   FROM downloads WHERE job_id=?""",
                (job_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            
            return DownloadIndexEntry(
                url=row[0],
                type=row[1],
                quality=row[2],
                format=row[3],
                files=json.loads(row[4]) if row[4] else [],
                status=row[5],
                job_id=row[6],
                created_at=row[7],
                last_access=row[8],
                error=row[9],
            )
        finally:
            con.close()


class MediaRepository(BaseRepository):
    """
    Repositorio para archivos de media.
    Gestiona el catálogo de archivos y sus metadatos.
    """
    
    def ensure_schema(self) -> None:
        """Crea las tablas de media si no existen."""
        con = self._connect()
        try:
            con.execute(
                """CREATE TABLE IF NOT EXISTS media_files (
                  hash TEXT PRIMARY KEY,
                  path TEXT NOT NULL,
                  size_bytes INTEGER,
                  created_at TEXT,
                  quality TEXT,
                  format TEXT,
                  display_name TEXT
                )"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS url_to_media (
                  url TEXT PRIMARY KEY,
                  hash TEXT NOT NULL,
                  added_at TEXT,
                  FOREIGN KEY(hash) REFERENCES media_files(hash)
                )"""
            )
            con.commit()
        finally:
            con.close()
    
    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """
        Calcula el hash SHA256 de un archivo.
        
        Args:
            file_path: Ruta del archivo
            
        Returns:
            Hash en hexadecimal
        """
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1_048_576), b""):
                h.update(chunk)
        return h.hexdigest()
    
    def upsert_media(
        self,
        file_path: Path,
        created_at: str,
        quality: Optional[str],
        format_: Optional[str],
        display_name: Optional[str]
    ) -> str:
        """
        Inserta o actualiza un archivo de media.
        
        Args:
            file_path: Ruta del archivo
            created_at: Timestamp de creación
            quality: Calidad opcional
            format_: Formato opcional
            display_name: Nombre para mostrar
            
        Returns:
            Hash del archivo
        """
        file_hash = self.compute_hash(file_path)
        size = file_path.stat().st_size
        
        con = self._connect()
        try:
            con.execute(
                """INSERT OR REPLACE INTO media_files
                   (hash, path, size_bytes, created_at, quality, format, display_name) 
                   VALUES (?,?,?,?,?,?,?)""",
                (file_hash, str(file_path), size, created_at, quality, format_, display_name),
            )
            con.commit()
        finally:
            con.close()
        
        return file_hash
    
    def map_url_to_hash(self, url: str, file_hash: str, added_at: str) -> None:
        """
        Mapea una URL a un hash de archivo.
        
        Args:
            url: URL a mapear
            file_hash: Hash del archivo
            added_at: Timestamp
        """
        con = self._connect()
        try:
            con.execute(
                """INSERT OR REPLACE INTO url_to_media(url, hash, added_at) 
                   VALUES (?,?,?)""",
                (url, file_hash, added_at),
            )
            con.commit()
        finally:
            con.close()
    
    def get_by_url(self, url: str) -> Optional[MediaInfo]:
        """
        Obtiene información de media por URL.
        
        Args:
            url: URL a buscar
            
        Returns:
            MediaInfo si se encuentra
        """
        con = self._connect()
        try:
            cur = con.execute(
                "SELECT hash FROM url_to_media WHERE url=?", (url,)
            )
            row = cur.fetchone()
            if not row:
                return None
            
            file_hash = row[0]
            cur2 = con.execute(
                """SELECT path, quality, format, display_name, size_bytes, created_at 
                   FROM media_files WHERE hash=?""",
                (file_hash,)
            )
            row2 = cur2.fetchone()
            if not row2:
                return None
            
            return MediaInfo(
                hash=file_hash,
                path=row2[0],
                quality=row2[1],
                format=row2[2],
                display_name=row2[3],
                size_bytes=row2[4],
                created_at=row2[5],
            )
        finally:
            con.close()


# Instancias globales de repositorios
_db_path = settings.BASE_DIR / "app" / "storage" / "downloads.db"
download_index_repo = DownloadIndexRepository(_db_path)
media_repo = MediaRepository(_db_path)
