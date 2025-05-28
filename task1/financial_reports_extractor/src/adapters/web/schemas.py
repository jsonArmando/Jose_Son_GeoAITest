"""
API Schemas - Pydantic models for request/response validation
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl, validator
from pydantic.types import NonNegativeInt, PositiveInt


# ==================== ENUMS ====================

class DocumentTypeEnum(str, Enum):
    """Document types enum for API"""
    QUARTERLY_REPORT = "quarterly_report"
    ANNUAL_REPORT = "annual_report"
    INTERIM_REPORT = "interim_report"
    PRESS_RELEASE = "press_release"
    PRESENTATION = "presentation"
    UNKNOWN = "unknown"


class ExtractionStatusEnum(str, Enum):
    """Extraction status enum for API"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class JobStatusEnum(str, Enum):
    """Job status enum for API"""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ==================== REQUEST MODELS ====================

class ExtractionJobRequest(BaseModel):
    """Request model for creating extraction jobs"""
    company_url: HttpUrl = Field(
        ..., 
        description="Base URL of the company's investor relations page",
        example="https://torexgold.com/investors/financial-reports/"
    )
    company_name: str = Field(
        ..., 
        min_length=2, 
        max_length=200,
        description="Name of the company",
        example="Torex Gold Resources Inc."
    )
    target_years: List[int] = Field(
        ..., 
        min_items=1,
        description="List of years to extract reports from",
        example=[2021, 2022, 2023, 2024]
    )
    document_types: Optional[List[DocumentTypeEnum]] = Field(
        None,
        description="Specific document types to extract (if empty, extracts all)",
        example=["quarterly_report", "annual_report"]
    )
    notify_webhook: Optional[HttpUrl] = Field(
        None,
        description="Webhook URL to notify when job completes"
    )
    job_name: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional name for the extraction job",
        example="Torex Gold Q4 2023 Extraction"
    )
    
    @validator('target_years')
    def validate_years(cls, v):
        current_year = datetime.now().year
        for year in v:
            if year < 2000 or year > current_year + 1:
                raise ValueError(f'Year {year} is outside valid range (2000-{current_year + 1})')
        return sorted(list(set(v)))  # Remove duplicates and sort
    
    class Config:
        schema_extra = {
            "example": {
                "company_url": "https://torexgold.com/investors/financial-reports/",
                "company_name": "Torex Gold Resources Inc.",
                "target_years": [2022, 2023, 2024],
                "document_types": ["quarterly_report", "annual_report"],
                "job_name": "Torex Gold Financial Reports Extraction"
            }
        }


class RetryExtractionRequest(BaseModel):
    """Request model for retrying failed extractions"""
    force_retry: bool = Field(
        False,
        description="Force retry even if max retries exceeded"
    )
    use_different_method: bool = Field(
        False,
        description="Try with different extraction method"
    )


class ScrapingConfigRequest(BaseModel):
    """Request model for updating scraping configuration"""
    max_pages: PositiveInt = Field(10, le=100, description="Maximum pages to scrape")
    delay_between_requests: float = Field(1.0, ge=0.1, le=10.0, description="Delay between requests in seconds")
    document_links_selector: str = Field(..., description="CSS selector for document links")
    use_headless: bool = Field(True, description="Use headless browser")
    custom_headers: Optional[Dict[str, str]] = Field(None, description="Custom HTTP headers")
    
    class Config:
        schema_extra = {
            "example": {
                "max_pages": 15,
                "delay_between_requests": 2.5,
                "document_links_selector": "a[href*='.pdf']",
                "use_headless": True,
                "custom_headers": {
                    "User-Agent": "FinancialExtractor/1.0"
                }
            }
        }


# ==================== RESPONSE MODELS ====================

