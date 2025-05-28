"""
Entidades del dominio - Core business logic
Representan los conceptos fundamentales del negocio
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4


class DocumentType(Enum):
    """Tipos de documentos financieros"""
    QUARTERLY_REPORT = "quarterly_report"
    ANNUAL_REPORT = "annual_report"
    INTERIM_REPORT = "interim_report"
    PRESS_RELEASE = "press_release"
    PRESENTATION = "presentation"
    UNKNOWN = "unknown"


class ExtractionStatus(Enum):
    """Estados del proceso de extracción"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class Quarter(Enum):
    """Trimestres del año"""
    Q1 = 1
    Q2 = 2
    Q3 = 3
    Q4 = 4


@dataclass
class FinancialDocument:
    """
    Entidad principal - Documento financiero
    Representa un documento financiero con todos sus metadatos y estado
    """
    # Identificadores únicos
    id: UUID = field(default_factory=uuid4)
    
    # Información básica del documento
    url: str = ""
    title: str = ""
    document_type: DocumentType = DocumentType.UNKNOWN
    
    # Información temporal
    year: int = 0
    quarter: Optional[Quarter] = None
    publication_date: Optional[datetime] = None
    
    # Información de archivo
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_hash: Optional[str] = None
    original_filename: Optional[str] = None
    
    # Estado del procesamiento
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Información de calidad y validación
    validation_score: float = 0.0
    confidence_level: float = 0.0
    error_messages: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    
    # Metadatos adicionales
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validaciones y configuraciones post-inicialización"""
        self.updated_at = datetime.utcnow()
        
        # Validar año
        if self.year < 1900 or self.year > datetime.now().year + 1:
            raise ValueError(f"Año inválido: {self.year}")
        
        # Validar URL
        if self.url and not (self.url.startswith('http://') or self.url.startswith('https://')):
            raise ValueError(f"URL inválida: {self.url}")
    
    def mark_as_downloaded(self, file_path: str, file_size: int, file_hash: str) -> None:
        """Marca el documento como descargado exitosamente"""
        self.file_path = file_path
        self.file_size_bytes = file_size
        self.file_hash = file_hash
        self.extraction_status = ExtractionStatus.PROCESSING
        self.updated_at = datetime.utcnow()
    
    def mark_as_completed(self, validation_score: float, confidence_level: float) -> None:
        """Marca el documento como procesado exitosamente"""
        self.validation_score = validation_score
        self.confidence_level = confidence_level
        self.extraction_status = ExtractionStatus.COMPLETED
        self.updated_at = datetime.utcnow()
    
    def mark_as_failed(self, error_message: str) -> None:
        """Marca el documento como fallido"""
        self.error_messages.append(error_message)
        self.retry_count += 1
        
        if self.retry_count >= self.max_retries:
            self.extraction_status = ExtractionStatus.FAILED
        else:
            self.extraction_status = ExtractionStatus.RETRY
        
        self.updated_at = datetime.utcnow()
    
    def can_retry(self) -> bool:
        """Verifica si el documento puede ser reintentado"""
        return (
            self.extraction_status == ExtractionStatus.RETRY 
            and self.retry_count < self.max_retries
        )
    
    def is_quarterly(self) -> bool:
        """Verifica si es un reporte trimestral"""
        return self.quarter is not None and self.document_type == DocumentType.QUARTERLY_REPORT
    
    def is_annual(self) -> bool:
        """Verifica si es un reporte anual"""
        return self.document_type == DocumentType.ANNUAL_REPORT
    
    def get_period_identifier(self) -> str:
        """Obtiene el identificador del período (e.g., '2023-Q3', '2023-Annual')"""
        if self.is_quarterly():
            return f"{self.year}-{self.quarter.name}"
        elif self.is_annual():
            return f"{self.year}-Annual"
        else:
            return f"{self.year}-{self.document_type.value}"


@dataclass
class ExtractionJob:
    """
    Entidad para trabajos de extracción
    Representa un trabajo completo de extracción de múltiples documentos
    """
    # Identificadores
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    
    # Parámetros del trabajo
    company_url: str = ""
    target_years: List[int] = field(default_factory=list)
    document_types: List[DocumentType] = field(default_factory=list)
    
    # Estado del trabajo
    status: str = "created"  # created, running, completed, failed
    progress_percentage: float = 0.0
    
    # Documentos asociados
    document_ids: List[UUID] = field(default_factory=list)
    
    # Métricas del trabajo
    total_documents_found: int = 0
    documents_processed: int = 0
    documents_successful: int = 0
    documents_failed: int = 0
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Configuración
    configuration: Dict[str, Any] = field(default_factory=dict)
    
    def start_job(self) -> None:
        """Inicia el trabajo de extracción"""
        self.status = "running"
        self.started_at = datetime.utcnow()
        self.progress_percentage = 0.0
    
    def complete_job(self) -> None:
        """Completa el trabajo de extracción"""
        self.status = "completed"
        self.completed_at = datetime.utcnow()
        self.progress_percentage = 100.0
    
    def fail_job(self, error_message: str) -> None:
        """Marca el trabajo como fallido"""
        self.status = "failed"
        self.completed_at = datetime.utcnow()
        if 'errors' not in self.configuration:
            self.configuration['errors'] = []
        self.configuration['errors'].append(error_message)
    
    def update_progress(self) -> None:
        """Actualiza el progreso basado en los documentos procesados"""
        if self.total_documents_found > 0:
            self.progress_percentage = (
                self.documents_processed / self.total_documents_found * 100
            )
    
    def add_document(self, document_id: UUID) -> None:
        """Añade un documento al trabajo"""
        if document_id not in self.document_ids:
            self.document_ids.append(document_id)
            self.total_documents_found = len(self.document_ids)
    
    def record_document_processed(self, success: bool) -> None:
        """Registra un documento como procesado"""
        self.documents_processed += 1
        if success:
            self.documents_successful += 1
        else:
            self.documents_failed += 1
        self.update_progress()
    
    def get_success_rate(self) -> float:
        """Calcula la tasa de éxito del trabajo"""
        if self.documents_processed == 0:
            return 0.0
        return self.documents_successful / self.documents_processed * 100
    
    def get_duration_seconds(self) -> Optional[float]:
        """Obtiene la duración del trabajo en segundos"""
        if not self.started_at:
            return None
        
        end_time = self.completed_at or datetime.utcnow()
        return (end_time - self.started_at).total_seconds()


@dataclass
class CompanyProfile:
    """
    Entidad para perfiles de empresas
    Mantiene información sobre las empresas y sus patrones de reportes
    """
    # Identificadores
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    ticker_symbol: Optional[str] = None
    
    # URLs y configuración
    base_url: str = ""
    reports_url: str = ""
    
    # Patrones de scraping aprendidos
    url_patterns: Dict[str, str] = field(default_factory=dict)
    css_selectors: Dict[str, str] = field(default_factory=dict)
    
    # Información de la empresa
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    
    # Configuración de scraping
    scraping_config: Dict[str, Any] = field(default_factory=dict)
    
    # Historial y estadísticas
    last_scraped_at: Optional[datetime] = None
    total_documents_found: int = 0
    scraping_success_rate: float = 0.0
    
    # Metadatos
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def update_scraping_patterns(self, new_patterns: Dict[str, str]) -> None:
        """Actualiza los patrones de scraping aprendidos"""
        self.url_patterns.update(new_patterns.get('url_patterns', {}))
        self.css_selectors.update(new_patterns.get('css_selectors', {}))
        self.updated_at = datetime.utcnow()
    
    def record_scraping_attempt(self, success: bool, documents_found: int = 0) -> None:
        """Registra un intento de scraping"""
        self.last_scraped_at = datetime.utcnow()
        self.total_documents_found += documents_found
        
        # Actualizar tasa de éxito (promedio móvil simple)
        if success:
            self.scraping_success_rate = (self.scraping_success_rate + 100) / 2
        else:
            self.scraping_success_rate = self.scraping_success_rate / 2