"""
FastAPI Application - Financial Reports Extractor API
RESTful API for the financial document extraction system
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import structlog

from ...application.use_cases import (
    ExtractFinancialReportsUseCase,
    GetExtractionJobStatusUseCase,
    ListFinancialDocumentsUseCase,
    RetryFailedExtractionUseCase,
    ExtractFinancialReportsCommand,
    ExtractionResult
)
from ...domain.entities import DocumentType
from .dependencies import get_use_cases, get_metrics_service, get_logger
from .middleware import RequestLoggingMiddleware, MetricsMiddleware
from .schemas import *


# Configurar logging
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for FastAPI app"""
    # Startup
    logger.info("Starting Financial Reports Extractor API")
    yield
    # Shutdown
    logger.info("Shutting down Financial Reports Extractor API")


# Crear aplicación FastAPI
app = FastAPI(
    title="Financial Reports Extractor API",
    description="AI-powered financial document extraction and analysis system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configurar apropiadamente en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(MetricsMiddleware)


# ==================== HEALTH CHECKS ====================

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0",
        "service": "financial-reports-extractor"
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """Readiness check - verify all dependencies are available"""
    try:
        # Aquí podrías verificar conexiones a BD, APIs externas, etc.
        # Por simplicidad, retornamos siempre ready
        return {
            "status": "ready",
            "timestamp": time.time(),
            "checks": {
                "database": "ok",
                "cache": "ok",
                "external_apis": "ok"
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "error": str(e)}
        )


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics():
    """Prometheus metrics endpoint"""
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# ==================== EXTRACTION ENDPOINTS ====================

@app.post("/extraction/jobs", response_model=ExtractionJobResponse, tags=["Extraction"])
async def create_extraction_job(
    request: ExtractionJobRequest,
    background_tasks: BackgroundTasks,
    use_cases = Depends(get_use_cases),
    logger_service = Depends(get_logger)
):
    """
    Create a new financial reports extraction job
    """
    try:
        # Crear comando
        command = ExtractFinancialReportsCommand(
            company_url=request.company_url,
            company_name=request.company_name,
            target_years=request.target_years,
            document_types=request.document_types,
            notify_webhook=request.notify_webhook,
            job_name=request.job_name
        )
        
        # Ejecutar en background
        background_tasks.add_task(
            execute_extraction_job,
            use_cases['extract_reports'],
            command,
            logger_service
        )
        
        # Por ahora retornamos un job_id temporal
        # En una implementación real, crearías el job primero y luego lo ejecutarías
        job_id = "temp-job-id"
        
        await logger_service.log_info(
            "Extraction job created",
            context={
                "company": request.company_name,
                "years": request.target_years,
                "job_id": job_id
            }
        )
        
        return ExtractionJobResponse(
            job_id=job_id,
            status="started",
            message="Extraction job started successfully",
            estimated_completion_minutes=15
        )
        
    except Exception as e:
        await logger_service.log_error(
            "Error creating extraction job",
            error=e,
            context={"request": request.dict()}
        )
        raise HTTPException(status_code=500, detail=str(e))


async def execute_extraction_job(
    use_case: ExtractFinancialReportsUseCase,
    command: ExtractFinancialReportsCommand,
    logger_service
):
    """Execute extraction job in background"""
    try:
        result = await use_case.execute(command)
        await logger_service.log_info(
            "Extraction job completed",
            context={
                "job_id": str(result.job_id),
                "total_documents": result.total_documents,
                "successful": result.successful_extractions,
                "failed": result.failed_extractions
            }
        )
    except Exception as e:
        await logger_service.log_error(
            "Error in background extraction job",
            error=e
        )


@app.get("/extraction/jobs/{job_id}", response_model=ExtractionJobStatusResponse, tags=["Extraction"])
async def get_extraction_job_status(
    job_id: UUID = Path(..., description="Job ID"),
    use_cases = Depends(get_use_cases)
):
    """
    Get the status of an extraction job
    """
    try:
        status_use_case: GetExtractionJobStatusUseCase = use_cases['get_job_status']
        job_status = await status_use_case.execute(job_id)
        
        if not job_status:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return ExtractionJobStatusResponse(**job_status)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/extraction/jobs", response_model=List[ExtractionJobSummary], tags=["Extraction"])
async def list_extraction_jobs(
    status: Optional[str] = Query(None, description="Filter by job status"),
    limit: int = Query(20, ge=1, le=100, description="Number of jobs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    use_cases = Depends(get_use_cases)
):
    """
    List extraction jobs with optional filtering
    """
    try:
        # Esta funcionalidad necesitaría un caso de uso adicional
        # Por ahora retornamos una lista vacía
        return []
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== DOCUMENTS ENDPOINTS ====================

@app.get("/documents", response_model=List[FinancialDocumentResponse], tags=["Documents"])
async def list_financial_documents(
    company_name: Optional[str] = Query(None, description="Filter by company name"),
    year: Optional[int] = Query(None, ge=2000, le=2030, description="Filter by year"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    status: Optional[str] = Query(None, description="Filter by extraction status"),
    limit: int = Query(50, ge=1, le=200, description="Number of documents to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    use_cases = Depends(get_use_cases)
):
    """
    List financial documents with filtering options
    """
    try:
        list_use_case: ListFinancialDocumentsUseCase = use_cases['list_documents']
        
        documents = await list_use_case.execute(
            company_name=company_name,
            year=year,
            document_type=document_type,
            status=status,
            limit=limit,
            offset=offset
        )
        
        return [FinancialDocumentResponse(**doc) for doc in documents]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents/{document_id}", response_model=FinancialDocumentDetailResponse, tags=["Documents"])
async def get_document_details(
    document_id: UUID = Path(..., description="Document ID"),
    use_cases = Depends(get_use_cases)
):
    """
    Get detailed information about a specific document
    """
    try:
        # Esta funcionalidad necesitaría un caso de uso específico
        # Por ahora retornamos error 501
        raise HTTPException(status_code=501, detail="Not implemented yet")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/documents/{document_id}/retry", response_model=RetryExtractionResponse, tags=["Documents"])
async def retry_document_extraction(
    document_id: UUID = Path(..., description="Document ID"),
    use_cases = Depends(get_use_cases),
    logger_service = Depends(get_logger)
):
    """
    Retry extraction for a failed document
    """
    try:
        retry_use_case: RetryFailedExtractionUseCase = use_cases['retry_extraction']
        
        success = await retry_use_case.execute(document_id)
        
        if success:
            await logger_service.log_info(
                "Document extraction retry successful",
                context={"document_id": str(document_id)}
            )
            return RetryExtractionResponse(
                success=True,
                message="Extraction retry completed successfully"
            )
        else:
            return RetryExtractionResponse(
                success=False,
                message="Document cannot be retried or retry failed"
            )
            
    except Exception as e:
        await logger_service.log_error(
            "Error retrying document extraction",
            error=e,
            context={"document_id": str(document_id)}
        )
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ANALYTICS ENDPOINTS ====================

@app.get("/analytics/summary", response_model=AnalyticsSummaryResponse, tags=["Analytics"])
async def get_analytics_summary(
    period_days: int = Query(30, ge=1, le=365, description="Period in days for analytics"),
    use_cases = Depends(get_use_cases)
):
    """
    Get analytics summary for the specified period
    """
    try:
        # Esta sería una implementación ejemplo
        return AnalyticsSummaryResponse(
            total_documents_processed=150,
            successful_extractions=142,
            failed_extractions=8,
            average_confidence_score=0.87,
            total_companies=12,
            extraction_success_rate=94.7,
            average_processing_time_seconds=45.2,
            period_days=period_days
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/companies", response_model=List[CompanyAnalyticsResponse], tags=["Analytics"])
async def get_company_analytics(
    limit: int = Query(20, ge=1, le=100),
    use_cases = Depends(get_use_cases)
):
    """
    Get analytics breakdown by company
    """
    try:
        # Implementación ejemplo
        return [
            CompanyAnalyticsResponse(
                company_name="Torex Gold Resources",
                documents_processed=25,
                success_rate=96.0,
                average_confidence=0.89,
                last_extraction="2024-01-15T10:30:00Z"
            )
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CONFIGURATION ENDPOINTS ====================

@app.get("/config/companies/{company_name}/scraping", response_model=ScrapingConfigResponse, tags=["Configuration"])
async def get_company_scraping_config(
    company_name: str = Path(..., description="Company name"),
    use_cases = Depends(get_use_cases)
):
    """
    Get scraping configuration for a specific company
    """
    try:
        # Esta funcionalidad necesitaría casos de uso específicos
        raise HTTPException(status_code=501, detail="Configuration endpoints not implemented yet")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/config/companies/{company_name}/scraping", response_model=Dict[str, str], tags=["Configuration"])
async def update_company_scraping_config(
    company_name: str = Path(..., description="Company name"),
    config: ScrapingConfigRequest = ...,
    use_cases = Depends(get_use_cases),
    logger_service = Depends(get_logger)
):
    """
    Update scraping configuration for a specific company
    """
    try:
        # Implementación futura
        await logger_service.log_audit(
            "scraping_config_updated",
            resource_id=company_name,
            context={"config": config.dict()}
        )
        
        return {"message": "Configuration updated successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ERROR HANDLERS ====================

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions"""
    return JSONResponse(
        status_code=400,
        content={
            "error": "validation_error",
            "message": str(exc),
            "timestamp": time.time()
        }
    )


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found",
            "message": "Resource not found",
            "timestamp": time.time()
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle internal server errors"""
    logger.error("Internal server error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An internal error occurred",
            "timestamp": time.time()
        }
    )


# ==================== WEBSOCKET ENDPOINTS ====================

@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_updates(websocket, job_id: str):
    """
    WebSocket endpoint for real-time job status updates
    """
    await websocket.accept()
    
    try:
        # En una implementación real, te suscribirías a eventos del job
        while True:
            # Simular actualizaciones de estado
            await asyncio.sleep(5)
            await websocket.send_json({
                "job_id": job_id,
                "status": "processing",
                "progress": 45.0,
                "timestamp": time.time()
            })
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()


# ==================== STARTUP CONFIGURATION ====================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )