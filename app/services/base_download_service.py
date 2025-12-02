"""
Servicio base de descarga.
Define la interfaz común para todos los servicios de descarga.
"""
import subprocess
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Callable, List
import threading

from ..core.config import settings
from ..core.enums import JobStatus, MediaType
from ..schemas import JobMetadata, FileInfo
from ..managers import job_manager, file_manager, metadata_manager
from ..helpers import DateTimeHelper, TextHelper
from ..repositories import download_index_repo, media_repo


class BaseDownloadService(ABC):
    """
    Servicio base abstracto para descargas.
    Define el template method pattern para el proceso de descarga.
    """
    
    def __init__(self):
        """Inicializa el servicio de descarga."""
        self.job_manager = job_manager
        self.file_manager = file_manager
        self.metadata_manager = metadata_manager
        self.download_index = download_index_repo
        self.media_repo = media_repo
    
    @abstractmethod
    def get_source_name(self) -> str:
        """Retorna el nombre de la fuente ('spotify' o 'yt')."""
        pass
    
    @abstractmethod
    def get_media_type(self) -> MediaType:
        """Retorna el tipo de media (audio o video)."""
        pass
    
    @abstractmethod
    def build_command(
        self,
        url: str,
        output_path: Path,
        **kwargs
    ) -> List[str]:
        """
        Construye el comando a ejecutar.
        
        Args:
            url: URL a descargar
            output_path: Ruta de salida
            **kwargs: Parámetros adicionales (quality, format, etc.)
            
        Returns:
            Lista de argumentos del comando
        """
        pass
    
    @abstractmethod
    def get_file_extensions(self) -> set:
        """Retorna el set de extensiones de archivo esperadas."""
        pass
    
    @abstractmethod
    def validate_url(self, url: str) -> None:
        """
        Valida que la URL sea válida para esta fuente.
        
        Args:
            url: URL a validar
            
        Raises:
            InvalidURLException: Si la URL no es válida
        """
        pass
    
    def download(
        self,
        url: str,
        job_id: Optional[str] = None,
        callback: Optional[Callable] = None,
        **kwargs
    ) -> None:
        """
        Inicia la descarga en un thread daemon.
        
        Args:
            url: URL a descargar
            job_id: ID del job (se genera si no se proporciona)
            callback: Función de callback al finalizar
            **kwargs: Parámetros adicionales (quality, format, etc.)
        """
        thread = threading.Thread(
            target=self.download_sync,
            args=(url,),
            kwargs={"job_id": job_id, "callback": callback, **kwargs}
        )
        thread.daemon = True
        thread.start()
    
    def download_sync(
        self,
        url: str,
        job_id: Optional[str] = None,
        callback: Optional[Callable] = None,
        **kwargs
    ) -> None:
        """
        Ejecuta la descarga de forma síncrona (template method).
        
        Args:
            url: URL a descargar
            job_id: ID del job (se genera si no se proporciona)
            callback: Función de callback al finalizar
            **kwargs: Parámetros adicionales (quality, format, etc.)
        """
        # 1. Preparación
        job_id = job_id or self._generate_job_id()
        created_at = DateTimeHelper.now_iso()
        
        # 2. Validación temprana
        try:
            self.validate_url(url)
        except Exception as e:
            self._handle_validation_error(url, job_id, created_at, str(e))
            if callback:
                callback(None, None)
            return
        
        # 3. Preparar directorios
        paths = self._prepare_paths(job_id, **kwargs)
        
        # 4. Iniciar descarga
        started_at = DateTimeHelper.now_iso()
        try:
            with open(paths["log_file"], "w", encoding="utf-8") as log_file:
                log_file.write(f"[{started_at}] JOB {job_id} START url={url}\n")
                
                # Construir comando
                command = self.build_command(url, paths["temp_dir"], **kwargs)
                
                # Ejecutar proceso
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    preexec_fn=os.setsid,
                )
                
                self.job_manager.register_job(job_id, process)
                
                raw_output = self._capture_output(process, log_file)
            
            finished_at = DateTimeHelper.now_iso()
            self.job_manager.unregister_job(job_id)
            
            success = process.returncode == 0
            
            moved_files = self._move_files(paths["temp_dir"], paths["download_dir"])
            
            if success and len(moved_files) == 0:
                success = False
                error_msg = self._extract_error_from_output(raw_output)
            else:
                error_msg = None if success else TextHelper.truncate_text(raw_output)
            
            # 8. Limpiar
            self.file_manager.cleanup_temp_directory(paths["temp_dir"])
            
            # 9. Guardar metadata
            status = JobStatus.SUCCESS if success else JobStatus.FAILED
            self._save_metadata(
                job_id=job_id,
                url=url,
                created_at=created_at,
                started_at=started_at,
                finished_at=finished_at,
                status=status.value,
                moved_files=moved_files,
                log_path=paths["log_file"],
                error=error_msg,
                raw_output=raw_output,
                **kwargs
            )
            
            # 10. Registrar en índice y catálogo
            if success:
                self._register_success(job_id, moved_files, url, finished_at, **kwargs)
            else:
                self.download_index.register_failed(job_id, error_msg or "Download failed")
            
            # 11. Callback
            if callback:
                if success:
                    callback(
                        [f.name for f in moved_files],
                        [f.path for f in moved_files]
                    )
                else:
                    callback(None, None)
            
            # 12. Log
            print(f"JOB {job_id} STATUS {status.value} FILES {len(moved_files)} PATH {paths['download_dir']}")
        
        except Exception as e:
            self._handle_execution_error(
                job_id, url, created_at, started_at, paths["log_file"], str(e)
            )
            if callback:
                callback(None, None)
    
    def _generate_job_id(self) -> str:
        """Genera un ID único para el job."""
        import uuid
        return uuid.uuid4().hex[:8]
    
    def _prepare_paths(self, job_id: str, **kwargs) -> dict:
        """
        Prepara los directorios necesarios.
        
        Args:
            job_id: ID del job
            **kwargs: Parámetros adicionales
            
        Returns:
            Dict con las rutas necesarias
        """
        quality_or_format = kwargs.get("quality") or kwargs.get("format")
        
        download_dir = self.file_manager.get_download_path(
            self.get_media_type().value, quality_or_format
        )
        temp_dir = self.file_manager.get_temp_path(
            self.get_source_name(), self.get_media_type().value, job_id
        )
        log_dir, log_file = self.file_manager.get_log_path(
            self.get_source_name(), job_id
        )
        
        return {
            "download_dir": download_dir,
            "temp_dir": temp_dir,
            "log_dir": log_dir,
            "log_file": log_file,
        }
    
    def _capture_output(self, process: subprocess.Popen, log_file) -> str:
        """Captura la salida del proceso."""
        raw_lines = []
        try:
            if process.stdout:
                for line in process.stdout:
                    raw_lines.append(line)
                    log_file.write(line)
        except Exception:
            pass
        
        try:
            process.wait()
        except Exception:
            pass
        
        return "".join(raw_lines)
    
    def _move_files(self, temp_dir: Path, download_dir: Path) -> List[FileInfo]:
        """Mueve los archivos desde el directorio temporal al final."""
        return self.file_manager.move_files_to_destination(
            temp_dir, download_dir, self.get_file_extensions()
        )
    
    def _extract_error_from_output(self, output: str) -> str:
        """Extrae un mensaje de error relevante de la salida."""
        if not output:
            return "No files produced (no output)"
        
        lines = [l for l in output.splitlines() if l.strip()]
        extracted = None
        
        # Buscar líneas con "Error" en las últimas 200 líneas
        for line in reversed(lines[-200:]):
            if "Error" in line or "AudioProviderError" in line or "Traceback" in line:
                extracted = line
                break
        
        if not extracted and lines:
            extracted = lines[-1]
        
        return extracted or "Unknown error"
    
    def _save_metadata(
        self,
        job_id: str,
        url: str,
        created_at: str,
        started_at: str,
        finished_at: str,
        status: str,
        moved_files: List[FileInfo],
        log_path: Path,
        error: Optional[str],
        raw_output: str,
        **kwargs
    ) -> None:
        """Guarda los metadatos del job."""
        # Extraer resumen si hay éxito
        summary = None
        if status == JobStatus.SUCCESS.value and raw_output:
            summary = self._extract_summary(raw_output)
        
        metadata = JobMetadata(
            job_id=job_id,
            url=url,
            type=self.get_media_type().value,
            source_id=None,
            artist=None,
            album=None,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            files=[f.dict() for f in moved_files],
            log_path=str(log_path),
            error=error,
            inferred_from_filenames=False,
        )
        
        # Agregar summary específico según la fuente
        if self.get_source_name() == "spotify":
            metadata.raw_spotdl_summary = summary
        else:
            metadata.raw_yt_summary = summary
        
        self.metadata_manager.save_metadata(metadata)
    
    def _extract_summary(self, output: str) -> Optional[str]:
        """Extrae un resumen de la salida del comando."""
        import re
        
        patterns = [
            r"Downloaded\s+\d+\s+tracks",
            r"Downloaded\s+\d+\s+files?",
            r"Merged",
            r"Destination:\s+",
        ]
        
        for pattern in patterns:
            m = re.search(pattern, output)
            if m:
                return m.group(0)
        
        return None
    
    def _register_success(
        self,
        job_id: str,
        moved_files: List[FileInfo],
        url: str,
        finished_at: str,
        **kwargs
    ) -> None:
        """Registra el éxito en índice y catálogo."""
        file_paths = [f.path for f in moved_files]
        
        # Registrar en índice
        self.download_index.register_success(job_id, file_paths)
        
        # Registrar en catálogo de media
        quality = kwargs.get("quality")
        format_ = kwargs.get("format")
        
        try:
            for file_info in moved_files:
                file_path = Path(file_info.path)
                file_hash = self.media_repo.upsert_media(
                    file_path,
                    finished_at,
                    quality,
                    format_,
                    file_path.stem
                )
                self.media_repo.map_url_to_hash(url, file_hash, finished_at)
        except Exception:
            # No fallar si el registro en catálogo falla
            pass
    
    def _handle_validation_error(
        self,
        url: str,
        job_id: str,
        created_at: str,
        error: str
    ) -> None:
        """Maneja errores de validación."""
        log_dir, log_file = self.file_manager.get_log_path(
            self.get_source_name(), job_id
        )
        
        metadata = self.metadata_manager.create_failure_metadata(
            job_id=job_id,
            url=url,
            media_type=self.get_media_type().value,
            log_path=log_file,
            error=error,
            created_at=created_at,
        )
        
        # ⭐ IMPORTANTE: Registrar el fallo en el índice
        self.download_index.register_failed(job_id, error)
        
        print(f"JOB {job_id} STATUS failed reason=validation_error")
    
    def _handle_execution_error(
        self,
        job_id: str,
        url: str,
        created_at: str,
        started_at: str,
        log_path: Path,
        error: str
    ) -> None:
        """Maneja errores durante la ejecución."""
        finished_at = DateTimeHelper.now_iso()
        
        metadata = self.metadata_manager.create_failure_metadata(
            job_id=job_id,
            url=url,
            media_type=self.get_media_type().value,
            log_path=log_path,
            error=error,
            created_at=created_at,
            started_at=started_at,
        )
        
        self.download_index.register_failed(job_id, error)
        print(f"JOB {job_id} STATUS failed exception={error}")
