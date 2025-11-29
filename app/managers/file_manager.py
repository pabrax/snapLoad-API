"""
Gestor de archivos y metadatos.
Centraliza las operaciones con archivos y metadatos de jobs.
"""
import json
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..core.config import settings
from ..core.exceptions import FileNotFoundException, JobNotFoundException
from ..helpers import FileNameHelper, DateTimeHelper
from ..schemas import JobMetadata, FileInfo


class FileManager:
    """
    Gestor de operaciones con archivos.
    Responsable de mover, limpiar y gestionar archivos descargados.
    """
    
    @staticmethod
    def move_files_to_destination(
        source_folder: Path,
        destination_folder: Path,
        file_extensions: set
    ) -> List[FileInfo]:
        """
        Mueve archivos de una carpeta temporal a su destino final.
        
        Args:
            source_folder: Carpeta origen
            destination_folder: Carpeta destino
            file_extensions: Set de extensiones a mover
            
        Returns:
            Lista de FileInfo con los archivos movidos
        """
        if not source_folder.exists():
            return []
        
        destination_folder.mkdir(parents=True, exist_ok=True)
        moved_files = []
        
        for file_path in source_folder.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in file_extensions:
                # Sanitizar nombre y evitar colisiones
                safe_name = FileNameHelper.sanitize_filename(file_path.name)
                dest = destination_folder / safe_name
                dest = FileNameHelper.unique_path(dest)
                
                # Mover archivo
                shutil.move(str(file_path), str(dest))
                
                moved_files.append(FileInfo(
                    name=dest.name,
                    path=str(dest),
                    size_bytes=dest.stat().st_size
                ))
        
        return moved_files
    
    @staticmethod
    def cleanup_temp_directory(temp_folder: Path) -> None:
        """
        Limpia una carpeta temporal eliminando su contenido.
        
        Args:
            temp_folder: Carpeta a limpiar
        """
        try:
            for sub in temp_folder.glob("*"):
                if sub.is_dir():
                    shutil.rmtree(sub)
                elif sub.is_file():
                    sub.unlink()
            
            if temp_folder.exists() and not any(temp_folder.iterdir()):
                temp_folder.rmdir()
        except Exception:
            # No fallar si la limpieza tiene problemas
            pass
    
    @staticmethod
    def get_download_path(media_type: str, quality_or_format: Optional[str] = None) -> Path:
        """
        Obtiene la ruta de destino para descargas según tipo y calidad/formato.
        
        Args:
            media_type: "audio" o "video"
            quality_or_format: Calidad (para audio) o formato (para video)
            
        Returns:
            Ruta del directorio de destino
        """
        from ..core.constants import DEFAULT_QUALITY
        
        subfolder = quality_or_format or DEFAULT_QUALITY
        path = settings.DOWNLOAD_DIR / media_type / subfolder
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @staticmethod
    def get_temp_path(source: str, media_type: str, job_id: str) -> Path:
        """
        Obtiene una ruta temporal para un job específico.
        
        Args:
            source: "spotify" o "yt"
            media_type: "audio" o "video"
            job_id: ID del job
            
        Returns:
            Ruta del directorio temporal
        """
        path = settings.TMP_DIR / source / media_type / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @staticmethod
    def get_log_path(source: str, job_id: str) -> tuple[Path, Path]:
        """
        Obtiene las rutas de directorio y archivo de log para un job.
        
        Args:
            source: "spotify" o "yt"
            job_id: ID del job
            
        Returns:
            Tupla (directorio_log, archivo_log)
        """
        log_dir = settings.LOGS_DIR / source / job_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"job-{job_id}.log"
        return log_dir, log_file
    
    @staticmethod
    def verify_file_in_downloads(file_path: Path) -> bool:
        """
        Verifica que un archivo esté dentro del directorio de descargas.
        
        Args:
            file_path: Ruta del archivo a verificar
            
        Returns:
            True si el archivo está dentro de downloads
        """
        try:
            file_path.resolve().relative_to(settings.DOWNLOAD_DIR.resolve())
            return True
        except ValueError:
            return False
    
    @staticmethod
    def create_archive(job_id: str, files: List[FileInfo]) -> Path:
        """
        Crea un archivo ZIP con los archivos de un job.
        
        Args:
            job_id: ID del job
            files: Lista de FileInfo a incluir
            
        Returns:
            Ruta del archivo ZIP creado
        """
        import zipfile
        
        tmp_archives = settings.TMP_DIR / "archives"
        tmp_archives.mkdir(parents=True, exist_ok=True)
        zip_path = tmp_archives / f"{job_id}.zip"
        
        with zipfile.ZipFile(str(zip_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_info in files:
                file_path = Path(file_info.path)
                if file_path.exists() and FileManager.verify_file_in_downloads(file_path):
                    zf.write(str(file_path), arcname=file_path.name)
        
        return zip_path


class MetadataManager:
    """
    Gestor de metadatos de jobs.
    Responsable de leer/escribir archivos de metadatos.
    """
    
    @staticmethod
    def get_metadata_path(job_id: str) -> Path:
        """
        Obtiene la ruta del archivo de metadatos para un job.
        
        Args:
            job_id: ID del job
            
        Returns:
            Ruta del archivo de metadatos
        """
        settings.META_DIR.mkdir(parents=True, exist_ok=True)
        return settings.META_DIR / f"meta-{job_id}.json"
    
    @staticmethod
    def read_metadata(job_id: str) -> JobMetadata:
        """
        Lee metadatos de un job (alias de load_metadata que lanza excepción).
        
        Args:
            job_id: ID del job
            
        Returns:
            JobMetadata
            
        Raises:
            JobNotFoundException: Si no se encuentran metadatos
        """
        metadata = MetadataManager.load_metadata(job_id)
        if not metadata:
            raise JobNotFoundException(job_id=job_id)
        return metadata
    
    @staticmethod
    def write_metadata(metadata: JobMetadata) -> None:
        """
        Escribe metadatos (alias de save_metadata para consistencia).
        
        Args:
            metadata: Objeto JobMetadata a guardar
        """
        MetadataManager.save_metadata(metadata)
    
    @staticmethod
    def save_metadata(metadata: JobMetadata) -> None:
        """
        Guarda metadatos de un job en disco.
        
        Args:
            metadata: Objeto JobMetadata a guardar
        """
        path = MetadataManager.get_metadata_path(metadata.job_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata.dict(), f, indent=2, ensure_ascii=False)
    
    @staticmethod
    def load_metadata(job_id: str) -> Optional[JobMetadata]:
        """
        Carga metadatos de un job desde disco.
        
        Args:
            job_id: ID del job
            
        Returns:
            JobMetadata o None si no existe
        """
        path = MetadataManager.get_metadata_path(job_id)
        if not path.exists():
            return None
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return JobMetadata(**data)
        except Exception:
            return None
    
    @staticmethod
    def metadata_exists(job_id: str) -> bool:
        """
        Verifica si existen metadatos para un job.
        
        Args:
            job_id: ID del job
            
        Returns:
            True si existe el archivo de metadatos
        """
        return MetadataManager.get_metadata_path(job_id).exists()
    
    @staticmethod
    def update_metadata_status(
        job_id: str,
        status: str,
        error: Optional[str] = None,
        files: Optional[List[dict]] = None
    ) -> None:
        """
        Actualiza el estado de un metadata existente.
        
        Args:
            job_id: ID del job
            status: Nuevo estado
            error: Mensaje de error opcional
            files: Lista de archivos opcional
        """
        metadata = MetadataManager.load_metadata(job_id)
        if not metadata:
            return
        
        metadata.status = status
        metadata.finished_at = DateTimeHelper.now_iso()
        
        if error is not None:
            metadata.error = error
        
        if files is not None:
            metadata.files = files
        
        MetadataManager.save_metadata(metadata)
    
    @staticmethod
    def create_failure_metadata(
        job_id: str,
        url: str,
        media_type: str,
        log_path: Path,
        error: str,
        created_at: Optional[str] = None,
        started_at: Optional[str] = None
    ) -> JobMetadata:
        """
        Crea metadatos para un job fallido.
        
        Args:
            job_id: ID del job
            url: URL que se intentó descargar
            media_type: Tipo de media
            log_path: Ruta del log
            error: Mensaje de error
            created_at: Timestamp de creación (opcional)
            started_at: Timestamp de inicio (opcional)
            
        Returns:
            JobMetadata creado
        """
        now = DateTimeHelper.now_iso()
        
        metadata = JobMetadata(
            job_id=job_id,
            url=url,
            type=media_type,
            source_id=None,
            artist=None,
            album=None,
            created_at=created_at or now,
            started_at=started_at,
            finished_at=now,
            status="failed",
            files=[],
            log_path=str(log_path),
            error=error,
            inferred_from_filenames=False,
        )
        
        MetadataManager.save_metadata(metadata)
        return metadata


# Instancias globales
file_manager = FileManager()
metadata_manager = MetadataManager()
