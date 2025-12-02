"""
Servicio de limpieza y optimización del servidor.
Implementa limpieza automática de archivos antiguos y huérfanos.
"""
import logging
import shutil
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta

from ..core.config import settings, cleanup_settings
from ..core.enums import CleanupTarget, CleanupStrategy
from ..schemas import CleanupStats, CleanupSummary, StorageStats
from ..repositories import download_index_repo, media_repo
from ..helpers import DateTimeHelper


class CleanupService:
    """
    Servicio de limpieza y optimización del servidor.
    
    Responsabilidades:
    - Eliminar archivos antiguos según políticas de retención
    - Limpiar logs y metadatos huérfanos
    - Mantener consistencia de base de datos
    - Generar reportes detallados de limpieza
    """
    
    def __init__(self):
        self.download_index = download_index_repo
        self.media_catalog = media_repo
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """Configura el logger para operaciones de limpieza."""
        logger = logging.getLogger("cleanup_service")
        logger.setLevel(getattr(logging, cleanup_settings.CLEANUP_LOG_LEVEL))
        
        # Crear directorio de logs si no existe
        cleanup_settings.CLEANUP_LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        # Handler de archivo con timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        log_file = cleanup_settings.CLEANUP_LOG_DIR / f"cleanup-{timestamp}.log"
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Handler de consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formato detallado
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def cleanup_all(
        self,
        strategy: str = "age_based",
        dry_run: bool = None
    ) -> CleanupSummary:
        """
        Ejecuta limpieza completa de todos los targets.
        
        Args:
            strategy: Estrategia de limpieza
            dry_run: Si es True, solo simula. Si es None, usa configuración
            
        Returns:
            CleanupSummary con resultados
        """
        if dry_run is None:
            dry_run = cleanup_settings.CLEANUP_DRY_RUN
        
        start_time = time.time()
        self.logger.info("=" * 60)
        self.logger.info("CLEANUP STARTED")
        self.logger.info("=" * 60)
        self.logger.info(f"Config: retention={cleanup_settings.RETENTION_HOURS}h, dry_run={dry_run}")
        self.logger.info("")
        
        targets_cleaned = []
        total_files = 0
        total_space = 0.0
        errors = []
        
        # 1. Limpiar downloads
        try:
            stats = self.cleanup_downloads(strategy, dry_run)
            targets_cleaned.append(stats)
            total_files += stats.files_deleted
            total_space += stats.space_freed_mb
        except Exception as e:
            error_msg = f"Error en limpieza de downloads: {str(e)}"
            self.logger.error(error_msg)
            errors.append(error_msg)
        
        # 2. Limpiar logs
        try:
            stats = self.cleanup_logs(cleanup_settings.RETENTION_HOURS, dry_run)
            targets_cleaned.append(stats)
            total_files += stats.files_deleted
            total_space += stats.space_freed_mb
        except Exception as e:
            error_msg = f"Error en limpieza de logs: {str(e)}"
            self.logger.error(error_msg)
            errors.append(error_msg)
        
        # 3. Limpiar metadata
        try:
            stats = self.cleanup_metadata(cleanup_settings.RETENTION_HOURS, dry_run)
            targets_cleaned.append(stats)
            total_files += stats.files_deleted
            total_space += stats.space_freed_mb
        except Exception as e:
            error_msg = f"Error en limpieza de metadata: {str(e)}"
            self.logger.error(error_msg)
            errors.append(error_msg)
        
        # 4. Limpiar temp
        try:
            stats = self.cleanup_temp(dry_run)
            targets_cleaned.append(stats)
            total_files += stats.files_deleted
            total_space += stats.space_freed_mb
        except Exception as e:
            error_msg = f"Error en limpieza de temp: {str(e)}"
            self.logger.error(error_msg)
            errors.append(error_msg)
        
        # 5. Limpiar base de datos
        try:
            stats = self.cleanup_database(cleanup_settings.RETENTION_HOURS, dry_run)
            targets_cleaned.append(stats)
            total_files += stats.files_deleted
            total_space += stats.space_freed_mb
        except Exception as e:
            error_msg = f"Error en limpieza de database: {str(e)}"
            self.logger.error(error_msg)
            errors.append(error_msg)
        
        duration = time.time() - start_time
        
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info("CLEANUP COMPLETED")
        self.logger.info("=" * 60)
        self.logger.info(f"Total files deleted: {total_files}")
        self.logger.info(f"Total space freed: {total_space:.2f} MB")
        self.logger.info(f"Duration: {duration:.2f} seconds")
        if errors:
            self.logger.warning(f"Errors encountered: {len(errors)}")
        
        return CleanupSummary(
            total_files_deleted=total_files,
            total_space_freed_mb=round(total_space, 2),
            targets_cleaned=targets_cleaned,
            errors=errors,
            timestamp=DateTimeHelper.now_iso(),
            duration_seconds=round(duration, 2),
            dry_run=dry_run
        )
    
    def cleanup_downloads(
        self,
        strategy: str = "age_based",
        dry_run: bool = None
    ) -> CleanupStats:
        """
        Limpia archivos descargados antiguos.
        
        Args:
            strategy: Estrategia de limpieza
            dry_run: Si es True, solo simula
            
        Returns:
            CleanupStats con resultados
        """
        if dry_run is None:
            dry_run = cleanup_settings.CLEANUP_DRY_RUN
        
        start_time = time.time()
        self.logger.info("--- DOWNLOADS CLEANUP ---")
        
        files_deleted = 0
        space_freed = 0
        errors = []
        
        # Escanear downloads/audio/ y downloads/video/
        for media_dir in [settings.DOWNLOAD_DIR / "audio", settings.DOWNLOAD_DIR / "video"]:
            if not media_dir.exists():
                continue
            
            self.logger.info(f"Scanning: {media_dir}")
            
            # Obtener todos los archivos
            all_files = []
            for file_path in media_dir.rglob("*"):
                if file_path.is_file():
                    all_files.append(file_path)
            
            self.logger.info(f"Found: {len(all_files)} files")
            
            # Filtrar archivos elegibles para eliminación
            eligible_files = self._get_files_by_age(
                all_files,
                cleanup_settings.RETENTION_HOURS
            )
            
            self.logger.info(f"Eligible for deletion: {len(eligible_files)} files (older than {cleanup_settings.RETENTION_HOURS}h)")
            
            # Eliminar archivos
            for file_path in eligible_files:
                try:
                    age_hours = self._get_file_age_hours(file_path)
                    size_mb = file_path.stat().st_size / (1024 * 1024)
                    
                    self.logger.info(f"DELETE: {file_path} (age: {age_hours:.1f}h, size: {size_mb:.2f}MB)")
                    
                    if not dry_run:
                        file_path.unlink()
                        files_deleted += 1
                        space_freed += size_mb
                    else:
                        files_deleted += 1
                        space_freed += size_mb
                except Exception as e:
                    error_msg = f"Error deleting {file_path}: {str(e)}"
                    self.logger.error(error_msg)
                    errors.append(error_msg)
        
        duration = time.time() - start_time
        self.logger.info(f"Deleted: {files_deleted} files, freed: {space_freed:.2f} MB")
        self.logger.info("")
        
        return CleanupStats(
            target=CleanupTarget.DOWNLOADS.value,
            files_deleted=files_deleted,
            space_freed_bytes=int(space_freed * 1024 * 1024),
            space_freed_mb=round(space_freed, 2),
            duration_seconds=round(duration, 2),
            timestamp=DateTimeHelper.now_iso(),
            dry_run=dry_run,
            errors=errors
        )
    
    def cleanup_logs(
        self,
        max_age_hours: float,
        dry_run: bool = None
    ) -> CleanupStats:
        """
        Limpia logs antiguos de jobs.
        
        Args:
            max_age_hours: Edad máxima en horas
            dry_run: Si es True, solo simula
            
        Returns:
            CleanupStats con resultados
        """
        if dry_run is None:
            dry_run = cleanup_settings.CLEANUP_DRY_RUN
        
        start_time = time.time()
        self.logger.info("--- LOGS CLEANUP ---")
        
        files_deleted = 0
        space_freed = 0
        errors = []
        
        # Escanear logs/yt/ y logs/spotify/
        for source_dir in [settings.LOGS_DIR / "yt", settings.LOGS_DIR / "spotify"]:
            if not source_dir.exists():
                continue
            
            self.logger.info(f"Scanning: {source_dir}")
            
            # Obtener directorios de jobs
            job_dirs = [d for d in source_dir.iterdir() if d.is_dir()]
            self.logger.info(f"Found: {len(job_dirs)} log directories")
            
            # Filtrar elegibles
            eligible_dirs = []
            for job_dir in job_dirs:
                age_hours = self._get_dir_age_hours(job_dir)
                if age_hours > max_age_hours:
                    eligible_dirs.append(job_dir)
            
            self.logger.info(f"Eligible for deletion: {len(eligible_dirs)} directories")
            
            # Eliminar directorios
            for job_dir in eligible_dirs:
                try:
                    age_hours = self._get_dir_age_hours(job_dir)
                    size_mb = self._get_dir_size(job_dir) / (1024 * 1024)
                    
                    self.logger.info(f"DELETE: {job_dir} (age: {age_hours:.1f}h, size: {size_mb:.2f}MB)")
                    
                    if not dry_run:
                        shutil.rmtree(job_dir)
                        files_deleted += 1
                        space_freed += size_mb
                    else:
                        files_deleted += 1
                        space_freed += size_mb
                except Exception as e:
                    error_msg = f"Error deleting {job_dir}: {str(e)}"
                    self.logger.error(error_msg)
                    errors.append(error_msg)
        
        duration = time.time() - start_time
        self.logger.info(f"Deleted: {files_deleted} directories, freed: {space_freed:.2f} MB")
        self.logger.info("")
        
        return CleanupStats(
            target=CleanupTarget.LOGS.value,
            files_deleted=files_deleted,
            space_freed_bytes=int(space_freed * 1024 * 1024),
            space_freed_mb=round(space_freed, 2),
            duration_seconds=round(duration, 2),
            timestamp=DateTimeHelper.now_iso(),
            dry_run=dry_run,
            errors=errors
        )
    
    def cleanup_metadata(
        self,
        max_age_hours: float,
        dry_run: bool = None
    ) -> CleanupStats:
        """
        Limpia archivos de metadata antiguos.
        
        Args:
            max_age_hours: Edad máxima en horas
            dry_run: Si es True, solo simula
            
        Returns:
            CleanupStats con resultados
        """
        if dry_run is None:
            dry_run = cleanup_settings.CLEANUP_DRY_RUN
        
        start_time = time.time()
        self.logger.info("--- METADATA CLEANUP ---")
        
        files_deleted = 0
        space_freed = 0
        errors = []
        
        if not settings.META_DIR.exists():
            self.logger.info("Metadata directory does not exist, skipping")
            return CleanupStats(
                target=CleanupTarget.METADATA.value,
                files_deleted=0,
                space_freed_bytes=0,
                space_freed_mb=0.0,
                duration_seconds=0.0,
                timestamp=DateTimeHelper.now_iso(),
                dry_run=dry_run,
                errors=[]
            )
        
        self.logger.info(f"Scanning: {settings.META_DIR}")
        
        # Obtener archivos de metadata
        meta_files = list(settings.META_DIR.glob("meta-*.json"))
        self.logger.info(f"Found: {len(meta_files)} metadata files")
        
        # Filtrar por edad
        eligible_files = []
        for meta_file in meta_files:
            try:
                # Leer created_at del JSON
                with open(meta_file, 'r') as f:
                    data = json.load(f)
                    created_at = data.get('created_at')
                    
                    if created_at:
                        age_hours = self._get_age_from_timestamp(created_at)
                        if age_hours > max_age_hours:
                            eligible_files.append((meta_file, age_hours))
                    else:
                        # Si no tiene created_at, usar mtime
                        age_hours = self._get_file_age_hours(meta_file)
                        if age_hours > max_age_hours:
                            eligible_files.append((meta_file, age_hours))
            except Exception as e:
                self.logger.warning(f"Error reading {meta_file}: {str(e)}")
        
        self.logger.info(f"Eligible for deletion: {len(eligible_files)} files")
        
        # Eliminar archivos
        for meta_file, age_hours in eligible_files:
            try:
                size_mb = meta_file.stat().st_size / (1024 * 1024)
                
                self.logger.info(f"DELETE: {meta_file.name} (age: {age_hours:.1f}h, size: {size_mb:.3f}MB)")
                
                if not dry_run:
                    meta_file.unlink()
                    files_deleted += 1
                    space_freed += size_mb
                else:
                    files_deleted += 1
                    space_freed += size_mb
            except Exception as e:
                error_msg = f"Error deleting {meta_file}: {str(e)}"
                self.logger.error(error_msg)
                errors.append(error_msg)
        
        duration = time.time() - start_time
        self.logger.info(f"Deleted: {files_deleted} files, freed: {space_freed:.3f} MB")
        self.logger.info("")
        
        return CleanupStats(
            target=CleanupTarget.METADATA.value,
            files_deleted=files_deleted,
            space_freed_bytes=int(space_freed * 1024 * 1024),
            space_freed_mb=round(space_freed, 3),
            duration_seconds=round(duration, 2),
            timestamp=DateTimeHelper.now_iso(),
            dry_run=dry_run,
            errors=errors
        )
    
    def cleanup_temp(
        self,
        dry_run: bool = None
    ) -> CleanupStats:
        """
        Limpia directorio temporal agresivamente.
        
        Args:
            dry_run: Si es True, solo simula
            
        Returns:
            CleanupStats con resultados
        """
        if dry_run is None:
            dry_run = cleanup_settings.CLEANUP_DRY_RUN
        
        start_time = time.time()
        self.logger.info("--- TEMP CLEANUP ---")
        
        files_deleted = 0
        space_freed = 0
        errors = []
        
        if not settings.TMP_DIR.exists():
            self.logger.info("Temp directory does not exist, skipping")
            return CleanupStats(
                target=CleanupTarget.TEMP.value,
                files_deleted=0,
                space_freed_bytes=0,
                space_freed_mb=0.0,
                duration_seconds=0.0,
                timestamp=DateTimeHelper.now_iso(),
                dry_run=dry_run,
                errors=[]
            )
        
        self.logger.info(f"Scanning: {settings.TMP_DIR}")
        
        # Limpiar subdirectorios temporales
        for temp_subdir in [settings.TMP_DIR / "yt", settings.TMP_DIR / "spotify", settings.TMP_DIR / "archives"]:
            if not temp_subdir.exists():
                continue
            
            # Obtener todos los items
            items = list(temp_subdir.rglob("*"))
            
            for item in items:
                try:
                    age_hours = self._get_file_age_hours(item) if item.is_file() else self._get_dir_age_hours(item)
                    
                    # Usar retención más corta para temporales
                    if age_hours > cleanup_settings.TEMP_RETENTION_HOURS:
                        if item.is_file():
                            size_mb = item.stat().st_size / (1024 * 1024)
                            self.logger.info(f"DELETE: {item} (age: {age_hours:.1f}h, size: {size_mb:.2f}MB)")
                            
                            if not dry_run:
                                item.unlink()
                            files_deleted += 1
                            space_freed += size_mb
                        elif item.is_dir():
                            size_mb = self._get_dir_size(item) / (1024 * 1024)
                            self.logger.info(f"DELETE DIR: {item} (age: {age_hours:.1f}h, size: {size_mb:.2f}MB)")
                            
                            if not dry_run:
                                shutil.rmtree(item)
                            files_deleted += 1
                            space_freed += size_mb
                except Exception as e:
                    error_msg = f"Error deleting {item}: {str(e)}"
                    self.logger.error(error_msg)
                    errors.append(error_msg)
        
        duration = time.time() - start_time
        self.logger.info(f"Deleted: {files_deleted} items, freed: {space_freed:.2f} MB")
        self.logger.info("")
        
        return CleanupStats(
            target=CleanupTarget.TEMP.value,
            files_deleted=files_deleted,
            space_freed_bytes=int(space_freed * 1024 * 1024),
            space_freed_mb=round(space_freed, 2),
            duration_seconds=round(duration, 2),
            timestamp=DateTimeHelper.now_iso(),
            dry_run=dry_run,
            errors=errors
        )
    
    def cleanup_database(
        self,
        max_age_hours: float,
        dry_run: bool = None
    ) -> CleanupStats:
        """
        Limpia registros huérfanos y antiguos de la base de datos.
        
        Args:
            max_age_hours: Edad máxima en horas
            dry_run: Si es True, solo simula
            
        Returns:
            CleanupStats con resultados
        """
        if dry_run is None:
            dry_run = cleanup_settings.CLEANUP_DRY_RUN
        
        start_time = time.time()
        self.logger.info("--- DATABASE CLEANUP ---")
        
        records_deleted = 0
        errors = []
        
        # 1. Limpiar registros huérfanos (archivos no existen)
        self.logger.info("Checking orphan records...")
        try:
            orphan_count = self._cleanup_orphan_records(dry_run)
            records_deleted += orphan_count
            self.logger.info(f"Found and marked: {orphan_count} orphan records")
        except Exception as e:
            error_msg = f"Error cleaning orphan records: {str(e)}"
            self.logger.error(error_msg)
            errors.append(error_msg)
        
        # 2. Eliminar registros antiguos con status='failed'
        self.logger.info("Checking old failed records...")
        try:
            old_failed = self._cleanup_old_failed_records(max_age_hours, dry_run)
            records_deleted += old_failed
            self.logger.info(f"Deleted: {old_failed} old failed records")
        except Exception as e:
            error_msg = f"Error cleaning old failed records: {str(e)}"
            self.logger.error(error_msg)
            errors.append(error_msg)
        
        duration = time.time() - start_time
        self.logger.info(f"Total records processed: {records_deleted}")
        self.logger.info("")
        
        return CleanupStats(
            target=CleanupTarget.DATABASE.value,
            files_deleted=records_deleted,
            space_freed_bytes=0,
            space_freed_mb=0.0,
            duration_seconds=round(duration, 2),
            timestamp=DateTimeHelper.now_iso(),
            dry_run=dry_run,
            errors=errors
        )
    
    def get_storage_stats(self) -> StorageStats:
        """
        Obtiene estadísticas de almacenamiento del servidor.
        
        Returns:
            StorageStats con información actual
        """
        downloads_size = self._get_dir_size(settings.DOWNLOAD_DIR) if settings.DOWNLOAD_DIR.exists() else 0
        downloads_count = len(list(settings.DOWNLOAD_DIR.rglob("*"))) if settings.DOWNLOAD_DIR.exists() else 0
        
        logs_size = self._get_dir_size(settings.LOGS_DIR) if settings.LOGS_DIR.exists() else 0
        logs_count = len([d for d in settings.LOGS_DIR.rglob("*") if d.is_dir()]) if settings.LOGS_DIR.exists() else 0
        
        metadata_size = self._get_dir_size(settings.META_DIR) if settings.META_DIR.exists() else 0
        metadata_count = len(list(settings.META_DIR.glob("meta-*.json"))) if settings.META_DIR.exists() else 0
        
        temp_size = self._get_dir_size(settings.TMP_DIR) if settings.TMP_DIR.exists() else 0
        
        db_path = settings.BASE_DIR / "app" / "storage" / "downloads.db"
        db_size = db_path.stat().st_size if db_path.exists() else 0
        
        # Contar registros en BD
        try:
            db_record_count = self.download_index._get_total_records()
        except:
            db_record_count = 0
        
        return StorageStats(
            downloads_size_mb=round(downloads_size / (1024 * 1024), 2),
            downloads_file_count=downloads_count,
            logs_size_mb=round(logs_size / (1024 * 1024), 2),
            logs_dir_count=logs_count,
            metadata_size_mb=round(metadata_size / (1024 * 1024), 3),
            metadata_file_count=metadata_count,
            temp_size_mb=round(temp_size / (1024 * 1024), 2),
            total_size_mb=round((downloads_size + logs_size + metadata_size + temp_size + db_size) / (1024 * 1024), 2),
            database_size_mb=round(db_size / (1024 * 1024), 3),
            db_record_count=db_record_count,
            timestamp=DateTimeHelper.now_iso()
        )
    
    # === Métodos privados ===
    
    def _get_files_by_age(self, files: List[Path], max_age_hours: float) -> List[Path]:
        """Filtra archivos por edad."""
        eligible = []
        for file_path in files:
            age_hours = self._get_file_age_hours(file_path)
            if age_hours > max_age_hours:
                eligible.append(file_path)
        return eligible
    
    def _get_file_age_hours(self, file_path: Path) -> float:
        """Obtiene la edad de un archivo en horas."""
        mtime = file_path.stat().st_mtime
        now = time.time()
        age_seconds = now - mtime
        return age_seconds / 3600
    
    def _get_dir_age_hours(self, dir_path: Path) -> float:
        """Obtiene la edad de un directorio en horas (basado en mtime)."""
        mtime = dir_path.stat().st_mtime
        now = time.time()
        age_seconds = now - mtime
        return age_seconds / 3600
    
    def _get_age_from_timestamp(self, timestamp_str: str) -> float:
        """Calcula edad en horas desde un timestamp ISO."""
        try:
            created = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(created.tzinfo) if created.tzinfo else datetime.now()
            age = now - created
            return age.total_seconds() / 3600
        except:
            return 0.0
    
    def _get_dir_size(self, dir_path: Path) -> int:
        """Calcula el tamaño total de un directorio en bytes."""
        total_size = 0
        try:
            for item in dir_path.rglob("*"):
                if item.is_file():
                    total_size += item.stat().st_size
        except:
            pass
        return total_size
    
    def _cleanup_orphan_records(self, dry_run: bool) -> int:
        """Limpia registros sin archivos físicos."""
        orphan_count = 0
        
        try:
            # Obtener registros con status='ready'
            entries = self.download_index.get_all_ready_entries()
            
            for entry in entries:
                # Verificar si los archivos existen
                missing_files = []
                for file_path_str in entry.files:
                    file_path = Path(file_path_str)
                    if not file_path.exists():
                        missing_files.append(file_path_str)
                
                if missing_files:
                    self.logger.info(f"Orphan record: {entry.url} (missing: {len(missing_files)} files)")
                    
                    if not dry_run:
                        # Marcar como fallido en lugar de eliminar
                        self.download_index._mark_as_failed(
                            entry.url,
                            entry.type,
                            entry.quality,
                            entry.format,
                            f"missing_files: {missing_files}"
                        )
                    orphan_count += 1
        except Exception as e:
            self.logger.error(f"Error in orphan cleanup: {str(e)}")
        
        return orphan_count
    
    def _cleanup_old_failed_records(self, max_age_hours: float, dry_run: bool) -> int:
        """Elimina registros con status='failed' antiguos."""
        deleted_count = 0
        
        try:
            old_failed = self.download_index.get_old_failed_entries(max_age_hours)
            
            for entry in old_failed:
                self.logger.info(f"Old failed record: {entry.url} (error: {entry.error})")
                
                if not dry_run:
                    self.download_index.delete_entry(
                        entry.url,
                        entry.type,
                        entry.quality,
                        entry.format
                    )
                deleted_count += 1
        except Exception as e:
            self.logger.error(f"Error cleaning old failed records: {str(e)}")
        
        return deleted_count


# Instancia global del servicio
cleanup_service = CleanupService()
