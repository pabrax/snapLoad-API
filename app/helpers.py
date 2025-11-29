"""
Utilidades y helpers de la aplicación.
Funciones auxiliares para manejo de archivos, strings, fechas, etc.
"""
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List

from .core.config import settings


class DateTimeHelper:
    """Helper para manejo de fechas."""
    
    @staticmethod
    def now_iso() -> str:
        """
        Retorna la fecha/hora actual en formato ISO sin microsegundos.
        
        Returns:
            String en formato ISO (ej: "2024-01-01T12:00:00Z")
        """
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class FileNameHelper:
    """Helper para sanitización de nombres de archivos."""
    
    @staticmethod
    def sanitize_filename(name: str, max_length: int = None) -> str:
        """
        Sanitiza un nombre de fichero para evitar caracteres inválidos.
        
        - Normaliza Unicode (NFC)
        - Reemplaza barras y caracteres de control
        - Recorta a max_length caracteres
        
        Args:
            name: Nombre a sanitizar
            max_length: Longitud máxima (default desde settings)
            
        Returns:
            Nombre sanitizado
        """
        if not name:
            return ""
        
        if max_length is None:
            max_length = settings.MAX_FILENAME_LENGTH
        
        # Normalize
        name = unicodedata.normalize("NFC", name)
        
        # Replace path separators
        name = name.replace("/", "-").replace("\\", "-")
        
        # Remove control characters
        name = re.sub(r"[\x00-\x1f\x7f]+", "", name)
        
        # Collapse repeated spaces
        name = re.sub(r"\s+", " ", name).strip()
        
        if len(name) > max_length:
            name = name[:max_length]
        
        return name
    
    @staticmethod
    def sanitize_filename_ascii(name: str, max_length: int = None) -> str:
        """
        Genera una variante ASCII del nombre para uso en headers HTTP.
        
        - Normaliza NFKD y elimina marcas diacríticas
        - Sustituye caracteres no ASCII por '-'
        - Recorta longitud
        
        Args:
            name: Nombre a sanitizar
            max_length: Longitud máxima (default desde settings)
            
        Returns:
            Nombre en ASCII
        """
        if not name:
            return ""
        
        if max_length is None:
            max_length = settings.MAX_FILENAME_LENGTH
        
        raw = unicodedata.normalize("NFKD", name)
        out_chars = []
        
        for ch in raw:
            o = ord(ch)
            if o < 128:
                # Evitar caracteres de control
                if 32 <= o < 127:
                    out_chars.append(ch)
                continue
            
            # Reemplazos específicos
            if ch in {"：", "﹕"}:  # fullwidth colon variants
                out_chars.append(":")
                continue
            
            # Descarta diacríticos y otros -> '-'
            cat = unicodedata.category(ch)
            if cat.startswith("M"):
                # marca diacrítica ignorada
                continue
            out_chars.append("-")
        
        ascii_name = ''.join(out_chars)
        ascii_name = re.sub(r"[\s]+", " ", ascii_name).strip()
        
        if len(ascii_name) > max_length:
            ascii_name = ascii_name[:max_length]
        
        if not ascii_name:
            ascii_name = "file"
        
        return ascii_name
    
    @staticmethod
    def unique_path(path: Path) -> Path:
        """
        Retorna una ruta que no colisione agregando un contador si es necesario.
        
        Args:
            path: Ruta deseada
            
        Returns:
            Ruta única que no existe
        """
        candidate = path
        i = 1
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}-{i}{path.suffix}")
            i += 1
        return candidate


class FileSystemHelper:
    """Helper para operaciones del sistema de archivos."""
    
    @staticmethod
    def list_audio_files(folder: Path) -> List[Path]:
        """
        Lista todos los archivos de audio en una carpeta (recursivo).
        
        Args:
            folder: Carpeta a buscar
            
        Returns:
            Lista de rutas de archivos de audio
        """
        if not folder.exists():
            return []
        
        files = []
        for p in folder.rglob("*"):
            if p.is_file() and p.suffix.lower() in settings.AUDIO_EXTENSIONS:
                files.append(p)
        return files
    
    @staticmethod
    def list_video_files(folder: Path) -> List[Path]:
        """
        Lista todos los archivos de video en una carpeta (recursivo).
        
        Args:
            folder: Carpeta a buscar
            
        Returns:
            Lista de rutas de archivos de video
        """
        if not folder.exists():
            return []
        
        files = []
        for p in folder.rglob("*"):
            if p.is_file() and p.suffix.lower() in settings.VIDEO_EXTENSIONS:
                files.append(p)
        return files
    
    @staticmethod
    def list_media_files(folder: Path, media_type: str = "audio") -> List[Path]:
        """
        Lista archivos de media según el tipo.
        
        Args:
            folder: Carpeta a buscar
            media_type: "audio" o "video"
            
        Returns:
            Lista de rutas de archivos
        """
        if media_type == "audio":
            return FileSystemHelper.list_audio_files(folder)
        else:
            return FileSystemHelper.list_video_files(folder)


class TextHelper:
    """Helper para operaciones con texto."""
    
    @staticmethod
    def truncate_text(text: str, max_lines: int = None) -> str:
        """
        Trunca un texto manteniendo solo las últimas N líneas.
        
        Args:
            text: Texto a truncar
            max_lines: Número máximo de líneas (default desde settings)
            
        Returns:
            Texto truncado
        """
        if not text:
            return ""
        
        if max_lines is None:
            max_lines = settings.MAX_LOG_LINES
        
        lines = text.strip().splitlines()
        if len(lines) <= max_lines:
            return "\n".join(lines)
        return "\n".join(lines[-max_lines:])
