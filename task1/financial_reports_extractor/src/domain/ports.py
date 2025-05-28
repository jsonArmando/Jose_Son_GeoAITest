"""
Puertos (Interfaces) del dominio
Definen los contratos que deben cumplir las implementaciones externas
Arquitectura Hexagonal - Dependency Inversion Principle
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, AsyncIterator
from uuid import UUID

from .entities import FinancialDocument, ExtractionJob, CompanyProfile
from .value_objects import (
    FinancialMetrics, 
    ValidationResult, 
    ScrapingConfiguration,
    AIExtractionConfiguration,
    ExtractionContext
)


# ==================== REPOSITORY PORTS ====================

class FinancialDocumentRepository(ABC):
    """Puerto para repositorio de documentos financieros"""
    
    @abstractmethod
    async def save(self, document: FinancialDocument) -> None:
        """Guarda un documento financiero"""
        pass
    
    @abstractmethod
    async def find_by_id(self, document_id: UUID) -> Optional[FinancialDocument]:
        """Busca un documento por ID"""
        pass
    
    @abstractmethod
    async def find_by_url(self, url: str) -> Optional[FinancialDocument]:
        """Busca un documento por URL"""
        pass
    
    @abstractmethod
    async def find_by_company_and_period(
        self, 
        company_name: str, 
        year: int, 
        quarter: Optional[int] = None
    ) -> List[FinancialDocument]:
        """Busca documentos por empresa y período"""
        pass
    
    @abstractmethod
    async def find_pending_processing(self, limit: int = 10) -> List[FinancialDocument]:
        """Busca documentos pendientes de procesamiento"""
        pass
    
    @abstractmethod
    async def find_failed_documents(self, limit: int = 10) -> List[FinancialDocument]:
        """Busca documentos que fallaron en el procesamiento"""
        pass
    
    @abstractmethod
    async def delete(self, document_id: UUID) -> None:
        """Elimina un documento"""
        pass
    
    @abstractmethod
    async def list_by_filters(
        self,
        company_name: Optional[str] = None,
        year: Optional[int] = None,
        document_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[FinancialDocument]:
        """Lista documentos con filtros"""
        pass


class ExtractionJobRepository(ABC):
    """Puerto para repositorio de trabajos de extracción"""
    
    @abstractmethod
    async def save(self, job: ExtractionJob) -> None:
        """Guarda un trabajo de extracción"""
        pass
    
    @abstractmethod
    async def find_by_id(self, job_id: UUID) -> Optional[ExtractionJob]:
        """Busca un trabajo por ID"""
        pass
    
    @abstractmethod
    async def find_active_jobs(self) -> List[ExtractionJob]:
        """Busca trabajos activos"""
        pass
    
    @abstractmethod
    async def find_completed_jobs(self, limit: int = 10) -> List[ExtractionJob]:
        """Busca trabajos completados"""
        pass


class CompanyProfileRepository(ABC):
    """Puerto para repositorio de perfiles de empresas"""
    
    @abstractmethod
    async def save(self, profile: CompanyProfile) -> None:
        """Guarda un perfil de empresa"""
        pass
    
    @abstractmethod
    async def find_by_name(self, name: str) -> Optional[CompanyProfile]:
        """Busca un perfil por nombre de empresa"""
        pass
    
    @abstractmethod
    async def find_by_base_url(self, base_url: str) -> Optional[CompanyProfile]:
        """Busca un perfil por URL base"""
        pass


# ==================== EXTERNAL SERVICE PORTS ====================

class WebScrapingPort(ABC):
    """Puerto para servicios de web scraping"""
    
    @abstractmethod
    async def discover_documents(
        self, 
        base_url: str, 
        config: ScrapingConfiguration
    ) -> List[Dict[str, Any]]:
        """
        Descubre documentos financieros en un sitio web
        Retorna lista de diccionarios con metadatos de documentos
        """
        pass
    
    @abstractmethod
    async def download_document(
        self, 
        url: str, 
        destination_path: str
    ) -> Dict[str, Any]:
        """
        Descarga un documento desde una URL
        Retorna información sobre el archivo descargado
        """
        pass
    
    @abstractmethod
    async def extract_document_metadata(
        self, 
        url: str
    ) -> Dict[str, Any]:
        """Extrae metadatos de un documento sin descargarlo"""
        pass
    
    @abstractmethod
    async def check_url_accessibility(self, url: str) -> bool:
        """Verifica si una URL es accesible"""
        pass


class AIExtractionPort(ABC):
    """Puerto para servicios de extracción con IA"""
    
    @abstractmethod
    async def extract_financial_data(
        self,
        file_path: str,
        context: ExtractionContext,
        config: AIExtractionConfiguration
    ) -> FinancialMetrics:
        """Extrae datos financieros de un documento usando IA"""
        pass
    
    @abstractmethod
    async def classify_document_type(
        self,
        file_path: str,
        config: AIExtractionConfiguration
    ) -> str:
        """Clasifica el tipo de documento usando IA"""
        pass
    
    @abstractmethod
    async def extract_text_content(
        self,
        file_path: str,
        config: AIExtractionConfiguration
    ) -> str:
        """Extrae contenido de texto de un documento"""
        pass
    
    @abstractmethod
    async def process_document_images(
        self,
        file_path: str,
        config: AIExtractionConfiguration
    ) -> List[Dict[str, Any]]:
        """Procesa imágenes dentro de un documento"""
        pass


class ValidationPort(ABC):
    """Puerto para servicios de validación de datos"""
    
    @abstractmethod
    async def validate_financial_metrics(
        self,
        metrics: FinancialMetrics,
        context: ExtractionContext
    ) -> ValidationResult:
        """Valida métricas financieras extraídas"""
        pass
    
    @abstractmethod
    async def validate_document_consistency(
        self,
        document: FinancialDocument,
        metrics: FinancialMetrics
    ) -> ValidationResult:
        """Valida consistencia entre documento y métricas"""
        pass
    
    @abstractmethod
    async def cross_validate_with_external_sources(
        self,
        metrics: FinancialMetrics,
        company_name: str,
        period: str
    ) -> ValidationResult:
        """Validación cruzada con fuentes externas"""
        pass


# ==================== STORAGE PORTS ====================

class FileStoragePort(ABC):
    """Puerto para almacenamiento de archivos"""
    
    @abstractmethod
    async def store_file(
        self,
        file_path: str,
        content: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Almacena un archivo y retorna la ruta de almacenamiento"""
        pass
    
    @abstractmethod
    async def retrieve_file(self, file_path: str) -> bytes:
        """Recupera un archivo almacenado"""
        pass
    
    @abstractmethod
    async def delete_file(self, file_path: str) -> None:
        """Elimina un archivo almacenado"""
        pass
    
    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """Verifica si un archivo existe"""
        pass
    
    @abstractmethod
    async def get_file_metadata(self, file_path: str) -> Dict[str, Any]:
        """Obtiene metadatos de un archivo"""
        pass
    
    @abstractmethod
    async def list_files(
        self,
        prefix: Optional[str] = None,
        limit: int = 100
    ) -> List[str]:
        """Lista archivos almacenados"""
        pass


