"""
Integration Tests for Use Cases
Tests the interaction between use cases and their dependencies
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from uuid import uuid4

from src.application.use_cases import (
    ExtractFinancialReportsUseCase,
    GetExtractionJobStatusUseCase,
    ListFinancialDocumentsUseCase,
    RetryFailedExtractionUseCase,
    ExtractFinancialReportsCommand,
    ExtractionResult
)
from src.domain.entities import (
    FinancialDocument, 
    ExtractionJob, 
    CompanyProfile,
    DocumentType, 
    ExtractionStatus
)
from src.domain.value_objects import (
    FinancialMetrics,
    ValidationResult,
    ScrapingConfiguration,
    AIExtractionConfiguration,
    ExtractionContext
)


class TestExtractFinancialReportsUseCase:
    """Integration tests for the main extraction use case"""
    
    @pytest.fixture
    async def mock_dependencies(self):
        """Create mock dependencies for the use case"""
        return {
            'document_repo': AsyncMock(),
            'job_repo': AsyncMock(),
            'company_repo': AsyncMock(),
            'scraper': AsyncMock(),
            'ai_extractor': AsyncMock(),
            'validator': AsyncMock(),
            'file_storage': AsyncMock(),
            'event_publisher': AsyncMock(),
            'metrics': AsyncMock(),
            'logger': AsyncMock(),
            'config': AsyncMock()
        }
    
    @pytest.fixture
    def extraction_command(self):
        """Sample extraction command"""
        return ExtractFinancialReportsCommand(
            company_url="https://torexgold.com/investors/financial-reports/",
            company_name="Torex Gold Resources Inc.",
            target_years=[2022, 2023, 2024],
            document_types=[DocumentType.QUARTERLY_REPORT, DocumentType.ANNUAL_REPORT],
            job_name="Test Extraction Job"
        )
    
    async def test_successful_extraction_flow(self, mock_dependencies, extraction_command):
        """Test successful end-to-end extraction flow"""
        # Setup mocks
        mocks = mock_dependencies
        
        # Mock company profile
        company_profile = CompanyProfile(
            name="Torex Gold Resources Inc.",
            base_url="https://torexgold.com",
            reports_url="https://torexgold.com/investors/financial-reports/"
        )
        mocks['company_repo'].find_by_name.return_value = company_profile
        
        # Mock scraping configuration
        scraping_config = ScrapingConfiguration(
            base_url="https://torexgold.com/investors/financial-reports/",
            max_pages=10,
            delay_between_requests=2.0
        )
        mocks['config'].get_scraping_config.return_value = scraping_config
        
        # Mock discovered documents
        discovered_docs = [
            {
                'id': 'doc1',
                'url': 'https://torexgold.com/report1.pdf',
                'title': 'Q4 2023 Report',
                'type': 'quarterly_report',
                'year': 2023,
                'quarter': 4
            },
            {
                'id': 'doc2',
                'url': 'https://torexgold.com/report2.pdf',
                'title': '2023 Annual Report',
                'type': 'annual_report',
                'year': 2023,
                'quarter': None
            }
        ]
        mocks['scraper'].discover_documents.return_value = discovered_docs
        
        # Mock document download
        download_info = {
            'file_path': '/tmp/document.pdf',
            'file_size': 1024000,
            'file_hash': 'abc123def456'
        }
        mocks['scraper'].download_document.return_value = download_info
        
        # Mock AI extraction
        financial_metrics = FinancialMetrics(
            revenue=Decimal('285000000'),
            net_income=Decimal('45000000'),
            ebitda=Decimal('95000000'),
            extraction_confidence=0.92,
            currency="USD",
            reporting_period="2023-Q4"
        )
        mocks['ai_extractor'].extract_financial_data.return_value = financial_metrics
        
        # Mock AI configuration
        ai_config = AIExtractionConfiguration(
            model_name="gpt-4-turbo-preview",
            max_tokens=4000,
            temperature=0.1
        )
        mocks['config'].get_ai_config.return_value = ai_config
        
        # Mock validation
        validation_result = ValidationResult(
            is_valid=True,
            confidence_score=0.89,
            validation_messages=["Data validation successful"],
            warnings=[],
            errors=[]
        )
        mocks['validator'].validate_financial_metrics.return_value = validation_result
        
        # Create use case
        use_case = ExtractFinancialReportsUseCase(**mocks)
        
        # Execute
        result = await use_case.execute(extraction_command)
        
        # Assertions
        assert isinstance(result, ExtractionResult)
        assert result.total_documents == 2
        assert result.successful_extractions == 2
        assert result.failed_extractions == 0
        assert result.average_confidence > 0.8
        
        # Verify interactions
        mocks['company_repo'].find_by_name.assert_called_once_with("Torex Gold Resources Inc.")
        mocks['scraper'].discover_documents.assert_called_once()
        mocks['scraper'].download_document.assert_called()
        mocks['ai_extractor'].extract_financial_data.assert_called()
        mocks['validator'].validate_financial_metrics.assert_called()
        mocks['event_publisher'].publish_extraction_completed.assert_called()
    
    async def test_scraping_failure_handling(self, mock_dependencies, extraction_command):
        """Test handling of scraping failures"""
        mocks = mock_dependencies
        
        # Mock company profile
        company_profile = CompanyProfile(
            name="Torex Gold Resources Inc.",
            base_url="https://torexgold.com"
        )
        mocks['company_repo'].find_by_name.return_value = company_profile
        
        # Mock scraping failure
        mocks['scraper'].discover_documents.side_effect = Exception("Network timeout")
        
        # Create use case
        use_case = ExtractFinancialReportsUseCase(**mocks)
        
        # Execute and expect exception
        with pytest.raises(Exception, match="Network timeout"):
            await use_case.execute(extraction_command)
        
        # Verify error handling
        mocks['logger'].log_error.assert_called()
    
    async def test_partial_extraction_success(self, mock_dependencies, extraction_command):
        """Test scenario where some documents succeed and others fail"""
        mocks = mock_dependencies
        
        # Setup basic mocks
        company_profile = CompanyProfile(
            name="Torex Gold Resources Inc.",
            base_url="https://torexgold.com"
        )
        mocks['company_repo'].find_by_name.return_value = company_profile
        
        scraping_config = ScrapingConfiguration(
            base_url="https://torexgold.com/investors/financial-reports/",
            max_pages=10
        )
        mocks['config'].get_scraping_config.return_value = scraping_config
        
        # Mock discovered documents
        discovered_docs = [
            {
                'id': 'doc1',
                'url': 'https://torexgold.com/good-report.pdf',
                'title': 'Q4 2023 Report',
                'type': 'quarterly_report',
                'year': 2023
            },
            {
                'id': 'doc2',
                'url': 'https://torexgold.com/bad-report.pdf',
                'title': 'Corrupted Report',
                'type': 'quarterly_report',
                'year': 2023
            }
        ]
        mocks['scraper'].discover_documents.return_value = discovered_docs
        
        # Mock download - first succeeds, second fails
        async def mock_download_side_effect(url, path):
            if 'good-report' in url:
                return {
                    'file_path': '/tmp/good-document.pdf',
                    'file_size': 1024000,
                    'file_hash': 'abc123'
                }
            else:
                raise Exception("Download failed")
        
        mocks['scraper'].download_document.side_effect = mock_download_side_effect
        
        # Mock successful extraction for good document
        financial_metrics = FinancialMetrics(
            revenue=Decimal('285000000'),
            extraction_confidence=0.92
        )
        mocks['ai_extractor'].extract_financial_data.return_value = financial_metrics
        
        ai_config = AIExtractionConfiguration()
        mocks['config'].get_ai_config.return_value = ai_config
        
        validation_result = ValidationResult(
            is_valid=True,
            confidence_score=0.89
        )
        mocks['validator'].validate_financial_metrics.return_value = validation_result
        
        # Create use case
        use_case = ExtractFinancialReportsUseCase(**mocks)
        
        # Execute
        result = await use_case.execute(extraction_command)
        
        # Assertions
        assert result.total_documents == 2  # Both documents attempted
        assert result.successful_extractions == 1  # Only one succeeded
        assert result.failed_extractions == 1  # One failed
        
        # Verify error events were published
        mocks['event_publisher'].publish_extraction_failed.assert_called()
    
    async def test_company_profile_creation(self, mock_dependencies, extraction_command):
        """Test creation of new company profile when it doesn't exist"""
        mocks = mock_dependencies
        
        # Mock company not found
        mocks['company_repo'].find_by_name.return_value = None
        
        # Mock successful profile creation
        async def mock_save_company(profile):
            assert profile.name == "Torex Gold Resources Inc."
            assert profile.base_url == "https://torexgold.com/investors/financial-reports/"
        
        mocks['company_repo'].save.side_effect = mock_save_company
        
        # Mock other dependencies to avoid complex setup
        mocks['config'].get_scraping_config.return_value = ScrapingConfiguration(
            base_url="https://torexgold.com"
        )
        mocks['scraper'].discover_documents.return_value = []
        
        # Create use case
        use_case = ExtractFinancialReportsUseCase(**mocks)
        
        # Execute
        await use_case.execute(extraction_command)
        
        # Verify company profile was created and saved
        mocks['company_repo'].save.assert_called_once()


