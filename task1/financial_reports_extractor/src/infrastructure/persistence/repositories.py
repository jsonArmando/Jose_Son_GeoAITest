"""
Implementaciones de repositorios usando SQLAlchemy
Adaptadores de persistencia para la Arquitectura Hexagonal
"""

from typing import List, Dict, Optional, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.orm import selectinload

from ...domain.entities import FinancialDocument, ExtractionJob, CompanyProfile, DocumentType, ExtractionStatus
from ...domain.ports import FinancialDocumentRepository, ExtractionJobRepository, CompanyProfileRepository
from .models import FinancialDocumentModel, ExtractionJobModel, CompanyProfileModel, FinancialMetricsModel


class SQLAlchemyFinancialDocumentRepository(FinancialDocumentRepository):
    """Implementación SQLAlchemy del repositorio de documentos financieros"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def save(self, document: FinancialDocument) -> None:
        """Guarda un documento financiero"""
        # Buscar si ya existe
        stmt = select(FinancialDocumentModel).where(
            FinancialDocumentModel.id == document.id
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # Actualizar existente
            self._update_model_from_entity(existing, document)
        else:
            # Crear nuevo
            model = self._create_model_from_entity(document)
            self.session.add(model)
        
        await self.session.commit()
    
    async def find_by_id(self, document_id: UUID) -> Optional[FinancialDocument]:
        """Busca un documento por ID"""
        stmt = select(FinancialDocumentModel).where(
            FinancialDocumentModel.id == document_id
        ).options(selectinload(FinancialDocumentModel.financial_metrics))
        
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        
        return self._create_entity_from_model(model) if model else None
    
    async def find_by_url(self, url: str) -> Optional[FinancialDocument]:
        """Busca un documento por URL"""
        stmt = select(FinancialDocumentModel).where(
            FinancialDocumentModel.url == url
        ).options(selectinload(FinancialDocumentModel.financial_metrics))
        
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        
        return self._create_entity_from_model(model) if model else None
    
    async def find_by_company_and_period(
        self, 
        company_name: str, 
        year: int, 
        quarter: Optional[int] = None
    ) -> List[FinancialDocument]:
        """Busca documentos por empresa y período"""
        conditions = [
            FinancialDocumentModel.year == year
        ]
        
        if quarter:
            conditions.append(FinancialDocumentModel.quarter == quarter)
        
        # Buscar por nombre de empresa en metadatos o tags
        company_condition = or_(
            FinancialDocumentModel.metadata.contains(f'"{company_name}"'),
            FinancialDocumentModel.tags.any(company_name.lower())
        )
        conditions.append(company_condition)
        
        stmt = select(FinancialDocumentModel).where(
            and_(*conditions)
        ).options(selectinload(FinancialDocumentModel.financial_metrics))
        
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        
        return [self._create_entity_from_model(model) for model in models]
    
    async def find_pending_processing(self, limit: int = 10) -> List[FinancialDocument]:
        """Busca documentos pendientes de procesamiento"""
        stmt = select(FinancialDocumentModel).where(
            FinancialDocumentModel.extraction_status.in_([
                ExtractionStatus.PENDING.value,
                ExtractionStatus.RETRY.value
            ])
        ).limit(limit).options(selectinload(FinancialDocumentModel.financial_metrics))
        
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        
        return [self._create_entity_from_model(model) for model in models]
    
    async def find_failed_documents(self, limit: int = 10) -> List[FinancialDocument]:
        """Busca documentos que fallaron en el procesamiento"""
        stmt = select(FinancialDocumentModel).where(
            FinancialDocumentModel.extraction_status == ExtractionStatus.FAILED.value
        ).order_by(desc(FinancialDocumentModel.updated_at)).limit(limit).options(
            selectinload(FinancialDocumentModel.financial_metrics)
        )
        
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        
        return [self._create_entity_from_model(model) for model in models]
    
    async def delete(self, document_id: UUID) -> None:
        """Elimina un documento"""
        stmt = select(FinancialDocumentModel).where(
            FinancialDocumentModel.id == document_id
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        
        if model:
            await self.session.delete(model)
            await self.session.commit()
    
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
        conditions = []
        
        if company_name:
            company_condition = or_(
                FinancialDocumentModel.metadata.contains(f'"{company_name}"'),
                FinancialDocumentModel.tags.any(company_name.lower())
            )
            conditions.append(company_condition)
        
        if year:
            conditions.append(FinancialDocumentModel.year == year)
        
        if document_type:
            conditions.append(FinancialDocumentModel.document_type == document_type)
        
        if status:
            conditions.append(FinancialDocumentModel.extraction_status == status)
        
        stmt = select(FinancialDocumentModel)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        stmt = stmt.order_by(desc(FinancialDocumentModel.created_at)).offset(offset).limit(limit).options(
            selectinload(FinancialDocumentModel.financial_metrics)
        )
        
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        
        return [self._create_entity_from_model(model) for model in models]
    
    def _create_model_from_entity(self, document: FinancialDocument) -> FinancialDocumentModel:
        """Convierte entidad a modelo SQLAlchemy"""
        return FinancialDocumentModel(
            id=document.id,
            url=document.url,
            title=document.title,
            document_type=document.document_type.value,
            year=document.year,
            quarter=document.quarter.value if document.quarter else None,
            publication_date=document.publication_date,
            file_path=document.file_path,
            file_size_bytes=document.file_size_bytes,
            file_hash=document.file_hash,
            original_filename=document.original_filename,
            extraction_status=document.extraction_status.value,
            created_at=document.created_at,
            updated_at=document.updated_at,
            validation_score=document.validation_score,
            confidence_level=document.confidence_level,
            error_messages=document.error_messages,
            retry_count=document.retry_count,
            max_retries=document.max_retries,
            metadata=document.metadata,
            tags=document.tags
        )
    
    def _update_model_from_entity(self, model: FinancialDocumentModel, document: FinancialDocument) -> None:
        """Actualiza modelo existente con datos de entidad"""
        model.url = document.url
        model.title = document.title
        model.document_type = document.document_type.value
        model.year = document.year
        model.quarter = document.quarter.value if document.quarter else None
        model.publication_date = document.publication_date
        model.file_path = document.file_path
        model.file_size_bytes = document.file_size_bytes
        model.file_hash = document.file_hash
        model.original_filename = document.original_filename
        model.extraction_status = document.extraction_status.value
        model.updated_at = document.updated_at
        model.validation_score = document.validation_score
        model.confidence_level = document.confidence_level
        model.error_messages = document.error_messages
        model.retry_count = document.retry_count
        model.max_retries = document.max_retries
        model.metadata = document.metadata
        model.tags = document.tags
    
    def _create_entity_from_model(self, model: FinancialDocumentModel) -> FinancialDocument:
        """Convierte modelo SQLAlchemy a entidad"""
        from ...domain.entities import Quarter
        
        return FinancialDocument(
            id=model.id,
            url=model.url,
            title=model.title,
            document_type=DocumentType(model.document_type),
            year=model.year,
            quarter=Quarter(model.quarter) if model.quarter else None,
            publication_date=model.publication_date,
            file_path=model.file_path,
            file_size_bytes=model.file_size_bytes,
            file_hash=model.file_hash,
            original_filename=model.original_filename,
            extraction_status=ExtractionStatus(model.extraction_status),
            created_at=model.created_at,
            updated_at=model.updated_at,
            validation_score=model.validation_score,
            confidence_level=model.confidence_level,
            error_messages=model.error_messages or [],
            retry_count=model.retry_count,
            max_retries=model.max_retries,
            metadata=model.metadata or {},
            tags=model.tags or []
        )


class SQLAlchemyExtractionJobRepository(ExtractionJobRepository):
    """Implementación SQLAlchemy del repositorio de trabajos de extracción"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def save(self, job: ExtractionJob) -> None:
        """Guarda un trabajo de extracción"""
        stmt = select(ExtractionJobModel).where(ExtractionJobModel.id == job.id)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            self._update_model_from_entity(existing, job)
        else:
            model = self._create_model_from_entity(job)
            self.session.add(model)
        
        await self.session.commit()
    
    async def find_by_id(self, job_id: UUID) -> Optional[ExtractionJob]:
        """Busca un trabajo por ID"""
        stmt = select(ExtractionJobModel).where(ExtractionJobModel.id == job_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        
        return self._create_entity_from_model(model) if model else None
    
    async def find_active_jobs(self) -> List[ExtractionJob]:
        """Busca trabajos activos"""
        stmt = select(ExtractionJobModel).where(
            ExtractionJobModel.status.in_(['created', 'running'])
        ).order_by(desc(ExtractionJobModel.created_at))
        
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        
        return [self._create_entity_from_model(model) for model in models]
    
    async def find_completed_jobs(self, limit: int = 10) -> List[ExtractionJob]:
        """Busca trabajos completados"""
        stmt = select(ExtractionJobModel).where(
            ExtractionJobModel.status.in_(['completed', 'failed'])
        ).order_by(desc(ExtractionJobModel.completed_at)).limit(limit)
        
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        
        return [self._create_entity_from_model(model) for model in models]
    
    def _create_model_from_entity(self, job: ExtractionJob) -> ExtractionJobModel:
        """Convierte entidad a modelo SQLAlchemy"""
        return ExtractionJobModel(
            id=job.id,
            name=job.name,
            company_url=job.company_url,
            target_years=job.target_years,
            document_types=[dt.value for dt in job.document_types],
            status=job.status,
            progress_percentage=job.progress_percentage,
            document_ids=[str(doc_id) for doc_id in job.document_ids],
            total_documents_found=job.total_documents_found,
            documents_processed=job.documents_processed,
            documents_successful=job.documents_successful,
            documents_failed=job.documents_failed,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            configuration=job.configuration
        )
    
    def _update_model_from_entity(self, model: ExtractionJobModel, job: ExtractionJob) -> None:
        """Actualiza modelo existente con datos de entidad"""
        model.name = job.name
        model.company_url = job.company_url
        model.target_years = job.target_years
        model.document_types = [dt.value for dt in job.document_types]
        model.status = job.status
        model.progress_percentage = job.progress_percentage
        model.document_ids = [str(doc_id) for doc_id in job.document_ids]
        model.total_documents_found = job.total_documents_found
        model.documents_processed = job.documents_processed
        model.documents_successful = job.documents_successful
        model.documents_failed = job.documents_failed
        model.started_at = job.started_at
        model.completed_at = job.completed_at
        model.configuration = job.configuration
    
    def _create_entity_from_model(self, model: ExtractionJobModel) -> ExtractionJob:
        """Convierte modelo SQLAlchemy a entidad"""
        return ExtractionJob(
            id=model.id,
            name=model.name,
            company_url=model.company_url,
            target_years=model.target_years or [],
            document_types=[DocumentType(dt) for dt in (model.document_types or [])],
            status=model.status,
            progress_percentage=model.progress_percentage,
            document_ids=[UUID(doc_id) for doc_id in (model.document_ids or [])],
            total_documents_found=model.total_documents_found,
            documents_processed=model.documents_processed,
            documents_successful=model.documents_successful,
            documents_failed=model.documents_failed,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            configuration=model.configuration or {}
        )


class SQLAlchemyCompanyProfileRepository(CompanyProfileRepository):
    """Implementación SQLAlchemy del repositorio de perfiles de empresas"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def save(self, profile: CompanyProfile) -> None:
        """Guarda un perfil de empresa"""
        stmt = select(CompanyProfileModel).where(CompanyProfileModel.id == profile.id)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            self._update_model_from_entity(existing, profile)
        else:
            model = self._create_model_from_entity(profile)
            self.session.add(model)
        
        await self.session.commit()
    
    async def find_by_name(self, name: str) -> Optional[CompanyProfile]:
        """Busca un perfil por nombre de empresa"""
        stmt = select(CompanyProfileModel).where(
            func.lower(CompanyProfileModel.name) == func.lower(name)
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        
        return self._create_entity_from_model(model) if model else None
    
    async def find_by_base_url(self, base_url: str) -> Optional[CompanyProfile]:
        """Busca un perfil por URL base"""
        stmt = select(CompanyProfileModel).where(
            CompanyProfileModel.base_url == base_url
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        
        return self._create_entity_from_model(model) if model else None
    
    def _create_model_from_entity(self, profile: CompanyProfile) -> CompanyProfileModel:
        """Convierte entidad a modelo SQLAlchemy"""
        return CompanyProfileModel(
            id=profile.id,
            name=profile.name,
            ticker_symbol=profile.ticker_symbol,
            base_url=profile.base_url,
            reports_url=profile.reports_url,
            url_patterns=profile.url_patterns,
            css_selectors=profile.css_selectors,
            sector=profile.sector,
            industry=profile.industry,
            country=profile.country,
            scraping_config=profile.scraping_config,
            last_scraped_at=profile.last_scraped_at,
            total_documents_found=profile.total_documents_found,
            scraping_success_rate=profile.scraping_success_rate,
            created_at=profile.created_at,
            updated_at=profile.updated_at
        )
    
    def _update_model_from_entity(self, model: CompanyProfileModel, profile: CompanyProfile) -> None:
        """Actualiza modelo existente con datos de entidad"""
        model.name = profile.name
        model.ticker_symbol = profile.ticker_symbol
        model.base_url = profile.base_url
        model.reports_url = profile.reports_url
        model.url_patterns = profile.url_patterns
        model.css_selectors = profile.css_selectors
        model.sector = profile.sector
        model.industry = profile.industry
        model.country = profile.country
        model.scraping_config = profile.scraping_config
        model.last_scraped_at = profile.last_scraped_at
        model.total_documents_found = profile.total_documents_found
        model.scraping_success_rate = profile.scraping_success_rate
        model.updated_at = profile.updated_at
    
    def _create_entity_from_model(self, model: CompanyProfileModel) -> CompanyProfile:
        """Convierte modelo SQLAlchemy a entidad"""
        return CompanyProfile(
            id=model.id,
            name=model.name,
            ticker_symbol=model.ticker_symbol,
            base_url=model.base_url,
            reports_url=model.reports_url,
            url_patterns=model.url_patterns or {},
            css_selectors=model.css_selectors or {},
            sector=model.sector,
            industry=model.industry,
            country=model.country,
            scraping_config=model.scraping_config or {},
            last_scraped_at=model.last_scraped_at,
            total_documents_found=model.total_documents_found,
            scraping_success_rate=model.scraping_success_rate,
            created_at=model.created_at,
            updated_at=model.updated_at
        )