# app/core/schemas.py
from pydantic import BaseModel, Field, HttpUrl, ConfigDict # ESTA LÍNEA DEBE COMENZAR EN LA COLUMNA 1
from typing import List, Optional, Union, Dict, Any

# --- Modelos para la API (Peticiones y Respuestas) ---

class TriggerExtractionRequest(BaseModel):
    start_year: Optional[int] = Field(None, description="Año de inicio para la extracción (inclusivo)")
    end_year: Optional[int] = Field(None, description="Año de fin para la extracción (inclusivo)")

class TriggerExtractionResponse(BaseModel):
    message: str
    reports_identified_count: int
    report_urls_found: List[HttpUrl] = []

class MetricItem(BaseModel): 
    metric_name: str
    quarter_value: Optional[str] = None 
    ytd_value: Optional[str] = None

class ExtractedReportDataResponse(BaseModel):
    id: int 
    report_name: str
    report_url: HttpUrl 
    year: int
    quarter: str 
    extraction_status: str 
    accuracy_score: Optional[float] = Field(None, ge=0, le=100, description="Puntaje de precisión de la extracción (0-100)")
    operational_highlights: List[MetricItem] = []
    financial_highlights: List[MetricItem] = []
    raw_extracted_data: Optional[Dict[str, Any]] = Field(None, description="Datos brutos devueltos por el LLM antes de estandarizar")
    error_message: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class ReportSummaryItem(BaseModel):
    id: int
    report_name: str
    year: int
    quarter: str
    status: str
    accuracy: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True)

class AllReportsSummaryResponse(BaseModel):
    total_reports_in_db: int
    reports_processed_successfully: int
    reports_failed: int
    average_accuracy: Optional[float] = None
    reports: List[ReportSummaryItem] = []

# --- Modelos internos para el flujo de datos (Dominio) ---

class ReportDetails(BaseModel): 
    report_name: str
    report_url: HttpUrl 
    year: int
    quarter: str 

class LLMExtractionInput(BaseModel):
    pdf_content_text: str 

class LLMOperationalHighlight(BaseModel): 
    metric_name: str
    quarter_value: Union[str, int, float, None] = Field(default=None)
    ytd_value: Union[str, int, float, None] = Field(default=None)

class LLMFinancialHighlight(BaseModel): 
    metric_name: str
    quarter_value: Union[str, int, float, None] = Field(default=None)
    ytd_value: Union[str, int, float, None] = Field(default=None)

class LLMReportDetailsInferred(BaseModel): 
    year: Union[int, str, None] = Field(None, description="Año inferido por el LLM, puede ser string o int")
    quarter: Optional[str] = Field(None, description="Trimestre (Q1-Q4, FY) inferido por el LLM")

class LLMFullExtractionResult(BaseModel): 
    report_details_inferred: Optional[LLMReportDetailsInferred] = Field(None, description="Año y trimestre inferidos por el LLM")
    operational_highlights: List[LLMOperationalHighlight] = []
    financial_highlights: List[LLMFinancialHighlight] = []   
    llm_extraction_notes: Optional[str] = None

class StandardizedExtractionOutput(BaseModel):
    report_details: ReportDetails 
    operational_highlights: List[MetricItem] 
    financial_highlights: List[MetricItem] 
    accuracy_score: float
    raw_llm_output: Dict[str, Any] 

# --- Modelos para las tablas de visualización anual ---
class TableRow(BaseModel):
    metric_name: str
    q1_value: Optional[str] = None
    q2_value: Optional[str] = None
    q3_value: Optional[str] = None
    q4_value: Optional[str] = None
    annual_value: Optional[str] = None

class AnnualReportTableResponse(BaseModel):
    year: int
    operational_table: List[TableRow]
    financial_table: List[TableRow]

# --- Modelos Pydantic para validación de datos de la DB ---
class FinancialReportDBBase(BaseModel):
    report_name: str
    report_url: HttpUrl 
    year: int
    quarter: str
    extraction_status: str = "PENDING"
    accuracy_score: Optional[float] = None
    raw_extracted_data: Optional[Dict[str, Any]] = None 
    error_message: Optional[str] = None

class FinancialReportDBCreate(FinancialReportDBBase):
    pass

class FinancialReportDB(FinancialReportDBBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class MetricDBBase(BaseModel):
    report_id: int
    metric_name: str
    quarter_value: Optional[str] = None 
    year_to_date_value: Optional[str] = None

class MetricDBCreate(MetricDBBase):
    pass

class MetricDB(MetricDBBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
    