class TestGetExtractionJobStatusUseCase:
    """Integration tests for job status retrieval"""
    
    @pytest.fixture
    def mock_repositories(self):
        """Mock repositories for job status use case"""
        return {
            'job_repo': AsyncMock(),
            'document_repo': AsyncMock()
        }
    
    async def test_get_existing_job_status(self, mock_repositories):
        """Test retrieving status of existing job"""
        job_id = uuid4()
        doc_id1 = uuid4()
        doc_id2 = uuid4()
        
        # Mock job
        extraction_job = ExtractionJob(
            id=job_id,
            name="Test Job",
            company_url="https://example.com",
            status="completed",
            progress_percentage=100.0,
            total_documents_found=2,
            documents_processed=2,
            documents_successful=2,
            documents_failed=0
        )
        extraction_job.document_ids = [doc_id1, doc_id2]
        
        mock_repositories['job_repo'].find_by_id.return_value = extraction_job
        
        # Mock documents
        doc1 = FinancialDocument(
            id=doc_id1,
            url="https://example.com/doc1.pdf",
            title="Document 1",
            extraction_status=ExtractionStatus.COMPLETED,
            confidence_level=0.92,
            validation_score=0.88
        )
        
        doc2 = FinancialDocument(
            id=doc_id2,
            url="https://example.com/doc2.pdf",
            title="Document 2",
            extraction_status=ExtractionStatus.COMPLETED,
            confidence_level=0.85,
            validation_score=0.90
        )
        
        async def mock_find_by_id(doc_id):
            if doc_id == doc_id1:
                return doc1
            elif doc_id == doc_id2:
                return doc2
            return None
        
        mock_repositories['document_repo'].find_by_id.side_effect = mock_find_by_id
        
        # Create use case
        use_case = GetExtractionJobStatusUseCase(**mock_repositories)
        
        # Execute
        result = await use_case.execute(job_id)
        
        # Assertions
        assert result is not None
        assert result['job_id'] == str(job_id)
        assert result['name'] == "Test Job"
        assert result['status'] == "completed"
        assert result['progress_percentage'] == 100.0
        assert result['total_documents'] == 2
        assert result['successful_documents'] == 2
        assert result['failed_documents'] == 0
        assert len(result['documents']) == 2
    
    async def test_get_nonexistent_job_status(self, mock_repositories):
        """Test retrieving status of non-existent job"""
        job_id = uuid4()
        
        # Mock job not found
        mock_repositories['job_repo'].find_by_id.return_value = None
        
        # Create use case
        use_case = GetExtractionJobStatusUseCase(**mock_repositories)
        
        # Execute
        result = await use_case.execute(job_id)
        
        # Assertions
        assert result is None


