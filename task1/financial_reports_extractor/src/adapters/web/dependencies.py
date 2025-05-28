"""
FastAPI Dependencies
Dependency injection for services and use cases
"""

import asyncio
from functools import lru_cache
from typing import Dict, Any
import os

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import aioredis

from ...application.use_cases import (
    ExtractFinancialReportsUseCase,
    GetExtractionJobStatusUseCase,
    ListFinancialDocumentsUseCase,
    RetryFailedExtractionUseCase
)
from ...infrastructure.persistence.repositories import (
    SQLAlchemyFinancialDocumentRepository,
    SQLAlchemyExtractionJobRepository,
    SQLAlchemyCompanyProfileRepository
)
from ...infrastructure.services import (
    LocalFileStorageService,
    MinIOFileStorageService,
    RedisCacheService,
    PrometheusMetricsService,
    StructuredLoggingService,
    SimpleEventPublisherService
)
from ...adapters.scraping.intelligent_scraper import IntelligentWebScrapingAgent
from ...adapters.ai_agents.financial_extractor import MultiModalFinancialExtractor
from ...adapters.ai_agents.validation_agent import IntelligentValidationAgent
from .config import get_settings


# ==================== CONFIGURATION ====================

@lru_cache()
def get_settings():
    """Get application settings (cached)"""
    return Settings()


class Settings:
    """Application settings from environment variables"""
    
    def __init__(self):
        # Database
        self.database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres123@localhost:5432/financial_reports")
        
        # Redis
        self.redis_url = os.getenv("REDIS_URL", "redis://:redis123@localhost:6379/0")
        
        # MinIO/S3
        self.minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
        self.minio_bucket_name = os.getenv("MINIO_BUCKET_NAME", "financial-documents")
        self.minio_secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
        
        # AI APIs
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        
        # Selenium
        self.selenium_hub_url = os.getenv("SELENIUM_HUB_URL", "http://localhost:4444/wd/hub")
        
        # Application
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"


# ==================== DATABASE DEPENDENCIES ====================