class ExtractionJobResponse(BaseModel):
    """Response model for job creation"""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatusEnum = Field(..., description="Initial job status")
    message: str = Field(..., description="Success message")
    estimated_completion_minutes: int = Field(..., description="Estimated time to completion")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Job creation timestamp")
    
    class Config:
        schema_extra = {
            "example": {
                "job_id": "job_123e4567-e89b-12d3-a456-426614174000",
                "status": "running",
                "message": "Extraction job started successfully",
                "estimated_completion_minutes": 15,
                "created_at": "2024-01-15T10:30:00Z"
            }
        }


class FinancialMetricsResponse(BaseModel):
    """Response model for financial metrics"""
    # Revenue metrics
    revenue: Optional[Decimal] = Field(None, description="Total revenue")
    net_income: Optional[Decimal] = Field(None, description="Net income")
    ebitda: Optional[Decimal] = Field(None, description="EBITDA")
    
    # Balance sheet
    total_assets: Optional[Decimal] = Field(None, description="Total assets")
    shareholders_equity: Optional[Decimal] = Field(None, description="Shareholders equity")
    
    # Cash flow
    operating_cash_flow: Optional[Decimal] = Field(None, description="Operating cash flow")
    free_cash_flow: Optional[Decimal] = Field(None, description="Free cash flow")
    
    # Per share metrics
    earnings_per_share: Optional[Decimal] = Field(None, description="Earnings per share")
    
    # Ratios
    debt_to_equity_ratio: Optional[Decimal] = Field(None, description="Debt to equity ratio")
    current_ratio: Optional[Decimal] = Field(None, description="Current ratio")
    
    # Metadata
    extraction_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score of extraction")
    currency: str = Field("USD", description="Currency of financial figures")
    reporting_period: Optional[str] = Field(None, description="Reporting period")
    completeness_score: float = Field(..., ge=0.0, le=1.0, description="Data completeness score")
    
    class Config:
        schema_extra = {
            "example": {
                "revenue": 285000000,
                "net_income": 45000000,
                "ebitda": 95000000,
                "total_assets": 850000000,
                "shareholders_equity": 420000000,
                "operating_cash_flow": 75000000,
                "extraction_confidence": 0.92,
                "currency": "USD",
                "reporting_period": "2023-Q4",
                "completeness_score": 0.85
            }
        }


class DocumentSummary(BaseModel):
    """Summary information about a processed document"""
    document_id: UUID = Field(..., description="Document unique identifier")
    title: str = Field(..., description="Document title")
    url: HttpUrl = Field(..., description="Document URL")
    status: ExtractionStatusEnum = Field(..., description="Processing status")
    confidence_level: float = Field(..., ge=0.0, le=1.0, description="Processing confidence")
    validation_score: float = Field(..., ge=0.0, le=1.0, description="Validation score")
    error_messages: List[str] = Field(default_factory=list, description="Any error messages")


class ExtractionJobStatusResponse(BaseModel):
    """Detailed job status response"""
    job_id: UUID = Field(..., description="Job unique identifier")
    name: str = Field(..., description="Job name")
    status: JobStatusEnum = Field(..., description="Current job status")
    progress_percentage: float = Field(..., ge=0.0, le=100.0, description="Completion percentage")
    
    # Counts
    total_documents: NonNegativeInt = Field(..., description="Total documents found")
    processed_documents: NonNegativeInt = Field(..., description="Documents processed")
    successful_documents: NonNegativeInt = Field(..., description="Successfully processed")
    failed_documents: NonNegativeInt = Field(..., description="Failed to process")
    
    # Performance metrics
    success_rate: float = Field(..., ge=0.0, le=100.0, description="Success rate percentage")
    duration_seconds: Optional[float] = Field(None, description="Job duration in seconds")
    
    # Timestamps
    created_at: datetime = Field(..., description="Job creation time")
    started_at: Optional[datetime] = Field(None, description="Job start time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")
    
    # Documents detail
    documents: List[DocumentSummary] = Field(default_factory=list, description="Processed documents")
    
    class Config:
        schema_extra = {
            "example": {
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Torex Gold Q4 2023 Extraction",
                "status": "completed",
                "progress_percentage": 100.0,
                "total_documents": 12,
                "processed_documents": 12,
                "successful_documents": 11,
                "failed_documents": 1,
                "success_rate": 91.7,
                "duration_seconds": 342.5,
                "created_at": "2024-01-15T10:30:00Z",
                "started_at": "2024-01-15T10:30:15Z",
                "completed_at": "2024-01-15T10:36:00Z"
            }
        }