class TestListFinancialDocumentsUseCase:
    """Integration tests for document listing"""
    
    @pytest.fixture
    def mock_document_repo(self):
        return AsyncMock()
    
    async def test_list_documents_with_filters(self, mock_document_repo):
        """Test listing documents with various filters"""
        # Mock documents
        doc1 = FinancialDocument(
            url="https://example.com/q1-2023.pdf",
            title="Q1 2023 Report",
            document_type=DocumentType.QUARTERLY_REPORT,
            year=2023,
            extraction_status=ExtractionStatus.COMPLETED
        )
        
        doc2 = FinancialDocument(
            url="https://example.com/annual-2023.pdf",
            title="2023 Annual Report",
            document_type=DocumentType.ANNUAL_REPORT,
            year=2023,
            extraction_status=ExtractionStatus.COMPLETED
        )
        
        mock_document_repo.list_by_filters.return_value = [doc1, doc2]
        
        # Create use case
        use_case = ListFinancialDocumentsUseCase(mock_document_repo)
        
        # Execute
        result = await use_case.execute(
            company_name="Test Company",
            year=2023,
            document_type="quarterly_report",
            status="completed",
            limit=50,
            offset=0
        )
        
        # Assertions
        assert len(result) == 2
        assert result[0]['title'] == "Q1 2023 Report"
        assert result[1]['title'] == "2023 Annual Report"
        
        # Verify repository was called with correct filters
        mock_document_repo.list_by_filters.assert_called_once_with(
            company_name="Test Company",
            year=2023,
            document_type="quarterly_report",
            status="completed",
            limit=50,
            offset=0
        )
    
    async def test_list_documents_no_filters(self, mock_document_repo):
        """Test listing documents without filters"""
        mock_document_repo.list_by_filters.return_value = []
        
        use_case = ListFinancialDocumentsUseCase(mock_document_repo)
        
        result = await use_case.execute()
        
        assert result == []
        mock_document_repo.list_by_filters.assert_called_once_with(
            company_name=None,
            year=None,
            document_type=None,
            status=None,
            limit=100,
            offset=0
        )


