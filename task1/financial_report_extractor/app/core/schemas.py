# app/core/schemas.py
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Union, Dict, Any
import uuid # Para IDs únicos si es necesario

# --- Modelos para la API (Peticiones y Respuestas) ---

class TriggerExtractionRequest(BaseModel):
    """
    Modelo para la petición de inicio de extracción.
    Los años pueden ser opcionales si se toman de la configuración global.
    """
    start_year: Optional[int] = Field(None, description="Año de inicio para la extracción (inclusivo)")
    end_year: Optional[int] = Field(None, description="Año de fin para la extracción (inclusivo)")

class TriggerExtractionResponse(BaseModel):
    """
    Respuesta al iniciar la extracción.
    """
    message: str
    reports_identified_count: int
    report_urls_found: List[HttpUrl] = []

class MetricItem(BaseModel):
    """
    Representa una métrica individual extraída.
    """
    metric_name: str
    quarter_value: Union[str, float, None] = Field(description="Valor del trimestre. 'Not found' o numérico.")
    ytd_value: Union[str, float, None] = Field(description="Valor acumulado del año. 'Not found' o numérico.")

class ExtractedReportDataResponse(BaseModel):
    """
    Respuesta detallada de los datos extraídos para un informe.
    """
    id: int # ID del informe en la base de datos
    report_name: str
    report_url: HttpUrl
    year: int
    quarter: str # e.g., "Q1", "Q2", "Q3", "Q4", "FY" (Full Year)
    extraction_status: str # e.g., "SUCCESS", "PARTIAL_SUCCESS", "FAILED", "PENDING"
    accuracy_score: Optional[float] = Field(None, ge=0, le=100, description="Puntaje de precisión de la extracción (0-100)")
    operational_highlights: List[MetricItem] = []
    financial_highlights: List[MetricItem] = []
    raw_extracted_data: Optional[Dict[str, Any]] = Field(None, description="Datos brutos devueltos por el LLM antes de estandarizar")
    error_message: Optional[str] = None


class ReportSummaryItem(BaseModel):
    """
    Información resumida de un informe procesado.
    """
    id: int
    report_name: str
    year: int
    quarter: str
    status: str
    accuracy: Optional[float] = None

class AllReportsSummaryResponse(BaseModel):
    """
    Respuesta del resumen de todos los informes.
    """
    total_reports_in_db: int
    reports_processed_successfully: int
    reports_failed: int
    average_accuracy: Optional[float] = None
    reports: List[ReportSummaryItem] = []

# --- Modelos internos para el flujo de datos (Dominio) ---

class ReportDetails(BaseModel):
    """
    Detalles básicos de un informe identificado.
    """
    report_name: str
    report_url: HttpUrl
    year: int
    quarter: str # Q1, Q2, Q3, Q4, FY

class LLMExtractionInput(BaseModel):
    """
    Datos de entrada para el LLM extractor de métricas.
    """
    pdf_content_text: str # Texto extraído del PDF
    # Opcionalmente, podría incluir tablas estructuradas si el primer LLM las separa
    # tables_data: Optional[List[Dict[str, Any]]] = None

class LLMOperationalHighlight(BaseModel):
    metric_name: str
    quarter_value: str # El LLM devolverá string, luego se puede intentar convertir
    ytd_value: str

class LLMFinancialHighlight(BaseModel):
    metric_name: str
    quarter_value: str
    ytd_value: str

class LLMFullExtractionResult(BaseModel):
    """
    Estructura esperada de la respuesta del LLM para la extracción de métricas.
    """
    report_details: Optional[Dict[str, Union[int, str]]] = Field(None, description="Año y trimestre inferidos por el LLM")
    operational_highlights: List[LLMOperationalHighlight] = []
    financial_highlights: List[LLMFinancialHighlight] = []
    # Podríamos añadir un campo para que el LLM explique suposiciones o problemas
    llm_notes: Optional[str] = None
    # Podríamos pedir al LLM un score de confianza general
    llm_confidence_score: Optional[float] = Field(None, ge=0, le=1)

class StandardizedExtractionOutput(BaseModel):
    """
    Datos estandarizados después del procesamiento del LLM y validación.
    """
    report_details: ReportDetails
    operational_highlights: List[MetricItem]
    financial_highlights: List[MetricItem]
    accuracy_score: float
    raw_llm_output: Dict[str, Any] # Guardar la respuesta original del LLM para auditoría

# --- Modelos para la base de datos (se definirán como modelos SQLAlchemy, pero Pydantic puede usarse para validación) ---
# Estos son conceptuales aquí, los modelos SQLAlchemy estarán en db_adapter.py

class FinancialReportDBBase(BaseModel):
    report_name: str
    report_url: HttpUrl
    year: int
    quarter: str
    extraction_status: str = "PENDING"
    accuracy_score: Optional[float] = None
    raw_extracted_data: Optional[Dict[str, Any]] = None # JSONB en la DB
    error_message: Optional[str] = None

class FinancialReportDBCreate(FinancialReportDBBase):
    pass

class FinancialReportDB(FinancialReportDBBase):
    id: int
    # Timestamps podrían añadirse aquí (created_at, updated_at)

    class Config:
        orm_mode = True # Permite que Pydantic funcione con modelos SQLAlchemy

class MetricDBBase(BaseModel):
    report_id: int
    metric_name: str
    quarter_value: Optional[str] = None # Se guarda como texto para acomodar "Not found"
    year_to_date_value: Optional[str] = None

class MetricDBCreate(MetricDBBase):
    pass

class MetricDB(MetricDBBase):
    id: int
    is_annual_summary: bool = False # Podría ser útil para diferenciar

    class Config:
        orm_mode = True
