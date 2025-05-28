"""
Value Objects del dominio
Objetos inmutables que representan conceptos sin identidad
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime
import json


@dataclass(frozen=True)
class FinancialMetrics:
    """
    Value Object para métricas financieras extraídas
    Representa los datos financieros de un período específico
    """
    # Métricas de ingresos
    revenue: Optional[Decimal] = None
    gross_revenue: Optional[Decimal] = None
    net_revenue: Optional[Decimal] = None
    
    # Métricas de rentabilidad
    net_income: Optional[Decimal] = None
    gross_profit: Optional[Decimal] = None
    operating_income: Optional[Decimal] = None
    ebitda: Optional[Decimal] = None
    ebit: Optional[Decimal] = None
    
    # Métricas de balance
    total_assets: Optional[Decimal] = None
    total_liabilities: Optional[Decimal] = None
    shareholders_equity: Optional[Decimal] = None
    cash_and_equivalents: Optional[Decimal] = None
    
    # Métricas de flujo de caja
    operating_cash_flow: Optional[Decimal] = None
    investing_cash_flow: Optional[Decimal] = None
    financing_cash_flow: Optional[Decimal] = None
    free_cash_flow: Optional[Decimal] = None
    
    # Métricas por acción
    earnings_per_share: Optional[Decimal] = None
    book_value_per_share: Optional[Decimal] = None
    dividends_per_share: Optional[Decimal] = None
    
    # Ratios financieros
    debt_to_equity_ratio: Optional[Decimal] = None
    current_ratio: Optional[Decimal] = None
    return_on_equity: Optional[Decimal] = None
    return_on_assets: Optional[Decimal] = None
    
    # Metadatos de extracción
    extraction_confidence: float = 0.0
    extraction_method: str = "unknown"
    source_page_numbers: List[int] = field(default_factory=list)
    extraction_timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Información contextual
    currency: str = "USD"
    reporting_period: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    
    def __post_init__(self):
        """Validaciones post-inicialización"""
        # Validar que al menos una métrica esté presente
        financial_fields = [
            self.revenue, self.net_income, self.total_assets, 
            self.gross_profit, self.operating_income, self.ebitda
        ]
        
        if all(field is None for field in financial_fields):
            raise ValueError("Al menos una métrica financiera debe estar presente")
        
        # Validar confidence score
        if not 0.0 <= self.extraction_confidence <= 1.0:
            raise ValueError("Confidence score debe estar entre 0.0 y 1.0")
    
    def get_completeness_score(self) -> float:
        """Calcula el score de completitud de los datos"""
        total_fields = 20  # Número total de campos financieros importantes
        filled_fields = sum(1 for field in [
            self.revenue, self.net_income, self.total_assets, self.total_liabilities,
            self.shareholders_equity, self.cash_and_equivalents, self.operating_cash_flow,
            self.gross_profit, self.operating_income, self.ebitda, self.ebit,
            self.free_cash_flow, self.earnings_per_share, self.book_value_per_share,
            self.dividends_per_share, self.debt_to_equity_ratio, self.current_ratio,
            self.return_on_equity, self.return_on_assets, self.investing_cash_flow
        ] if field is not None)
        
        return filled_fields / total_fields
    
    def get_key_metrics(self) -> Dict[str, Optional[Decimal]]:
        """Obtiene las métricas clave más importantes"""
        return {
            'revenue': self.revenue,
            'net_income': self.net_income,
            'ebitda': self.ebitda,
            'total_assets': self.total_assets,
            'shareholders_equity': self.shareholders_equity,
            'operating_cash_flow': self.operating_cash_flow
        }
    
    def is_profitable(self) -> Optional[bool]:
        """Determina si la empresa fue rentable en el período"""
        if self.net_income is None:
            return None
        return self.net_income > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para serialización"""
        return {
            'revenue': float(self.revenue) if self.revenue else None,
            'net_income': float(self.net_income) if self.net_income else None,
            'ebitda': float(self.ebitda) if self.ebitda else None,
            'total_assets': float(self.total_assets) if self.total_assets else None,
            'extraction_confidence': self.extraction_confidence,
            'completeness_score': self.get_completeness_score(),
            'currency': self.currency,
            'reporting_period': self.reporting_period
        }


