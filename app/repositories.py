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
from .schemas import DownloadIndexEntry, MediaInfo, TrackEntry


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
                     AND IFNULL(format,'')=IFNULL(?, '')
                   ORDER BY CASE status WHEN 'ready' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                            created_at DESC""",
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
            
            if entry.status == "ready":
                missing = [p for p in entry.files if not Path(p).exists()]
                if missing:
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
    
    def fail_pending_before(self, cutoff: str, error: str) -> int:
        """
        Marca como fallidas las descargas pendientes creadas antes de `cutoff`.

        Un proceso que se reinicia no conserva los jobs en memoria, así que sus filas
        pendientes anteriores al arranque nunca terminarán; sin esto la URL quedaría
        "en progreso" para siempre.

        Args:
            cutoff: Timestamp ISO; solo se afectan filas creadas antes
            error: Mensaje de error a guardar

        Returns:
            Número de filas actualizadas
        """
        con = self._connect()
        try:
            cur = con.execute(
                """UPDATE downloads SET status='failed', error=?
                   WHERE status='pending' AND created_at < ?""",
                (error, cutoff),
            )
            con.commit()
            return cur.rowcount
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
    
    def get_all_ready_entries(self) -> List[DownloadIndexEntry]:
        """
        Obtiene todas las entradas con status='ready'.
        
        Returns:
            Lista de DownloadIndexEntry
        """
        con = self._connect()
        try:
            cur = con.execute(
                """SELECT url, type, quality, format, files_json, status, job_id,
                          created_at, last_access, error
                   FROM downloads WHERE status='ready'"""
            )
            rows = cur.fetchall()
            
            entries = []
            for row in rows:
                entries.append(DownloadIndexEntry(
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
                ))
            
            return entries
        finally:
            con.close()
    
    def get_old_failed_entries(self, max_age_hours: float) -> List[DownloadIndexEntry]:
        """
        Obtiene entradas con status='failed' más antiguas que max_age_hours.
        
        Args:
            max_age_hours: Edad máxima en horas
            
        Returns:
            Lista de DownloadIndexEntry
        """
        from datetime import datetime, timedelta
        
        con = self._connect()
        try:
            # Calcular timestamp límite
            cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
            
            cur = con.execute(
                """SELECT url, type, quality, format, files_json, status, job_id,
                          created_at, last_access, error
                   FROM downloads 
                   WHERE status='failed' AND created_at < ?""",
                (cutoff,)
            )
            rows = cur.fetchall()
            
            entries = []
            for row in rows:
                entries.append(DownloadIndexEntry(
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
                ))
            
            return entries
        finally:
            con.close()
    
    def delete_entry(
        self,
        url: str,
        media_type: str,
        quality: Optional[str],
        format_: Optional[str]
    ) -> bool:
        """
        Elimina una entrada del índice.
        
        Args:
            url: URL
            media_type: Tipo de media
            quality: Calidad opcional
            format_: Formato opcional
            
        Returns:
            True si se eliminó, False si no existía
        """
        con = self._connect()
        try:
            cur = con.execute(
                """DELETE FROM downloads 
                   WHERE url=? AND type=? 
                     AND IFNULL(quality,'')=IFNULL(?, '') 
                     AND IFNULL(format,'')=IFNULL(?, '')""",
                (url, media_type, quality, format_),
            )
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()
    
    def _get_total_records(self) -> int:
        """
        Obtiene el total de registros en la tabla downloads.
        
        Returns:
            Número de registros
        """
        con = self._connect()
        try:
            cur = con.execute("SELECT COUNT(*) FROM downloads")
            row = cur.fetchone()
            return row[0] if row else 0
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


def track_id_for(path: Path) -> str:
    """
    Id opaco y estable de una pista: 16 hex del sha256 de su ruta relativa a DOWNLOAD_DIR.

    Args:
        path: Ruta del archivo de audio

    Returns:
        Id de 16 caracteres hexadecimales
    """
    try:
        key = Path(path).resolve().relative_to(settings.DOWNLOAD_DIR.resolve()).as_posix()
    except ValueError:
        key = Path(path).resolve().as_posix()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class TrackRepository(BaseRepository):
    """
    Repositorio de la biblioteca de música.
    Cachea los tags de cada pista de audio y la marca `kept` que protege de la limpieza.
    """

    _COLUMNS = (
        "id, job_id, path, title, artist, album, duration_s, format, "
        "size_bytes, has_cover, kept, mtime, tags_source"
    )

    def ensure_schema(self) -> None:
        """Crea la tabla tracks si no existe."""
        con = self._connect()
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS tracks (
                  id TEXT PRIMARY KEY,
                  job_id TEXT,
                  path TEXT NOT NULL,
                  title TEXT,
                  artist TEXT,
                  album TEXT,
                  duration_s REAL,
                  format TEXT,
                  size_bytes INTEGER NOT NULL DEFAULT 0,
                  has_cover INTEGER NOT NULL DEFAULT 0,
                  kept INTEGER NOT NULL DEFAULT 0,
                  mtime REAL NOT NULL DEFAULT 0,
                  tags_source TEXT
                )
                """
            )
            con.commit()
        finally:
            con.close()

    @staticmethod
    def _entry(row) -> TrackEntry:
        return TrackEntry(
            id=row[0],
            job_id=row[1],
            path=row[2],
            title=row[3],
            artist=row[4],
            album=row[5],
            duration_s=row[6],
            format=row[7],
            size_bytes=row[8],
            has_cover=bool(row[9]),
            kept=bool(row[10]),
            mtime=row[11],
            tags_source=row[12],
        )

    def upsert(
        self,
        path: Path,
        job_id: Optional[str] = None,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        duration_s: Optional[float] = None,
        fmt: Optional[str] = None,
        size_bytes: int = 0,
        has_cover: bool = False,
        kept: Optional[bool] = None,
        mtime: Optional[float] = None,
        tags_source: Optional[str] = None,
    ) -> str:
        """
        Inserta o actualiza una pista por su id (derivado de la ruta).

        Args:
            path: Ruta del archivo de audio
            kept: Marca kept; None conserva el valor existente (False en una pista nueva)
            mtime: Fecha de modificación; por defecto la del archivo (o 0 si no existe)

        Returns:
            Id de la pista
        """
        path = Path(path)
        track_id = track_id_for(path)
        if mtime is None:
            mtime = path.stat().st_mtime if path.exists() else 0.0

        con = self._connect()
        try:
            con.execute(
                f"""INSERT INTO tracks({self._COLUMNS})
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                      job_id=COALESCE(excluded.job_id, tracks.job_id),
                      path=excluded.path,
                      title=excluded.title,
                      artist=excluded.artist,
                      album=excluded.album,
                      duration_s=excluded.duration_s,
                      format=excluded.format,
                      size_bytes=excluded.size_bytes,
                      has_cover=excluded.has_cover,
                      kept=CASE WHEN ? IS NULL THEN tracks.kept ELSE excluded.kept END,
                      mtime=excluded.mtime,
                      tags_source=excluded.tags_source""",
                (
                    track_id, job_id, str(path), title, artist, album, duration_s, fmt,
                    size_bytes, int(has_cover), int(bool(kept)), mtime, tags_source,
                    None if kept is None else int(kept),
                ),
            )
            con.commit()
        finally:
            con.close()
        return track_id

    def get(self, track_id: str) -> Optional[TrackEntry]:
        """Obtiene una pista por id, o None si no existe."""
        con = self._connect()
        try:
            row = con.execute(
                f"SELECT {self._COLUMNS} FROM tracks WHERE id=?", (track_id,)
            ).fetchone()
            return self._entry(row) if row else None
        finally:
            con.close()

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        q: Optional[str] = None,
    ) -> "tuple[List[TrackEntry], int]":
        """
        Lista pistas, las más recientes primero.

        Args:
            limit: Máximo de pistas a devolver
            offset: Pistas a saltar
            q: Subcadena a buscar en título o artista (sin distinguir mayúsculas ASCII)

        Returns:
            (pistas de la página, total de coincidencias)
        """
        where, params = "", []
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where = "WHERE title LIKE ? ESCAPE '\\' OR artist LIKE ? ESCAPE '\\'"
            params = [f"%{escaped}%", f"%{escaped}%"]

        con = self._connect()
        try:
            total = con.execute(f"SELECT COUNT(*) FROM tracks {where}", params).fetchone()[0]
            rows = con.execute(
                f"""SELECT {self._COLUMNS} FROM tracks {where}
                    ORDER BY mtime DESC, rowid DESC LIMIT ? OFFSET ?""",
                [*params, limit, offset],
            ).fetchall()
            return [self._entry(r) for r in rows], total
        finally:
            con.close()

    def set_kept(self, track_id: str, kept: bool) -> Optional[TrackEntry]:
        """Cambia la marca kept; devuelve la pista actualizada o None si no existe."""
        con = self._connect()
        try:
            con.execute("UPDATE tracks SET kept=? WHERE id=?", (int(kept), track_id))
            con.commit()
        finally:
            con.close()
        return self.get(track_id)

    def delete(self, track_id: str) -> bool:
        """Elimina el registro de una pista; True si existía."""
        con = self._connect()
        try:
            cur = con.execute("DELETE FROM tracks WHERE id=?", (track_id,))
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()

    def kept_bytes(self) -> int:
        """Suma de bytes de las pistas kept."""
        con = self._connect()
        try:
            return con.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM tracks WHERE kept=1"
            ).fetchone()[0]
        finally:
            con.close()

    def kept_paths(self) -> "set[str]":
        """Rutas (str) de los audios de pistas kept."""
        con = self._connect()
        try:
            return {r[0] for r in con.execute("SELECT path FROM tracks WHERE kept=1")}
        finally:
            con.close()


# Instancias globales de repositorios
_db_path = settings.BASE_DIR / "app" / "storage" / "downloads.db"
download_index_repo = DownloadIndexRepository(_db_path)
media_repo = MediaRepository(_db_path)
track_repo = TrackRepository(_db_path)