class ExtractionJobSummary(BaseModel):
    """Summary information for job listings"""
    job_id: UUID = Field(..., description="Job unique identifier")
    name: str = Field(..., description="Job name")
    company_name: str = Field(..., description="Target company name")
    status: JobStatusEnum = Field(..., description="Current status")
    progress_percentage: float = Field(..., ge=0.0, le=100.0, description="Progress percentage")
    success_rate: float = Field(..., ge=0.0, le=100.0, description="Success rate")
    created_at: datetime = Field(..., description="Creation timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")


class FinancialDocumentResponse(BaseModel):
    """Response model for financial documents"""
    id: UUID = Field(..., description="Document unique identifier")
    title: str = Field(..., description="Document title")
    url: HttpUrl = Field(..., description="Document source URL")
    document_type: DocumentTypeEnum = Field(..., description="Type of document")
    year: int = Field(..., description="Reporting year")
    quarter: Optional[int] = Field(None, ge=1, le=4, description="Quarter (if applicable)")
    status: ExtractionStatusEnum = Field(..., description="Processing status")
    confidence_level: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    validation_score: float = Field(..., ge=0.0, le=1.0, description="Validation score")
    file_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    error_messages: List[str] = Field(default_factory=list, description="Error messages if any")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "Q4 2023 Financial Results",
                "url": "https://example.com/reports/q4-2023.pdf",
                "document_type": "quarterly_report",
                "year": 2023,
                "quarter": 4,
                "status": "completed",
                "confidence_level": 0.92,
                "validation_score": 0.88,
                "file_size_bytes": 2048576,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:35:00Z",
                "error_messages": []
            }
        }


class FinancialDocumentDetailResponse(FinancialDocumentResponse):
    """Detailed document response including extracted metrics"""
    financial_metrics: Optional[FinancialMetricsResponse] = Field(
        None, 
        description="Extracted financial metrics"
    )
    extraction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional extraction metadata"
    )
    validation_details: Optional[Dict[str, Any]] = Field(
        None,
        description="Detailed validation results"
    )


class RetryExtractionResponse(BaseModel):
    """Response for extraction retry requests"""
    success: bool = Field(..., description="Whether retry was successful")
    message: str = Field(..., description="Status message")
    new_confidence: Optional[float] = Field(None, description="New confidence score if successful")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Update timestamp")


class AnalyticsSummaryResponse(BaseModel):
    """Analytics summary response"""
    total_documents_processed: NonNegativeInt = Field(..., description="Total documents processed")
    successful_extractions: NonNegativeInt = Field(..., description="Successful extractions")
    failed_extractions: NonNegativeInt = Field(..., description="Failed extractions")
    average_confidence_score: float = Field(..., ge=0.0, le=1.0, description="Average confidence")
    total_companies: NonNegativeInt = Field(..., description="Number of companies processed")
    extraction_success_rate: float = Field(..., ge=0.0, le=100.0, description="Success rate percentage")
    average_processing_time_seconds: float = Field(..., description="Average processing time")
    period_days: PositiveInt = Field(..., description="Analysis period in days")
    
    class Config:
        schema_extra = {
            "example": {
                "total_documents_processed": 150,
                "successful_extractions": 142,
                "failed_extractions": 8,
                "average_confidence_score": 0.87,
                "total_companies": 12,
                "extraction_success_rate": 94.7,
                "average_processing_time_seconds": 45.2,
                "period_days": 30
            }
        }


