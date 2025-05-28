"""
Casos de Uso de la Aplicación
Orquestan la lógica de negocio utilizando los puertos del dominio
Arquitectura Hexagonal - Application Layer
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from uuid import UUID, uuid4
from datetime import datetime
import asyncio

from ..domain.entities import FinancialDocument, ExtractionJob, CompanyProfile, DocumentType, ExtractionStatus
from ..domain.value_objects import (
    FinancialMetrics, 
    ValidationResult, 
    ScrapingConfiguration,
    AIExtractionConfiguration,
    ExtractionContext
)
from ..domain.ports import (
    FinancialDocumentRepository,
    ExtractionJobRepository,
    CompanyProfileRepository,
    WebScrapingPort,
    AIExtractionPort,
    ValidationPort,
    FileStoragePort,
    EventPublisherPort,
    MetricsPort,
    LoggingPort,
    ConfigurationPort
)


@dataclass
class ExtractFinancialReportsCommand:
    """Comando para extraer reportes financieros"""
    company_url: str
    company_name: str
    target_years: List[int]
    document_types: Optional[List[DocumentType]] = None
    notify_webhook: Optional[str] = None
    job_name: Optional[str] = None


@dataclass
class ExtractionResult:
    """Resultado de extracción"""
    job_id: UUID
    total_documents: int
    successful_extractions: int
    failed_extractions: int
    average_confidence: float
    processing_time_seconds: float
    documents: List[FinancialDocument]


class ExtractFinancialReportsUseCase:
    """
    Caso de uso principal: Extraer reportes financieros de una empresa
    """
    
    def __init__(
        self,
        document_repo: FinancialDocumentRepository,
        job_repo: ExtractionJobRepository,
        company_repo: CompanyProfileRepository,
        scraper: WebScrapingPort,
        ai_extractor: AIExtractionPort,
        validator: ValidationPort,
        file_storage: FileStoragePort,
        event_publisher: EventPublisherPort,
        metrics: MetricsPort,
        logger: LoggingPort,
        config: ConfigurationPort
    ):
        self.document_repo = document_repo
        self.job_repo = job_repo
        self.company_repo = company_repo
        self.scraper = scraper
        self.ai_extractor = ai_extractor
        self.validator = validator
        self.file_storage = file_storage
        self.event_publisher = event_publisher
        self.metrics = metrics
        self.logger = logger
        self.config = config
    
    async def execute(self, command: ExtractFinancialReportsCommand) -> ExtractionResult:
        """Ejecuta el proceso completo de extracción"""
        start_time = datetime.utcnow()
        
        # 1. Crear trabajo de extracción
        job = await self._create_extraction_job(command)
        await self.job_repo.save(job)
        
        try:
            # 2. Obtener o crear perfil de empresa
            company_profile = await self._get_or_create_company_profile(command)
            
            # 3. Configurar scraping
            scraping_config = await self._get_scraping_configuration(company_profile)
            
            # 4. Descubrir documentos
            discovered_docs = await self._discover_documents(
                command.company_url, 
                scraping_config,
                command.target_years,
                command.document_types or []
            )
            
            job.total_documents_found = len(discovered_docs)
            await self.job_repo.save(job)
            
            # 5. Procesar documentos en paralelo (con límite de concurrencia)
            semaphore = asyncio.Semaphore(5)  # Máximo 5 documentos simultáneos
            
            tasks = [
                self._process_document_with_semaphore(
                    semaphore, doc_info, job, company_profile.name
                )
                for doc_info in discovered_docs
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 6. Procesar resultados
            documents = []
            successful_count = 0
            failed_count = 0
            confidence_scores = []
            
            for result in results:
                if isinstance(result, Exception):
                    failed_count += 1
                    await self.logger.log_error(
                        "Error procesando documento",
                        error=result
                    )
                elif result:
                    documents.append(result)
                    if result.extraction_status == ExtractionStatus.COMPLETED:
                        successful_count += 1
                        confidence_scores.append(result.confidence_level)
                    else:
                        failed_count += 1
                    
                    job.record_document_processed(
                        result.extraction_status == ExtractionStatus.COMPLETED
                    )
            
            # 7. Completar trabajo
            job.complete_job()
            await self.job_repo.save(job)
            
            # 8. Publicar evento de finalización
            await self.event_publisher.publish_job_status_changed(job)
            
            # 9. Registrar métricas
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            await self._record_job_metrics(job, processing_time, successful_count, failed_count)
            
            # 10. Retornar resultado
            return ExtractionResult(
                job_id=job.id,
                total_documents=len(documents),
                successful_extractions=successful_count,
                failed_extractions=failed_count,
                average_confidence=sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0,
                processing_time_seconds=processing_time,
                documents=documents
            )
            
        except Exception as e:
            job.fail_job(str(e))
            await self.job_repo.save(job)
            await self.logger.log_error(
                "Error en trabajo de extracción",
                error=e,
                context={"job_id": str(job.id)}
            )
            raise
    
    async def _create_extraction_job(self, command: ExtractFinancialReportsCommand) -> ExtractionJob:
        """Crea un nuevo trabajo de extracción"""
        job = ExtractionJob(
            name=command.job_name or f"{command.company_name} - {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            company_url=command.company_url,
            target_years=command.target_years,
            document_types=command.document_types or [],
            configuration={
                'company_name': command.company_name,
                'notify_webhook': command.notify_webhook
            }
        )
        job.start_job()
        
        await self.logger.log_info(
            "Trabajo de extracción creado",
            context={"job_id": str(job.id), "company": command.company_name}
        )
        
        return job
    
    async def _get_or_create_company_profile(
        self, 
        command: ExtractFinancialReportsCommand
    ) -> CompanyProfile:
        """Obtiene o crea un perfil de empresa"""
        profile = await self.company_repo.find_by_name(command.company_name)
        
        if not profile:
            profile = CompanyProfile(
                name=command.company_name,
                base_url=command.company_url,
                reports_url=command.company_url
            )
            await self.company_repo.save(profile)
            
            await self.logger.log_info(
                "Perfil de empresa creado",
                context={"company": command.company_name}
            )
        
        return profile
    
    async def _get_scraping_configuration(
        self, 
        company_profile: CompanyProfile
    ) -> ScrapingConfiguration:
        """Obtiene la configuración de scraping para la empresa"""
        try:
            return await self.config.get_scraping_config(company_profile.name)
        except Exception:
            # Configuración por defecto si no existe específica
            return ScrapingConfiguration(
                base_url=company_profile.base_url,
                max_pages=10,
                delay_between_requests=2.0,
                document_links_selector="a[href*='.pdf'], a[href*='report'], a[href*='financial']",
                use_headless=True
            )
    
    async def _discover_documents(
        self,
        base_url: str,
        config: ScrapingConfiguration,
        target_years: List[int],
        document_types: List[DocumentType]
    ) -> List[Dict[str, Any]]:
        """Descubre documentos financieros en el sitio web"""
        try:
            discovered = await self.scraper.discover_documents(base_url, config)
            
            # Filtrar por años objetivo
            filtered_docs = []
            for doc in discovered:
                doc_year = doc.get('year', 0)
                doc_type = doc.get('type', 'unknown')
                
                if doc_year in target_years:
                    if not document_types or DocumentType(doc_type) in document_types:
                        filtered_docs.append(doc)
            
            await self.logger.log_info(
                f"Documentos descubiertos: {len(discovered)}, filtrados: {len(filtered_docs)}",
                context={"base_url": base_url}
            )
            
            return filtered_docs
            
        except Exception as e:
            await self.logger.log_error(
                "Error descubriendo documentos",
                error=e,
                context={"base_url": base_url}
            )
            raise
    
    async def _process_document_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        doc_info: Dict[str, Any],
        job: ExtractionJob,
        company_name: str
    ) -> Optional[FinancialDocument]:
        """Procesa un documento con control de concurrencia"""
        async with semaphore:
            return await self._process_single_document(doc_info, job, company_name)
    
    async def _process_single_document(
        self,
        doc_info: Dict[str, Any],
        job: ExtractionJob,
        company_name: str
    ) -> Optional[FinancialDocument]:
        """Procesa un único documento"""
        document_start_time = datetime.utcnow()
        
        try:
            # 1. Crear entidad de documento
            document = FinancialDocument(
                url=doc_info['url'],
                title=doc_info.get('title', ''),
                document_type=DocumentType(doc_info.get('type', 'unknown')),
                year=doc_info.get('year', 0),
                quarter=doc_info.get('quarter'),
                original_filename=doc_info.get('filename', '')
            )
            
            # 2. Verificar si ya existe
            existing = await self.document_repo.find_by_url(document.url)
            if existing and existing.extraction_status == ExtractionStatus.COMPLETED:
                await self.logger.log_info(
                    "Documento ya procesado, omitiendo",
                    context={"url": document.url}
                )
                return existing
            
            # 3. Descargar documento
            document.extraction_status = ExtractionStatus.DOWNLOADING
            await self.document_repo.save(document)
            
            download_info = await self.scraper.download_document(
                document.url,
                f"storage/documents/{document.id}.pdf"
            )
            
            document.mark_as_downloaded(
                download_info['file_path'],
                download_info['file_size'],
                download_info['file_hash']
            )
            
            await self.event_publisher.publish_document_downloaded(document)
            
            # 4. Extraer datos con IA
            document.extraction_status = ExtractionStatus.PROCESSING
            await self.document_repo.save(document)
            
            extraction_context = ExtractionContext(
                document_type=document.document_type.value,
                company_name=company_name,
                reporting_period=document.get_period_identifier(),
                fiscal_year=document.year,
                source_url=document.url,
                file_path=document.file_path or "",
                page_count=0,  # Se actualizará durante la extracción
                file_size_bytes=document.file_size_bytes or 0
            )
            
            ai_config = await self.config.get_ai_config()
            
            financial_metrics = await self.ai_extractor.extract_financial_data(
                document.file_path or "",
                extraction_context,
                ai_config
            )
            
            # 5. Validar datos extraídos
            document.extraction_status = ExtractionStatus.VALIDATING
            await self.document_repo.save(document)
            
            validation_result = await self.validator.validate_financial_metrics(
                financial_metrics,
                extraction_context
            )
            
            # 6. Completar procesamiento
            document.mark_as_completed(
                validation_result.confidence_score,
                financial_metrics.extraction_confidence
            )
            
            # 7. Guardar documento y métricas
            await self.document_repo.save(document)
            
            # 8. Publicar eventos
            await self.event_publisher.publish_extraction_completed(document, financial_metrics)
            
            # 9. Registrar métricas de rendimiento
            processing_time = (datetime.utcnow() - document_start_time).total_seconds()
            await self.metrics.record_document_processed(
                True,
                processing_time,
                document.document_type.value
            )
            
            await self.metrics.record_extraction_accuracy(
                validation_result.confidence_score,
                financial_metrics.extraction_confidence,
                company_name
            )
            
            await self.logger.log_info(
                "Documento procesado exitosamente",
                context={
                    "document_id": str(document.id),
                    "confidence": validation_result.confidence_score,
                    "processing_time": processing_time
                }
            )
            
            return document
            
        except Exception as e:
            # Manejar error en procesamiento
            if 'document' in locals():
                document.mark_as_failed(str(e))
                await self.document_repo.save(document)
                await self.event_publisher.publish_extraction_failed(document, str(e))
                
                processing_time = (datetime.utcnow() - document_start_time).total_seconds()
                await self.metrics.record_document_processed(
                    False,
                    processing_time,
                    document.document_type.value
                )
            
            await self.logger.log_error(
                "Error procesando documento",
                error=e,
                context={"doc_info": doc_info}
            )
            
            return None
    
    async def _record_job_metrics(
        self,
        job: ExtractionJob,
        processing_time: float,
        successful_count: int,
        failed_count: int
    ) -> None:
        """Registra métricas del trabajo completo"""
        labels = {
            "job_id": str(job.id),
            "company": job.configuration.get('company_name', 'unknown')
        }
        
        await self.metrics.record_histogram(
            "extraction_job_duration_seconds",
            processing_time,
            labels
        )
        
        await self.metrics.increment_counter(
            "extraction_jobs_completed",
            labels
        )
        
        await self.metrics.record_histogram(
            "extraction_success_rate",
            job.get_success_rate(),
            labels
        )


class GetExtractionJobStatusUseCase:
    """Caso de uso: Obtener estado de trabajo de extracción"""
    
    def __init__(
        self,
        job_repo: ExtractionJobRepository,
        document_repo: FinancialDocumentRepository
    ):
        self.job_repo = job_repo
        self.document_repo = document_repo
    
    async def execute(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """Obtiene el estado detallado de un trabajo"""
        job = await self.job_repo.find_by_id(job_id)
        if not job:
            return None
        
        # Obtener documentos asociados
        documents = []
        for doc_id in job.document_ids:
            doc = await self.document_repo.find_by_id(doc_id)
            if doc:
                documents.append({
                    'id': str(doc.id),
                    'title': doc.title,
                    'url': doc.url,
                    'status': doc.extraction_status.value,
                    'confidence': doc.confidence_level,
                    'validation_score': doc.validation_score,
                    'error_messages': doc.error_messages
                })
        
        return {
            'job_id': str(job.id),
            'name': job.name,
            'status': job.status,
            'progress_percentage': job.progress_percentage,
            'total_documents': job.total_documents_found,
            'processed_documents': job.documents_processed,
            'successful_documents': job.documents_successful,
            'failed_documents': job.documents_failed,
            'success_rate': job.get_success_rate(),
            'duration_seconds': job.get_duration_seconds(),
            'created_at': job.created_at.isoformat(),
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'documents': documents
        }


class ListFinancialDocumentsUseCase:
    """Caso de uso: Listar documentos financieros con filtros"""
    
    def __init__(self, document_repo: FinancialDocumentRepository):
        self.document_repo = document_repo
    
    async def execute(
        self,
        company_name: Optional[str] = None,
        year: Optional[int] = None,
        document_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Lista documentos con filtros aplicados"""
        documents = await self.document_repo.list_by_filters(
            company_name=company_name,
            year=year,
            document_type=document_type,
            status=status,
            limit=limit,
            offset=offset
        )
        
        return [
            {
                'id': str(doc.id),
                'title': doc.title,
                'url': doc.url,
                'document_type': doc.document_type.value,
                'year': doc.year,
                'quarter': doc.quarter.value if doc.quarter else None,
                'status': doc.extraction_status.value,
                'confidence_level': doc.confidence_level,
                'validation_score': doc.validation_score,
                'created_at': doc.created_at.isoformat(),
                'updated_at': doc.updated_at.isoformat(),
                'file_size_bytes': doc.file_size_bytes,
                'error_messages': doc.error_messages
            }
            for doc in documents
        ]