@dataclass(frozen=True)
class ValidationResult:
    """
    Value Object para resultados de validación
    Representa el resultado de validar datos extraídos
    """
    # Resultado principal
    is_valid: bool
    confidence_score: float  # 0.0 - 1.0
    
    # Detalle de validaciones
    field_validations: Dict[str, bool] = field(default_factory=dict)
    validation_messages: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    # Información de contexto
    validation_method: str = "automated"
    validation_timestamp: datetime = field(default_factory=datetime.utcnow)
    validator_version: str = "1.0.0"
    
    # Métricas de calidad
    accuracy_score: Optional[float] = None
    consistency_score: Optional[float] = None
    completeness_score: Optional[float] = None
    
    def __post_init__(self):
        """Validaciones post-inicialización"""
        if not 0.0 <= self.confidence_score <= 1.0:
            raise ValueError("Confidence score debe estar entre 0.0 y 1.0")
        
        if self.accuracy_score is not None and not 0.0 <= self.accuracy_score <= 1.0:
            raise ValueError("Accuracy score debe estar entre 0.0 y 1.0")
    
    def get_overall_quality_score(self) -> float:
        """Calcula un score general de calidad"""
        scores = [self.confidence_score]
        
        if self.accuracy_score is not None:
            scores.append(self.accuracy_score)
        if self.consistency_score is not None:
            scores.append(self.consistency_score)
        if self.completeness_score is not None:
            scores.append(self.completeness_score)
        
        return sum(scores) / len(scores)
    
    def has_critical_errors(self) -> bool:
        """Verifica si hay errores críticos"""
        critical_keywords = ['critical', 'fatal', 'invalid', 'corrupted']
        return any(
            any(keyword in error.lower() for keyword in critical_keywords)
            for error in self.errors
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """Obtiene un resumen del resultado de validación"""
        return {
            'is_valid': self.is_valid,
            'confidence_score': self.confidence_score,
            'overall_quality_score': self.get_overall_quality_score(),
            'total_errors': len(self.errors),
            'total_warnings': len(self.warnings),
            'has_critical_errors': self.has_critical_errors(),
            'validation_timestamp': self.validation_timestamp.isoformat()
        }


@dataclass(frozen=True)
class ScrapingConfiguration:
    """
    Value Object para configuración de scraping
    Define cómo debe realizarse el scraping de un sitio específico
    """
    # Configuración básica
    base_url: str
    max_pages: int = 10
    delay_between_requests: float = 1.0
    timeout_seconds: int = 30
    
    # Selectores CSS/XPath
    document_links_selector: str = ""
    title_selector: str = ""
    date_selector: str = ""
    type_selector: str = ""
    
    # Configuración del navegador
    use_headless: bool = True
    window_size: tuple = (1920, 1080)
    user_agent: str = "Mozilla/5.0 (compatible; FinancialExtractor/1.0)"
    
    # Patrones de filtrado
    url_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    file_extensions: List[str] = field(default_factory=lambda: ['pdf', 'doc', 'docx'])
    
    # Configuración de reintentos
    max_retries: int = 3
    retry_delay: float = 5.0
    retry_backoff_factor: float = 2.0
    
    # Headers HTTP
    custom_headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validaciones post-inicialización"""
        if not self.base_url.startswith(('http://', 'https://')):
            raise ValueError("base_url debe comenzar con http:// o https://")
        
        if self.max_pages < 1:
            raise ValueError("max_pages debe ser mayor a 0")
        
        if self.delay_between_requests < 0:
            raise ValueError("delay_between_requests no puede ser negativo")
    
    def get_selenium_options(self) -> Dict[str, Any]:
        """Obtiene las opciones para Selenium WebDriver"""
        return {
            'headless': self.use_headless,
            'window_size': self.window_size,
            'user_agent': self.user_agent,
            'timeout': self.timeout_seconds,
            'custom_headers': self.custom_headers
        }
    
    def should_process_url(self, url: str) -> bool:
        """Verifica si una URL debe ser procesada según los patrones"""
        # Verificar patrones de inclusión
        if self.url_patterns:
            include_match = any(pattern in url for pattern in self.url_patterns)
            if not include_match:
                return False
        
        # Verificar patrones de exclusión
        if self.exclude_patterns:
            exclude_match = any(pattern in url for pattern in self.exclude_patterns)
            if exclude_match:
                return False
        
        return True


@dataclass(frozen=True)
class AIExtractionConfiguration:
    """
    Value Object para configuración de extracción con IA
    Define cómo los modelos de IA deben extraer datos
    """
    # Configuración del modelo
    model_name: str = "gpt-4-turbo-preview"
    max_tokens: int = 4000
    temperature: float = 0.1
    
    # Prompts y templates
    extraction_prompt_template: str = ""
    validation_prompt_template: str = ""
    classification_prompt_template: str = ""
    
    # Configuración de procesamiento
    use_ocr: bool = True
    ocr_languages: List[str] = field(default_factory=lambda: ['eng', 'spa'])
    process_images: bool = True
    process_tables: bool = True
    
    # Configuración de validación
    enable_cross_validation: bool = True
    min_confidence_threshold: float = 0.7
    use_multiple_models: bool = False
    
    # Límites y restricciones
    max_file_size_mb: int = 100
    max_pages_per_document: int = 50
    
    # Configuración de caché
    cache_responses: bool = True
    cache_ttl_hours: int = 24
    
    def __post_init__(self):
        """Validaciones post-inicialización"""
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature debe estar entre 0.0 y 2.0")
        
        if not 0.0 <= self.min_confidence_threshold <= 1.0:
            raise ValueError("min_confidence_threshold debe estar entre 0.0 y 1.0")
        
        if self.max_tokens < 100:
            raise ValueError("max_tokens debe ser al menos 100")
    
    def get_model_parameters(self) -> Dict[str, Any]:
        """Obtiene los parámetros para el modelo de IA"""
        return {
            'model': self.model_name,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'response_format': {'type': 'json_object'}
        }
    
    def should_process_file(self, file_size_mb: float, page_count: int) -> bool:
        """Verifica si un archivo debe ser procesado según las restricciones"""
        return (
            file_size_mb <= self.max_file_size_mb and
            page_count <= self.max_pages_per_document
        )


@dataclass(frozen=True)
class ExtractionContext:
    """
    Value Object para contexto de extracción
    Proporciona información contextual para el proceso de extracción
    """
    # Información del documento
    document_type: str
    company_name: str
    reporting_period: str
    fiscal_year: int
    
    # Información de la fuente
    source_url: str
    file_path: str
    page_count: int
    file_size_bytes: int
    
    # Configuración específica
    target_metrics: List[str] = field(default_factory=list)
    expected_currency: str = "USD"
    
    # Información temporal
    extraction_timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def get_context_prompt(self) -> str:
        """Genera un prompt de contexto para el modelo de IA"""
        return f"""
        Contexto del documento:
        - Tipo: {self.document_type}
        - Empresa: {self.company_name}
        - Período: {self.reporting_period}
        - Año fiscal: {self.fiscal_year}
        - Moneda esperada: {self.expected_currency}
        - Métricas objetivo: {', '.join(self.target_metrics)}
        """
    
    def to_metadata(self) -> Dict[str, Any]:
        """Convierte a metadata para almacenamiento"""
        return {
            'document_type': self.document_type,
            'company_name': self.company_name,
            'reporting_period': self.reporting_period,
            'fiscal_year': self.fiscal_year,
            'source_url': self.source_url,
            'expected_currency': self.expected_currency,
            'target_metrics': self.target_metrics,
            'extraction_timestamp': self.extraction_timestamp.isoformat()
        }