class CachePort(ABC):
    """Puerto para servicios de caché"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor del caché"""
        pass
    
    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        expiration_seconds: Optional[int] = None
    ) -> None:
        """Almacena un valor en el caché"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Elimina un valor del caché"""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Verifica si una clave existe en el caché"""
        pass
    
    @abstractmethod
    async def clear_pattern(self, pattern: str) -> int:
        """Elimina claves que coincidan con un patrón"""
        pass


# ==================== MESSAGING PORTS ====================

class EventPublisherPort(ABC):
    """Puerto para publicación de eventos"""
    
    @abstractmethod
    async def publish_document_discovered(
        self,
        document: FinancialDocument
    ) -> None:
        """Publica evento de documento descubierto"""
        pass
    
    @abstractmethod
    async def publish_document_downloaded(
        self,
        document: FinancialDocument
    ) -> None:
        """Publica evento de documento descargado"""
        pass
    
    @abstractmethod
    async def publish_extraction_completed(
        self,
        document: FinancialDocument,
        metrics: FinancialMetrics
    ) -> None:
        """Publica evento de extracción completada"""
        pass
    
    @abstractmethod
    async def publish_extraction_failed(
        self,
        document: FinancialDocument,
        error: str
    ) -> None:
        """Publica evento de extracción fallida"""
        pass
    
    @abstractmethod
    async def publish_job_status_changed(
        self,
        job: ExtractionJob
    ) -> None:
        """Publica evento de cambio de estado de trabajo"""
        pass


class NotificationPort(ABC):
    """Puerto para servicios de notificación"""
    
    @abstractmethod
    async def send_email_notification(
        self,
        recipient: str,
        subject: str,
        body: str,
        attachments: Optional[List[str]] = None
    ) -> None:
        """Envía notificación por email"""
        pass
    
    @abstractmethod
    async def send_webhook_notification(
        self,
        webhook_url: str,
        payload: Dict[str, Any]
    ) -> None:
        """Envía notificación por webhook"""
        pass
    
    @abstractmethod
    async def send_slack_notification(
        self,
        channel: str,
        message: str
    ) -> None:
        """Envía notificación a Slack"""
        pass


# ==================== MONITORING PORTS ====================

class MetricsPort(ABC):
    """Puerto para métricas y monitoreo"""
    
    @abstractmethod
    async def record_document_processed(
        self,
        success: bool,
        processing_time_seconds: float,
        document_type: str
    ) -> None:
        """Registra métricas de procesamiento de documento"""
        pass
    
    @abstractmethod
    async def record_extraction_accuracy(
        self,
        accuracy_score: float,
        confidence_score: float,
        company_name: str
    ) -> None:
        """Registra métricas de precisión de extracción"""
        pass
    
    @abstractmethod
    async def record_api_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: int
    ) -> None:
        """Registra métricas de API"""
        pass
    
    @abstractmethod
    async def increment_counter(self, counter_name: str, labels: Dict[str, str]) -> None:
        """Incrementa un contador con labels"""
        pass
    
    @abstractmethod
    async def record_histogram(
        self,
        histogram_name: str,
        value: float,
        labels: Dict[str, str]
    ) -> None:
        """Registra un valor en histograma"""
        pass


class LoggingPort(ABC):
    """Puerto para logging estructurado"""
    
    @abstractmethod
    async def log_info(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log de información"""
        pass
    
    @abstractmethod
    async def log_warning(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log de advertencia"""
        pass
    
    @abstractmethod
    async def log_error(
        self,
        message: str,
        error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log de error"""
        pass
    
    @abstractmethod
    async def log_audit(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log de auditoría"""
        pass


# ==================== CONFIGURATION PORTS ====================

class ConfigurationPort(ABC):
    """Puerto para configuración de la aplicación"""
    
    @abstractmethod
    async def get_scraping_config(self, company_name: str) -> ScrapingConfiguration:
        """Obtiene configuración de scraping para una empresa"""
        pass
    
    @abstractmethod
    async def get_ai_config(self) -> AIExtractionConfiguration:
        """Obtiene configuración de IA"""
        pass
    
    @abstractmethod
    async def get_validation_config(self) -> Dict[str, Any]:
        """Obtiene configuración de validación"""
        pass
    
    @abstractmethod
    async def update_company_config(
        self,
        company_name: str,
        config: Dict[str, Any]
    ) -> None:
        """Actualiza configuración de empresa"""
        pass