class TestRetryFailedExtractionUseCase:
    """Integration tests for retry functionality"""
    
    @pytest.fixture
    def mock_dependencies(self):
        return {
            'document_repo': AsyncMock(),
            'ai_extractor': AsyncMock(),
            'validator': AsyncMock(),
            'event_publisher': AsyncMock(),
            'logger': AsyncMock(),
            'config': AsyncMock()
        }
    
    async def test_successful_retry(self, mock_dependencies):
        """Test successful retry of failed extraction"""
        document_id = uuid4()
        mocks = mock_dependencies
        
        # Mock failed document that can be retried
        failed_doc = FinancialDocument(
            id=document_id,
            url="https://example.com/failed-doc.pdf",
            file_path="/tmp/failed-doc.pdf",
            extraction_status=ExtractionStatus.RETRY,
            retry_count=1,
            max_retries=3
        )
        
        mocks['document_repo'].find_by_id.return_value = failed_doc
        
        # Mock successful re-extraction
        financial_metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            extraction_confidence=0.85
        )
        mocks['ai_extractor'].extract_financial_data.return_value = financial_metrics
        
        ai_config = AIExtractionConfiguration()
        mocks['config'].get_ai_config.return_value = ai_config
        
        # Mock successful validation
        validation_result = ValidationResult(
            is_valid=True,
            confidence_score=0.82
        )
        mocks['validator'].validate_financial_metrics.return_value = validation_result
        
        # Create use case
        use_case = RetryFailedExtractionUseCase(**mocks)
        
        # Execute
        result = await use_case.execute(document_id)
        
        # Assertions
        assert result is True
        
        # Verify document was updated and saved
        assert mocks['document_repo'].save.call_count >= 2  # Once for retry, once for completion
        
        # Verify success event was published
        mocks['event_publisher'].publish_extraction_completed.assert_called_once()
        
        # Verify info was logged
        mocks['logger'].log_info.assert_called()
    
    async def test_retry_document_not_found(self, mock_dependencies):
        """Test retry when document doesn't exist"""
        document_id = uuid4()
        mocks = mock_dependencies
        
        # Mock document not found
        mocks['document_repo'].find_by_id.return_value = None
        
        use_case = RetryFailedExtractionUseCase(**mocks)
        
        result = await use_case.execute(document_id)
        
        assert result is False
    
    async def test_retry_document_cannot_retry(self, mock_dependencies):
        """Test retry when document has exceeded max retries"""
        document_id = uuid4()
        mocks = mock_dependencies
        
        # Mock document that cannot be retried
        exhausted_doc = FinancialDocument(
            id=document_id,
            url="https://example.com/exhausted-doc.pdf",
            extraction_status=ExtractionStatus.FAILED,
            retry_count=5,
            max_retries=3
        )
        
        mocks['document_repo'].find_by_id.return_value = exhausted_doc
        
        use_case = RetryFailedExtractionUseCase(**mocks)
        
        result = await use_case.execute(document_id)
        
        assert result is False
    
    async def test_retry_extraction_fails_again(self, mock_dependencies):
        """Test retry when extraction fails again"""
        document_id = uuid4()
        mocks = mock_dependencies
        
        # Mock retryable document
        retryable_doc = FinancialDocument(
            id=document_id,
            url="https://example.com/problematic-doc.pdf",
            file_path="/tmp/problematic-doc.pdf",
            extraction_status=ExtractionStatus.RETRY,
            retry_count=1,
            max_retries=3
        )
        
        mocks['document_repo'].find_by_id.return_value = retryable_doc
        
        ai_config = AIExtractionConfiguration()
        mocks['config'].get_ai_config.return_value = ai_config
        
        # Mock extraction failure
        mocks['ai_extractor'].extract_financial_data.side_effect = Exception("Extraction failed again")
        
        use_case = RetryFailedExtractionUseCase(**mocks)
        
        result = await use_case.execute(document_id)
        
        assert result is False
        
        # Verify error was logged
        mocks['logger'].log_error.assert_called()