class CompanyAnalyticsResponse(BaseModel):
    """Per-company analytics response"""
    company_name: str = Field(..., description="Company name")
    documents_processed: NonNegativeInt = Field(..., description="Documents processed for this company")
    success_rate: float = Field(..., ge=0.0, le=100.0, description="Success rate percentage")
    average_confidence: float = Field(..., ge=0.0, le=1.0, description="Average confidence score")
    last_extraction: Optional[datetime] = Field(None, description="Last extraction timestamp")
    total_revenue_extracted: Optional[Decimal] = Field(None, description="Total revenue across all periods")
    
    class Config:
        schema_extra = {
            "example": {
                "company_name": "Torex Gold Resources Inc.",
                "documents_processed": 25,
                "success_rate": 96.0,
                "average_confidence": 0.89,
                "last_extraction": "2024-01-15T10:30:00Z",
                "total_revenue_extracted": 1250000000
            }
        }


class ScrapingConfigResponse(BaseModel):
    """Scraping configuration response"""
    company_name: str = Field(..., description="Company name")
    max_pages: PositiveInt = Field(..., description="Maximum pages to scrape")
    delay_between_requests: float = Field(..., description="Delay between requests")
    document_links_selector: str = Field(..., description="CSS selector for documents")
    use_headless: bool = Field(..., description="Use headless browser")
    success_rate: float = Field(..., ge=0.0, le=100.0, description="Historical success rate")
    last_updated: datetime = Field(..., description="Configuration last updated")
    custom_headers: Dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers")


# ==================== ERROR MODELS ====================

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str = Field(..., description="Error type/code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: float = Field(..., description="Error timestamp")
    
    class Config:
        schema_extra = {
            "example": {
                "error": "validation_error",
                "message": "Invalid year range provided",
                "details": {
                    "field": "target_years",
                    "provided_value": [1999, 2025]
                },
                "timestamp": 1642234800.0
            }
        }


class ValidationError(BaseModel):
    """Validation error details"""
    field: str = Field(..., description="Field that failed validation")
    message: str = Field(..., description="Validation error message")
    provided_value: Any = Field(None, description="Value that was provided")
    expected_format: Optional[str] = Field(None, description="Expected format/type")


class ValidationErrorResponse(ErrorResponse):
    """Validation error response with field details"""
    validation_errors: List[ValidationError] = Field(..., description="Specific validation errors")


# ==================== WEBSOCKET MODELS ====================

class JobUpdateMessage(BaseModel):
    """Real-time job update message for WebSocket"""
    job_id: UUID = Field(..., description="Job identifier")
    status: JobStatusEnum = Field(..., description="Current status")
    progress: float = Field(..., ge=0.0, le=100.0, description="Progress percentage")
    message: Optional[str] = Field(None, description="Status message")
    timestamp: float = Field(..., description="Update timestamp")
    documents_processed: Optional[int] = Field(None, description="Documents processed so far")
    current_document: Optional[str] = Field(None, description="Currently processing document")
    
    class Config:
        schema_extra = {
            "example": {
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "running",
                "progress": 45.5,
                "message": "Processing document 5 of 11",
                "timestamp": 1642234800.0,
                "documents_processed": 4,
                "current_document": "Q3-2023-Financial-Results.pdf"
            }
        }


# ==================== PAGINATION MODELS ====================

class PaginationMetadata(BaseModel):
    """Metadata for paginated responses"""
    total_items: NonNegativeInt = Field(..., description="Total number of items")
    items_per_page: PositiveInt = Field(..., description="Items per page")
    current_page: PositiveInt = Field(..., description="Current page number")
    total_pages: PositiveInt = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there are more pages")
    has_previous: bool = Field(..., description="Whether there are previous pages")


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper"""
    items: List[Any] = Field(..., description="Items in current page")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")
    
    class Config:
        schema_extra = {
            "example": {
                "items": ["...items array..."],
                "pagination": {
                    "total_items": 150,
                    "items_per_page": 20,
                    "current_page": 1,
                    "total_pages": 8,
                    "has_next": True,
                    "has_previous": False
                }
            }
        }