class DatabaseSessionManager:
    """Database session manager singleton"""
    
    def __init__(self):
        self._engine = None
        self._session_factory = None
    
    def init(self, database_url: str):
        """Initialize database engine and session factory"""
        self._engine = create_async_engine(
            database_url,
            echo=False,
            pool_size=20,
            max_overflow=30,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    async def close(self):
        """Close database connections"""
        if self._engine:
            await self._engine.dispose()
    
    @property
    def session_factory(self):
        if not self._session_factory:
            raise RuntimeError("Database not initialized")
        return self._session_factory


# Global session manager
db_manager = DatabaseSessionManager()


async def get_database_session() -> AsyncSession:
    """Get database session dependency"""
    if not db_manager._session_factory:
        settings = get_settings()
        db_manager.init(settings.database_url)
    
    async with db_manager.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ==================== CACHE DEPENDENCIES ====================

class CacheManager:
    """Cache manager singleton"""
    
    def __init__(self):
        self._cache_service = None
    
    async def get_cache_service(self):
        if not self._cache_service:
            settings = get_settings()
            self._cache_service = RedisCacheService(settings.redis_url)
        return self._cache_service


cache_manager = CacheManager()


async def get_cache_service():
    """Get cache service dependency"""
    return await cache_manager.get_cache_service()


# ==================== STORAGE DEPENDENCIES ====================

class StorageManager:
    """Storage manager singleton"""
    
    def __init__(self):
        self._storage_service = None
    
    def get_storage_service(self):
        if not self._storage_service:
            settings = get_settings()
            
            # Use MinIO in production, local storage in development
            if settings.environment == "production":
                self._storage_service = MinIOFileStorageService(
                    endpoint=settings.minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                    bucket_name=settings.minio_bucket_name,
                    secure=settings.minio_secure
                )
            else:
                self._storage_service = LocalFileStorageService("./storage")
        
        return self._storage_service


storage_manager = StorageManager()


def get_storage_service():
    """Get storage service dependency"""
    return storage_manager.get_storage_service()


# ==================== LOGGING DEPENDENCIES ====================

class LoggingManager:
    """Logging manager singleton"""
    
    def __init__(self):
        self._logger = None
    
    def get_logger(self):
        if not self._logger:
            settings = get_settings()
            self._logger = StructuredLoggingService(settings.log_level)
        return self._logger


logging_manager = LoggingManager()


def get_logger():
    """Get logger service dependency"""
    return logging_manager.get_logger()


# ==================== METRICS DEPENDENCIES ====================

class MetricsManager:
    """Metrics manager singleton"""
    
    def __init__(self):
        self._metrics = None
    
    def get_metrics_service(self):
        if not self._metrics:
            self._metrics = PrometheusMetricsService()
        return self._metrics


metrics_manager = MetricsManager()


def get_metrics_service():
    """Get metrics service dependency"""
    return metrics_manager.get_metrics_service()


# ==================== EVENT PUBLISHER DEPENDENCIES ====================

class EventManager:
    """Event publisher manager singleton"""
    
    def __init__(self):
        self._publisher = None
    
    def get_event_publisher(self, logger):
        if not self._publisher:
            self._publisher = SimpleEventPublisherService(logger)
        return self._publisher


event_manager = EventManager()


def get_event_publisher(logger = Depends(get_logger)):
    """Get event publisher dependency"""
    return event_manager.get_event_publisher(logger)


# ==================== AI AGENTS DEPENDENCIES ====================

class AIAgentsManager:
    """AI agents manager singleton"""
    
    def __init__(self):
        self._scraper = None
        self._extractor = None
        self._validator = None
    
    def get_scraping_agent(self, logger):
        if not self._scraper:
            settings = get_settings()
            self._scraper = IntelligentWebScrapingAgent(
                openai_api_key=settings.openai_api_key,
                selenium_hub_url=settings.selenium_hub_url,
                logger=logger
            )
        return self._scraper
    
    async def get_extraction_agent(self, cache, logger):
        if not self._extractor:
            settings = get_settings()
            self._extractor = MultiModalFinancialExtractor(
                openai_api_key=settings.openai_api_key,
                anthropic_api_key=settings.anthropic_api_key,
                cache=cache,
                logger=logger
            )
        return self._extractor
    
    def get_validation_agent(self, cache, logger):
        if not self._validator:
            settings = get_settings()
            self._validator = IntelligentValidationAgent(
                openai_api_key=settings.openai_api_key,
                cache=cache,
                logger=logger
            )
        return self._validator


ai_agents_manager = AIAgentsManager()


def get_scraping_agent(logger = Depends(get_logger)):
    """Get web scraping agent dependency"""
    return ai_agents_manager.get_scraping_agent(logger)


async def get_extraction_agent(
    cache = Depends(get_cache_service),
    logger = Depends(get_logger)
):
    """Get AI extraction agent dependency"""
    return await ai_agents_manager.get_extraction_agent(cache, logger)


def get_validation_agent(
    cache = Depends(get_cache_service),
    logger = Depends(get_logger)
):
    """Get validation agent dependency"""
    return ai_agents_manager.get_validation_agent(cache, logger)


# ==================== REPOSITORY DEPENDENCIES ====================

def get_document_repository(session: AsyncSession = Depends(get_database_session)):
    """Get financial document repository"""
    return SQLAlchemyFinancialDocumentRepository(session)


def get_job_repository(session: AsyncSession = Depends(get_database_session)):
    """Get extraction job repository"""
    return SQLAlchemyExtractionJobRepository(session)


def get_company_repository(session: AsyncSession = Depends(get_database_session)):
    """Get company profile repository"""
    return SQLAlchemyCompanyProfileRepository(session)


# ==================== USE CASE DEPENDENCIES ====================

async def get_extract_reports_use_case(
    document_repo = Depends(get_document_repository),
    job_repo = Depends(get_job_repository),
    company_repo = Depends(get_company_repository),
    scraper = Depends(get_scraping_agent),
    ai_extractor = Depends(get_extraction_agent),
    validator = Depends(get_validation_agent),
    file_storage = Depends(get_storage_service),
    event_publisher = Depends(get_event_publisher),
    metrics = Depends(get_metrics_service),
    logger = Depends(get_logger),
    config_service = Depends(get_configuration_service)
):
    """Get extract financial reports use case"""
    return ExtractFinancialReportsUseCase(
        document_repo=document_repo,
        job_repo=job_repo,
        company_repo=company_repo,
        scraper=scraper,
        ai_extractor=ai_extractor,
        validator=validator,
        file_storage=file_storage,
        event_publisher=event_publisher,
        metrics=metrics,
        logger=logger,
        config=config_service
    )


def get_job_status_use_case(
    job_repo = Depends(get_job_repository),
    document_repo = Depends(get_document_repository)
):
    """Get job status use case"""
    return GetExtractionJobStatusUseCase(job_repo, document_repo)


def get_list_documents_use_case(
    document_repo = Depends(get_document_repository)
):
    """Get list documents use case"""
    return ListFinancialDocumentsUseCase(document_repo)


async def get_retry_extraction_use_case(
    document_repo = Depends(get_document_repository),
    ai_extractor = Depends(get_extraction_agent),
    validator = Depends(get_validation_agent),
    event_publisher = Depends(get_event_publisher),
    logger = Depends(get_logger),
    config_service = Depends(get_configuration_service)
):
    """Get retry extraction use case"""
    return RetryFailedExtractionUseCase(
        document_repo=document_repo,
        ai_extractor=ai_extractor,
        validator=validator,
        event_publisher=event_publisher,
        logger=logger,
        config=config_service
    )


# ==================== CONFIGURATION SERVICE ====================

class ConfigurationService:
    """Configuration service for dynamic settings"""
    
    def __init__(self):
        self.settings = get_settings()
    
    async def get_scraping_config(self, company_name: str):
        """Get scraping configuration for company"""
        from ...domain.value_objects import ScrapingConfiguration
        
        # Default configuration - in production would come from database
        return ScrapingConfiguration(
            base_url="",  # Will be set by use case
            max_pages=10,
            delay_between_requests=2.0,
            document_links_selector="a[href*='.pdf'], a[href*='report']",
            use_headless=True
        )
    
    async def get_ai_config(self):
        """Get AI extraction configuration"""
        from ...domain.value_objects import AIExtractionConfiguration
        
        return AIExtractionConfiguration(
            model_name="gpt-4-turbo-preview",
            max_tokens=4000,
            temperature=0.1,
            use_ocr=True,
            process_images=True,
            process_tables=True,
            enable_cross_validation=True,
            min_confidence_threshold=0.7,
            cache_responses=True,
            cache_ttl_hours=24
        )
    
    async def get_validation_config(self):
        """Get validation configuration"""
        return {
            "min_confidence_score": 0.7,
            "max_variance_percentage": 25.0,
            "balance_sheet_tolerance": 0.02,
            "enable_external_validation": False
        }


config_service_instance = ConfigurationService()


def get_configuration_service():
    """Get configuration service dependency"""
    return config_service_instance


# ==================== COMBINED USE CASES DEPENDENCY ====================

async def get_use_cases() -> Dict[str, Any]:
    """
    Get all use cases in a single dependency.
    Useful for endpoints that might need multiple use cases.
    """
    
    # Get all individual dependencies
    settings = get_settings()
    
    # Initialize database session manager if not already done
    if not db_manager._session_factory:
        db_manager.init(settings.database_url)
    
    # Create session
    async with db_manager.session_factory() as session:
        # Repositories
        document_repo = SQLAlchemyFinancialDocumentRepository(session)
        job_repo = SQLAlchemyExtractionJobRepository(session)
        company_repo = SQLAlchemyCompanyProfileRepository(session)
        
        # Services
        logger = StructuredLoggingService(settings.log_level)
        metrics = PrometheusMetricsService()
        cache = await cache_manager.get_cache_service()
        storage = storage_manager.get_storage_service()
        event_publisher = SimpleEventPublisherService(logger)
        config_service = ConfigurationService()
        
        # AI Agents
        scraper = IntelligentWebScrapingAgent(
            openai_api_key=settings.openai_api_key,
            selenium_hub_url=settings.selenium_hub_url,
            logger=logger
        )
        
        extractor = MultiModalFinancialExtractor(
            openai_api_key=settings.openai_api_key,
            anthropic_api_key=settings.anthropic_api_key,
            cache=cache,
            logger=logger
        )
        
        validator = IntelligentValidationAgent(
            openai_api_key=settings.openai_api_key,
            cache=cache,
            logger=logger
        )
        
        # Use Cases
        use_cases = {
            'extract_reports': ExtractFinancialReportsUseCase(
                document_repo=document_repo,
                job_repo=job_repo,
                company_repo=company_repo,
                scraper=scraper,
                ai_extractor=extractor,
                validator=validator,
                file_storage=storage,
                event_publisher=event_publisher,
                metrics=metrics,
                logger=logger,
                config=config_service
            ),
            'get_job_status': GetExtractionJobStatusUseCase(job_repo, document_repo),
            'list_documents': ListFinancialDocumentsUseCase(document_repo),
            'retry_extraction': RetryFailedExtractionUseCase(
                document_repo=document_repo,
                ai_extractor=extractor,
                validator=validator,
                event_publisher=event_publisher,
                logger=logger,
                config=config_service
            )
        }
        
        return use_cases


# ==================== CLEANUP DEPENDENCIES ====================

async def cleanup_resources():
    """Cleanup function to be called on application shutdown"""
    # Close database connections
    await db_manager.close()
    
    # Close other connections if needed
    if cache_manager._cache_service:
        # Redis connections are handled automatically
        pass
    
    # Close AI agent sessions if needed
    if ai_agents_manager._scraper and hasattr(ai_agents_manager._scraper, 'session'):
        if ai_agents_manager._scraper.session:
            await ai_agents_manager._scraper.session.close()


# ==================== HEALTH CHECK DEPENDENCIES ====================

async def check_database_health() -> bool:
    """Check database connectivity"""
    try:
        async with db_manager.session_factory() as session:
            await session.execute("SELECT 1")
            return True
    except Exception:
        return False


async def check_cache_health() -> bool:
    """Check cache connectivity"""
    try:
        cache = await cache_manager.get_cache_service()
        await cache.set("health_check", "ok", expiration_seconds=10)
        result = await cache.get("health_check")
        return result == "ok"
    except Exception:
        return False


async def check_storage_health() -> bool:
    """Check storage connectivity"""
    try:
        storage = storage_manager.get_storage_service()
        test_content = b"health_check"
        await storage.store_file("health_check.txt", test_content)
        retrieved = await storage.retrieve_file("health_check.txt")
        await storage.delete_file("health_check.txt")
        return retrieved == test_content
    except Exception:
        return False


async def get_health_checks() -> Dict[str, bool]:
    """Get all health check results"""
    return {
        "database": await check_database_health(),
        "cache": await check_cache_health(),
        "storage": await check_storage_health(),
    }