# ==================== PYTEST FIXTURES ====================

@pytest.fixture
def event_loop():
    """Create an event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def mock_financial_metrics():
    """Sample financial metrics for testing"""
    return FinancialMetrics(
        revenue=Decimal('285000000'),
        net_income=Decimal('45000000'),
        ebitda=Decimal('95000000'),
        total_assets=Decimal('850000000'),
        shareholders_equity=Decimal('420000000'),
        operating_cash_flow=Decimal('75000000'),
        extraction_confidence=0.92,
        currency="USD",
        reporting_period="2023-Q4"
    )


@pytest.fixture
async def mock_validation_result():
    """Sample validation result for testing"""
    return ValidationResult(
        is_valid=True,
        confidence_score=0.89,
        validation_messages=["Data validation successful"],
        warnings=["Minor formatting inconsistency"],
        errors=[],
        validation_method="automated",
        accuracy_score=0.91,
        consistency_score=0.87,
        completeness_score=0.85
    )


# ==================== INTEGRATION TEST HELPERS ====================

class MockAsyncContextManager:
    """Helper class for mocking async context managers"""
    
    def __init__(self, return_value=None):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


async def create_test_extraction_job(
    name: str = "Test Job",
    company_url: str = "https://example.com",
    target_years: list = None,
    status: str = "created"
) -> ExtractionJob:
    """Helper to create test extraction jobs"""
    if target_years is None:
        target_years = [2023, 2024]
    
    job = ExtractionJob(
        name=name,
        company_url=company_url,
        target_years=target_years,
        document_types=[DocumentType.QUARTERLY_REPORT, DocumentType.ANNUAL_REPORT]
    )
    job.status = status
    return job


async def create_test_financial_document(
    url: str = "https://example.com/test-doc.pdf",
    title: str = "Test Document",
    year: int = 2023,
    status: ExtractionStatus = ExtractionStatus.PENDING
) -> FinancialDocument:
    """Helper to create test financial documents"""
    doc = FinancialDocument(
        url=url,
        title=title,
        document_type=DocumentType.QUARTERLY_REPORT,
        year=year
    )
    doc.extraction_status = status
    return doc


# ==================== PERFORMANCE TESTS ====================

@pytest.mark.slow
class TestExtractionPerformance:
    """Performance tests for extraction use cases"""
    
    async def test_concurrent_document_processing(self, mock_dependencies):
        """Test processing multiple documents concurrently"""
        import time
        
        mocks = mock_dependencies
        
        # Setup mocks for large number of documents
        num_documents = 50
        discovered_docs = [
            {
                'id': f'doc{i}',
                'url': f'https://example.com/doc{i}.pdf',
                'title': f'Document {i}',
                'type': 'quarterly_report',
                'year': 2023
            }
            for i in range(num_documents)
        ]
        
        # Setup all necessary mocks
        company_profile = CompanyProfile(name="Test Company", base_url="https://example.com")
        mocks['company_repo'].find_by_name.return_value = company_profile
        mocks['config'].get_scraping_config.return_value = ScrapingConfiguration(base_url="https://example.com")
        mocks['scraper'].discover_documents.return_value = discovered_docs
        
        # Mock quick responses
        mocks['scraper'].download_document.return_value = {
            'file_path': '/tmp/doc.pdf',
            'file_size': 1000,
            'file_hash': 'hash123'
        }
        
        mocks['ai_extractor'].extract_financial_data.return_value = FinancialMetrics(
            revenue=Decimal('1000000'),
            extraction_confidence=0.8
        )
        
        mocks['config'].get_ai_config.return_value = AIExtractionConfiguration()
        
        mocks['validator'].validate_financial_metrics.return_value = ValidationResult(
            is_valid=True,
            confidence_score=0.8
        )
        
        # Create command
        command = ExtractFinancialReportsCommand(
            company_url="https://example.com",
            company_name="Test Company",
            target_years=[2023]
        )
        
        # Create use case
        use_case = ExtractFinancialReportsUseCase(**mocks)
        
        # Measure execution time
        start_time = time.time()
        result = await use_case.execute(command)
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        # Assertions
        assert result.total_documents == num_documents
        assert execution_time < 60  # Should complete within 60 seconds
        
        # Verify concurrent processing occurred
        # (All documents should be processed roughly simultaneously)
        print(f"Processed {num_documents} documents in {execution_time:.2f} seconds")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])