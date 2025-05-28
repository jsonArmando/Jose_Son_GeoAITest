"""
Modelos SQLAlchemy para persistencia
Representación de las tablas de base de datos
"""

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, JSON, Boolean, 
    ForeignKey, ARRAY, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid


Base = declarative_base()


class FinancialDocumentModel(Base):
    """Modelo para documentos financieros"""
    __tablename__ = "financial_documents"
    
    # Campos principales
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(String(1000), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    document_type = Column(String(50), nullable=False, index=True)
    
    # Información temporal
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=True, index=True)
    publication_date = Column(DateTime, nullable=True)
    
    # Información de archivo
    file_path = Column(String(1000), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    file_hash = Column(String(64), nullable=True, index=True)
    original_filename = Column(String(255), nullable=True)
    
    # Estado del procesamiento
    extraction_status = Column(String(50), nullable=False, default='pending', index=True)
    validation_score = Column(Float, nullable=False, default=0.0)
    confidence_level = Column(Float, nullable=False, default=0.0)
    
    # Manejo de errores y reintentos
    error_messages = Column(JSONB, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    
    # Metadatos y etiquetas
    metadata = Column(JSONB, nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    financial_metrics = relationship("FinancialMetricsModel", back_populates="document", cascade="all, delete-orphan")
    
    # Índices compuestos
    __table_args__ = (
        Index('ix_doc_company_year', 'year', 'extraction_status'),
        Index('ix_doc_type_status', 'document_type', 'extraction_status'),
        Index('ix_doc_url_hash', 'url', 'file_hash'),
        UniqueConstraint('url', name='uq_document_url'),
    )


class FinancialMetricsModel(Base):
    """Modelo para métricas financieras extraídas"""
    __tablename__ = "financial_metrics"
    
    # Campos principales
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('financial_documents.id'), nullable=False, index=True)
    
    # Métricas de ingresos (en centavos para evitar problemas de precisión)
    revenue_cents = Column(Integer, nullable=True)
    gross_revenue_cents = Column(Integer, nullable=True)
    net_revenue_cents = Column(Integer, nullable=True)
    
    # Métricas de rentabilidad
    net_income_cents = Column(Integer, nullable=True)
    gross_profit_cents = Column(Integer, nullable=True)
    operating_income_cents = Column(Integer, nullable=True)
    ebitda_cents = Column(Integer, nullable=True)
    ebit_cents = Column(Integer, nullable=True)
    
    # Métricas de balance
    total_assets_cents = Column(Integer, nullable=True)
    total_liabilities_cents = Column(Integer, nullable=True)
    shareholders_equity_cents = Column(Integer, nullable=True)
    cash_and_equivalents_cents = Column(Integer, nullable=True)
    
    # Métricas de flujo de caja
    operating_cash_flow_cents = Column(Integer, nullable=True)
    investing_cash_flow_cents = Column(Integer, nullable=True)
    financing_cash_flow_cents = Column(Integer, nullable=True)
    free_cash_flow_cents = Column(Integer, nullable=True)
    
    # Métricas por acción (en centavos)
    earnings_per_share_cents = Column(Integer, nullable=True)
    book_value_per_share_cents = Column(Integer, nullable=True)
    dividends_per_share_cents = Column(Integer, nullable=True)
    
    # Ratios financieros (multiplicados por 10000 para evitar decimales)
    debt_to_equity_ratio_scaled = Column(Integer, nullable=True)
    current_ratio_scaled = Column(Integer, nullable=True)
    return_on_equity_scaled = Column(Integer, nullable=True)
    return_on_assets_scaled = Column(Integer, nullable=True)
    
    # Metadatos de extracción
    extraction_confidence = Column(Float, nullable=False, default=0.0)
    extraction_method = Column(String(100), nullable=False, default='unknown')
    source_page_numbers = Column(ARRAY(Integer), nullable=True)
    extraction_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Información contextual
    currency = Column(String(3), nullable=False, default='USD')
    reporting_period = Column(String(50), nullable=True)
    fiscal_year_end = Column(String(50), nullable=True)
    
    # Relaciones
    document = relationship("FinancialDocumentModel", back_populates="financial_metrics")
    
    # Índices
    __table_args__ = (
        Index('ix_metrics_document', 'document_id'),
        Index('ix_metrics_extraction', 'extraction_timestamp', 'extraction_confidence'),
    )


class ExtractionJobModel(Base):
    """Modelo para trabajos de extracción"""
    __tablename__ = "extraction_jobs"
    
    # Campos principales
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    
    # Parámetros del trabajo
    company_url = Column(String(1000), nullable=False)
    target_years = Column(ARRAY(Integer), nullable=True)
    document_types = Column(ARRAY(String), nullable=True)
    
    # Estado del trabajo
    status = Column(String(50), nullable=False, default='created', index=True)
    progress_percentage = Column(Float, nullable=False, default=0.0)
    
    # Documentos asociados
    document_ids = Column(ARRAY(String), nullable=True)
    
    # Métricas del trabajo
    total_documents_found = Column(Integer, nullable=False, default=0)
    documents_processed = Column(Integer, nullable=False, default=0)
    documents_successful = Column(Integer, nullable=False, default=0)
    documents_failed = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Configuración
    configuration = Column(JSONB, nullable=True)
    
    # Índices
    __table_args__ = (
        Index('ix_job_status_created', 'status', 'created_at'),
    )


class CompanyProfileModel(Base):
    """Modelo para perfiles de empresas"""
    __tablename__ = "company_profiles"
    
    # Campos principales
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    ticker_symbol = Column(String(10), nullable=True, index=True)
    
    # URLs y configuración
    base_url = Column(String(1000), nullable=False)
    reports_url = Column(String(1000), nullable=False)
    
    # Patrones de scraping aprendidos
    url_patterns = Column(JSONB, nullable=True)
    css_selectors = Column(JSONB, nullable=True)
    
    # Información de la empresa
    sector = Column(String(100), nullable=True, index=True)
    industry = Column(String(100), nullable=True, index=True)
    country = Column(String(100), nullable=True, index=True)
    
    # Configuración de scraping
    scraping_config = Column(JSONB, nullable=True)
    
    # Historial y estadísticas
    last_scraped_at = Column(DateTime, nullable=True)
    total_documents_found = Column(Integer, nullable=False, default=0)
    scraping_success_rate = Column(Float, nullable=False, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Índices
    __table_args__ = (
        Index('ix_company_sector_industry', 'sector', 'industry'),
    )


class ValidationResultModel(Base):
    """Modelo para resultados de validación"""
    __tablename__ = "validation_results"
    
    # Campos principales
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('financial_documents.id'), nullable=False, index=True)
    
    # Resultado principal
    is_valid = Column(Boolean, nullable=False, default=False)
    confidence_score = Column(Float, nullable=False, default=0.0)
    
    # Detalle de validaciones
    field_validations = Column(JSONB, nullable=True)
    validation_messages = Column(ARRAY(String), nullable=True)
    warnings = Column(ARRAY(String), nullable=True)
    errors = Column(ARRAY(String), nullable=True)
    
    # Información de contexto
    validation_method = Column(String(100), nullable=False, default='automated')
    validation_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    validator_version = Column(String(50), nullable=False, default='1.0.0')
    
    # Métricas de calidad
    accuracy_score = Column(Float, nullable=True)
    consistency_score = Column(Float, nullable=True)
    completeness_score = Column(Float, nullable=True)
    
    # Relaciones
    document = relationship("FinancialDocumentModel")
    
    # Índices
    __table_args__ = (
        Index('ix_validation_document', 'document_id'),
        Index('ix_validation_timestamp', 'validation_timestamp'),
        Index('ix_validation_scores', 'confidence_score', 'accuracy_score'),
    )


class ScrapingLogModel(Base):
    """Modelo para logs de scraping"""
    __tablename__ = "scraping_logs"
    
    # Campos principales
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_profile_id = Column(UUID(as_uuid=True), ForeignKey('company_profiles.id'), nullable=True, index=True)
    
    # Información del scraping
    target_url = Column(String(1000), nullable=False)
    scraping_method = Column(String(50), nullable=False)  # selenium, requests, etc.
    success = Column(Boolean, nullable=False, default=False)
    
    # Resultados
    documents_found = Column(Integer, nullable=False, default=0)
    pages_scraped = Column(Integer, nullable=False, default=0)
    duration_seconds = Column(Float, nullable=False, default=0.0)
    
    # Errores y warnings
    error_message = Column(Text, nullable=True)
    warnings = Column(ARRAY(String), nullable=True)
    
    # Configuración utilizada
    scraping_config = Column(JSONB, nullable=True)
    
    # Metadatos
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relaciones
    company_profile = relationship("CompanyProfileModel")
    
    # Índices
    __table_args__ = (
        Index('ix_scraping_company_date', 'company_profile_id', 'created_at'),
        Index('ix_scraping_success', 'success', 'created_at'),
    )


class AIProcessingLogModel(Base):
    """Modelo para logs de procesamiento con IA"""
    __tablename__ = "ai_processing_logs"
    
    # Campos principales
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('financial_documents.id'), nullable=False, index=True)
    
    # Información del modelo
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=True)
    processing_type = Column(String(50), nullable=False)  # extraction, classification, validation
    
    # Métricas de rendimiento
    tokens_used = Column(Integer, nullable=True)
    processing_time_seconds = Column(Float, nullable=False, default=0.0)
    cost_usd = Column(Float, nullable=True)
    
    # Configuración utilizada
    model_parameters = Column(JSONB, nullable=True)
    prompt_template = Column(Text, nullable=True)
    
    # Resultados
    success = Column(Boolean, nullable=False, default=False)
    confidence_score = Column(Float, nullable=True)
    raw_response = Column(Text, nullable=True)
    processed_response = Column(JSONB, nullable=True)
    
    # Errores
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relaciones
    document = relationship("FinancialDocumentModel")
    
    # Índices
    __table_args__ = (
        Index('ix_ai_processing_document', 'document_id'),
        Index('ix_ai_processing_model', 'model_name', 'processing_type'),
        Index('ix_ai_processing_performance', 'processing_time_seconds', 'tokens_used'),
    )


class SystemMetricsModel(Base):
    """Modelo para métricas del sistema"""
    __tablename__ = "system_metrics"
    
    # Campos principales
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Identificadores de la métrica
    metric_name = Column(String(100), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # counter, histogram, gauge
    
    # Valor de la métrica
    value = Column(Float, nullable=False)
    
    # Labels/tags para filtrado
    labels = Column(JSONB, nullable=True)
    
    # Timestamp
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Índices
    __table_args__ = (
        Index('ix_metrics_name_timestamp', 'metric_name', 'timestamp'),
        Index('ix_metrics_type', 'metric_type'),
    )


class CacheEntryModel(Base):
    """Modelo para entradas de caché persistente"""
    __tablename__ = "cache_entries"
    
    # Campos principales
    id = Column(String(255), primary_key=True)  # cache key
    
    # Datos
    value = Column(JSONB, nullable=False)
    value_type = Column(String(50), nullable=False)  # json, string, binary
    
    # Expiración
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    accessed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    access_count = Column(Integer, nullable=False, default=0)
    
    # Metadatos
    tags = Column(ARRAY(String), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    
    # Índices
    __table_args__ = (
        Index('ix_cache_expiration', 'expires_at'),
        Index('ix_cache_tags', 'tags'),
    )