class RetryFailedExtractionUseCase:
    """Caso de uso: Reintentar extracción fallida"""
    
    def __init__(
        self,
        document_repo: FinancialDocumentRepository,
        ai_extractor: AIExtractionPort,
        validator: ValidationPort,
        event_publisher: EventPublisherPort,
        logger: LoggingPort,
        config: ConfigurationPort
    ):
        self.document_repo = document_repo
        self.ai_extractor = ai_extractor
        self.validator = validator
        self.event_publisher = event_publisher
        self.logger = logger
        self.config = config
    
    async def execute(self, document_id: UUID) -> bool:
        """Reintenta la extracción de un documento fallido"""
        document = await self.document_repo.find_by_id(document_id)
        
        if not document or not document.can_retry():
            return False
        
        try:
            # Resetear estado para reintento
            document.extraction_status = ExtractionStatus.PROCESSING
            await self.document_repo.save(document)
            
            # Crear contexto de extracción
            extraction_context = ExtractionContext(
                document_type=document.document_type.value,
                company_name="",  # Se debería obtener del contexto
                reporting_period=document.get_period_identifier(),
                fiscal_year=document.year,
                source_url=document.url,
                file_path=document.file_path or "",
                page_count=0,
                file_size_bytes=document.file_size_bytes or 0
            )
            
            # Reextraer datos
            ai_config = await self.config.get_ai_config()
            financial_metrics = await self.ai_extractor.extract_financial_data(
                document.file_path or "",
                extraction_context,
                ai_config
            )
            
            # Revalidar
            validation_result = await self.validator.validate_financial_metrics(
                financial_metrics,
                extraction_context
            )
            
            # Completar
            document.mark_as_completed(
                validation_result.confidence_score,
                financial_metrics.extraction_confidence
            )
            
            await self.document_repo.save(document)
            await self.event_publisher.publish_extraction_completed(document, financial_metrics)
            
            await self.logger.log_info(
                "Reintento de extracción exitoso",
                context={"document_id": str(document_id)}
            )
            
            return True
            
        except Exception as e:
            document.mark_as_failed(str(e))
            await self.document_repo.save(document)
            
            await self.logger.log_error(
                "Error en reintento de extracción",
                error=e,
                context={"document_id": str(document_id)}
            )
            
            return False