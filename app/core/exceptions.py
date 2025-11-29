"""
Excepciones personalizadas de la aplicación.
Proporciona excepciones específicas del dominio para mejor manejo de errores.
Todas las excepciones incluyen un mensaje descriptivo accesible.
"""


class SnapLoadException(Exception):
    """Excepción base para todas las excepciones de SnapLoad."""
    
    def __init__(self, message: str, details: str = None):
        """
        Args:
            message: Mensaje principal del error
            details: Detalles adicionales opcionales
        """
        self.message = message
        self.details = details
        full_message = f"{message}"
        if details:
            full_message += f" - {details}"
        super().__init__(full_message)


class InvalidURLException(SnapLoadException):
    """Se lanza cuando una URL no es válida o no está soportada."""
    
    def __init__(self, url: str = None, reason: str = None):
        message = "URL inválida o no soportada"
        details = []
        if url:
            details.append(f"URL: {url}")
        if reason:
            details.append(reason)
        super().__init__(message, " | ".join(details) if details else None)


class InvalidQualityException(SnapLoadException):
    """Se lanza cuando la calidad especificada no es válida."""
    
    def __init__(self, quality: str = None, reason: str = None):
        message = "Calidad de audio inválida"
        details = []
        if quality:
            details.append(f"Calidad recibida: {quality}")
        if reason:
            details.append(reason)
        else:
            details.append("Use valores como '128k', '192k', '320k', 'bestaudio' o '0'")
        super().__init__(message, " | ".join(details) if details else None)


class InvalidFormatException(SnapLoadException):
    """Se lanza cuando el formato especificado no es válido."""
    
    def __init__(self, format_value: str = None, valid_formats: list = None):
        message = "Formato de video inválido"
        details = []
        if format_value:
            details.append(f"Formato recibido: {format_value}")
        if valid_formats:
            details.append(f"Formatos válidos: {', '.join(valid_formats)}")
        else:
            details.append("Formatos válidos: webm, mp4, mkv, mov, avi")
        super().__init__(message, " | ".join(details) if details else None)


class JobNotFoundException(SnapLoadException):
    """Se lanza cuando no se encuentra un job."""
    
    def __init__(self, job_id: str = None):
        message = "Job no encontrado"
        details = f"Job ID: {job_id}" if job_id else None
        super().__init__(message, details)


class FileNotFoundException(SnapLoadException):
    """Se lanza cuando no se encuentra un archivo esperado."""
    
    def __init__(self, filename: str = None, path: str = None, context: str = None):
        message = "Archivo no encontrado"
        details = []
        if filename:
            details.append(f"Archivo: {filename}")
        if path:
            details.append(f"Ruta: {path}")
        if context:
            details.append(context)
        super().__init__(message, " | ".join(details) if details else None)


class DownloadFailedException(SnapLoadException):
    """Se lanza cuando una descarga falla."""
    
    def __init__(self, url: str = None, reason: str = None, exit_code: int = None):
        message = "Descarga fallida"
        details = []
        if url:
            details.append(f"URL: {url}")
        if reason:
            details.append(f"Razón: {reason}")
        if exit_code is not None:
            details.append(f"Código de salida: {exit_code}")
        super().__init__(message, " | ".join(details) if details else None)


class ProcessExecutionException(SnapLoadException):
    """Se lanza cuando hay un error ejecutando un proceso externo."""
    
    def __init__(self, command: str = None, exit_code: int = None, stderr: str = None):
        message = "Error al ejecutar proceso externo"
        details = []
        if command:
            details.append(f"Comando: {command}")
        if exit_code is not None:
            details.append(f"Código de salida: {exit_code}")
        if stderr:
            # Limitar stderr a 200 caracteres para evitar mensajes muy largos
            stderr_preview = stderr[:200] + "..." if len(stderr) > 200 else stderr
            details.append(f"Error: {stderr_preview}")
        super().__init__(message, " | ".join(details) if details else None)
