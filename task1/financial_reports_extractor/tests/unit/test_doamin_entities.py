"""
Unit Tests for Domain Entities
Tests the core business logic without external dependencies
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from src.domain.entities import (
    FinancialDocument, 
    ExtractionJob, 
    CompanyProfile,
    DocumentType, 
    ExtractionStatus, 
    Quarter
)
from src.domain.value_objects import (
    FinancialMetrics,
    ValidationResult,
    ScrapingConfiguration,
    AIExtractionConfiguration,
    ExtractionContext
)


class TestFinancialDocument:
    """Test cases for FinancialDocument entity"""
    
    def test_financial_document_creation(self):
        """Test basic financial document creation"""
        doc = FinancialDocument(
            url="https://example.com/report.pdf",
            title="Q4 2023 Report",
            document_type=DocumentType.QUARTERLY_REPORT,
            year=2023,
            quarter=Quarter.Q4
        )
        
        assert doc.url == "https://example.com/report.pdf"
        assert doc.title == "Q4 2023 Report"
        assert doc.document_type == DocumentType.QUARTERLY_REPORT
        assert doc.year == 2023
        assert doc.quarter == Quarter.Q4
        assert doc.extraction_status == ExtractionStatus.PENDING
        assert doc.validation_score == 0.0
        assert doc.confidence_level == 0.0
        assert doc.retry_count == 0
        assert isinstance(doc.created_at, datetime)
        assert isinstance(doc.updated_at, datetime)
    
    def test_invalid_year_raises_error(self):
        """Test that invalid year raises ValueError"""
        with pytest.raises(ValueError, match="Año inválido"):
            FinancialDocument(
                url="https://example.com/report.pdf",
                year=1800  # Invalid year
            )
    
    def test_invalid_url_raises_error(self):
        """Test that invalid URL raises ValueError"""
        with pytest.raises(ValueError, match="URL inválida"):
            FinancialDocument(
                url="not-a-valid-url",
                year=2023
            )
    
    def test_mark_as_downloaded(self):
        """Test marking document as downloaded"""
        doc = FinancialDocument(
            url="https://example.com/report.pdf",
            year=2023
        )
        
        initial_updated_at = doc.updated_at
        
        doc.mark_as_downloaded(
            file_path="/path/to/file.pdf",
            file_size=1024,
            file_hash="abc123"
        )
        
        assert doc.file_path == "/path/to/file.pdf"
        assert doc.file_size_bytes == 1024
        assert doc.file_hash == "abc123"
        assert doc.extraction_status == ExtractionStatus.PROCESSING
        assert doc.updated_at > initial_updated_at
    
    def test_mark_as_completed(self):
        """Test marking document as completed"""
        doc = FinancialDocument(
            url="https://example.com/report.pdf",
            year=2023
        )
        
        doc.mark_as_completed(
            validation_score=0.95,
            confidence_level=0.88
        )
        
        assert doc.validation_score == 0.95
        assert doc.confidence_level == 0.88
        assert doc.extraction_status == ExtractionStatus.COMPLETED
    
    def test_mark_as_failed(self):
        """Test marking document as failed"""
        doc = FinancialDocument(
            url="https://example.com/report.pdf",
            year=2023,
            max_retries=3
        )
        
        # First failure - should go to retry
        doc.mark_as_failed("Network error")
        assert doc.extraction_status == ExtractionStatus.RETRY
        assert doc.retry_count == 1
        assert "Network error" in doc.error_messages
        
        # More failures
        doc.mark_as_failed("Another error")
        doc.mark_as_failed("Yet another error")
        
        # Final failure - should go to failed
        doc.mark_as_failed("Final error")
        assert doc.extraction_status == ExtractionStatus.FAILED
        assert doc.retry_count == 4
        assert len(doc.error_messages) == 4
    
    def test_can_retry(self):
        """Test retry logic"""
        doc = FinancialDocument(
            url="https://example.com/report.pdf",
            year=2023,
            max_retries=2
        )
        
        # Initially cannot retry (not failed)
        assert not doc.can_retry()
        
        # After first failure, can retry
        doc.mark_as_failed("Error 1")
        assert doc.can_retry()
        
        # After second failure, can retry
        doc.mark_as_failed("Error 2")
        assert doc.can_retry()
        
        # After exceeding max retries, cannot retry
        doc.mark_as_failed("Error 3")
        assert not doc.can_retry()
    
    def test_is_quarterly(self):
        """Test quarterly document detection"""
        quarterly_doc = FinancialDocument(
            url="https://example.com/q1.pdf",
            document_type=DocumentType.QUARTERLY_REPORT,
            year=2023,
            quarter=Quarter.Q1
        )
        
        annual_doc = FinancialDocument(
            url="https://example.com/annual.pdf",
            document_type=DocumentType.ANNUAL_REPORT,
            year=2023
        )
        
        assert quarterly_doc.is_quarterly()
        assert not annual_doc.is_quarterly()
    
    def test_get_period_identifier(self):
        """Test period identifier generation"""
        quarterly_doc = FinancialDocument(
            url="https://example.com/q1.pdf",
            document_type=DocumentType.QUARTERLY_REPORT,
            year=2023,
            quarter=Quarter.Q1
        )
        
        annual_doc = FinancialDocument(
            url="https://example.com/annual.pdf",
            document_type=DocumentType.ANNUAL_REPORT,
            year=2023
        )
        
        assert quarterly_doc.get_period_identifier() == "2023-Q1"
        assert annual_doc.get_period_identifier() == "2023-Annual"


class TestExtractionJob:
    """Test cases for ExtractionJob entity"""
    
    def test_extraction_job_creation(self):
        """Test basic extraction job creation"""
        job = ExtractionJob(
            name="Test Job",
            company_url="https://example.com",
            target_years=[2022, 2023],
            document_types=[DocumentType.QUARTERLY_REPORT]
        )
        
        assert job.name == "Test Job"
        assert job.company_url == "https://example.com"
        assert job.target_years == [2022, 2023]
        assert job.document_types == [DocumentType.QUARTERLY_REPORT]
        assert job.status == "created"
        assert job.progress_percentage == 0.0
        assert job.documents_processed == 0
        assert job.documents_successful == 0
        assert job.documents_failed == 0
    
    def test_start_job(self):
        """Test starting a job"""
        job = ExtractionJob(name="Test Job", company_url="https://example.com")
        
        job.start_job()
        
        assert job.status == "running"
        assert job.started_at is not None
        assert job.progress_percentage == 0.0
    
    def test_complete_job(self):
        """Test completing a job"""
        job = ExtractionJob(name="Test Job", company_url="https://example.com")
        job.start_job()
        
        job.complete_job()
        
        assert job.status == "completed"
        assert job.completed_at is not None
        assert job.progress_percentage == 100.0
    
    def test_fail_job(self):
        """Test failing a job"""
        job = ExtractionJob(name="Test Job", company_url="https://example.com")
        
        job.fail_job("Network connection failed")
        
        assert job.status == "failed"
        assert job.completed_at is not None
        assert "Network connection failed" in job.configuration.get('errors', [])
    
    def test_add_document(self):
        """Test adding documents to job"""
        job = ExtractionJob(name="Test Job", company_url="https://example.com")
        doc_id1 = uuid4()
        doc_id2 = uuid4()
        
        job.add_document(doc_id1)
        job.add_document(doc_id2)
        job.add_document(doc_id1)  # Duplicate should be ignored
        
        assert len(job.document_ids) == 2
        assert doc_id1 in job.document_ids
        assert doc_id2 in job.document_ids
        assert job.total_documents_found == 2
    
    def test_record_document_processed(self):
        """Test recording document processing"""
        job = ExtractionJob(name="Test Job", company_url="https://example.com")
        job.total_documents_found = 5
        
        # Process successful document
        job.record_document_processed(success=True)
        assert job.documents_processed == 1
        assert job.documents_successful == 1
        assert job.documents_failed == 0
        assert job.progress_percentage == 20.0  # 1/5 * 100
        
        # Process failed document
        job.record_document_processed(success=False)
        assert job.documents_processed == 2
        assert job.documents_successful == 1
        assert job.documents_failed == 1
        assert job.progress_percentage == 40.0  # 2/5 * 100
    
    def test_get_success_rate(self):
        """Test success rate calculation"""
        job = ExtractionJob(name="Test Job", company_url="https://example.com")
        
        # No documents processed
        assert job.get_success_rate() == 0.0
        
        # Process some documents
        job.documents_processed = 10
        job.documents_successful = 8
        job.documents_failed = 2
        
        assert job.get_success_rate() == 80.0
    
    def test_get_duration_seconds(self):
        """Test job duration calculation"""
        job = ExtractionJob(name="Test Job", company_url="https://example.com")
        
        # Not started
        assert job.get_duration_seconds() is None
        
        # Started but not completed
        job.start_job()
        duration = job.get_duration_seconds()
        assert duration is not None
        assert duration >= 0
        
        # Completed
        job.complete_job()
        duration = job.get_duration_seconds()
        assert duration is not None
        assert duration >= 0


class TestCompanyProfile:
    """Test cases for CompanyProfile entity"""
    
    def test_company_profile_creation(self):
        """Test basic company profile creation"""
        profile = CompanyProfile(
            name="Test Company",
            ticker_symbol="TEST",
            base_url="https://testcompany.com",
            reports_url="https://testcompany.com/investors"
        )
        
        assert profile.name == "Test Company"
        assert profile.ticker_symbol == "TEST"
        assert profile.base_url == "https://testcompany.com"
        assert profile.reports_url == "https://testcompany.com/investors"
        assert profile.scraping_success_rate == 0.0
        assert profile.total_documents_found == 0
    
    def test_update_scraping_patterns(self):
        """Test updating scraping patterns"""
        profile = CompanyProfile(
            name="Test Company",
            base_url="https://testcompany.com"
        )
        
        initial_updated_at = profile.updated_at
        
        new_patterns = {
            'url_patterns': ['pattern1', 'pattern2'],
            'css_selectors': ['selector1', 'selector2']
        }
        
        profile.update_scraping_patterns(new_patterns)
        
        assert 'pattern1' in profile.url_patterns
        assert 'selector1' in profile.css_selectors
        assert profile.updated_at > initial_updated_at
    
    def test_record_scraping_attempt(self):
        """Test recording scraping attempts"""
        profile = CompanyProfile(
            name="Test Company",
            base_url="https://testcompany.com"
        )
        
        # Successful attempt
        profile.record_scraping_attempt(success=True, documents_found=5)
        assert profile.last_scraped_at is not None
        assert profile.total_documents_found == 5
        assert profile.scraping_success_rate == 50.0  # (0 + 100) / 2
        
        # Failed attempt
        profile.record_scraping_attempt(success=False, documents_found=0)
        assert profile.scraping_success_rate == 25.0  # 50 / 2


class TestFinancialMetrics:
    """Test cases for FinancialMetrics value object"""
    
    def test_financial_metrics_creation(self):
        """Test basic financial metrics creation"""
        metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            net_income=Decimal('150000'),
            ebitda=Decimal('200000'),
            total_assets=Decimal('5000000'),
            extraction_confidence=0.92,
            currency="USD",
            reporting_period="2023-Q4"
        )
        
        assert metrics.revenue == Decimal('1000000')
        assert metrics.net_income == Decimal('150000')
        assert metrics.ebitda == Decimal('200000')
        assert metrics.total_assets == Decimal('5000000')
        assert metrics.extraction_confidence == 0.92
        assert metrics.currency == "USD"
        assert metrics.reporting_period == "2023-Q4"
    
    def test_financial_metrics_validation_empty(self):
        """Test that at least one metric must be present"""
        with pytest.raises(ValueError, match="Al menos una métrica financiera debe estar presente"):
            FinancialMetrics(
                extraction_confidence=0.5,
                currency="USD"
            )
    
    def test_confidence_score_validation(self):
        """Test confidence score validation"""
        with pytest.raises(ValueError, match="Confidence score debe estar entre 0.0 y 1.0"):
            FinancialMetrics(
                revenue=Decimal('1000000'),
                extraction_confidence=1.5  # Invalid
            )
    
    def test_get_completeness_score(self):
        """Test completeness score calculation"""
        # Full metrics
        full_metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            net_income=Decimal('150000'),
            ebitda=Decimal('200000'),
            total_assets=Decimal('5000000'),
            total_liabilities=Decimal('3000000'),
            shareholders_equity=Decimal('2000000'),
            cash_and_equivalents=Decimal('500000'),
            operating_cash_flow=Decimal('300000'),
            gross_profit=Decimal('400000'),
            operating_income=Decimal('250000'),
            ebit=Decimal('220000'),
            free_cash_flow=Decimal('200000'),
            earnings_per_share=Decimal('2.5'),
            book_value_per_share=Decimal('15.0'),
            dividends_per_share=Decimal('1.0'),
            debt_to_equity_ratio=Decimal('1.5'),
            current_ratio=Decimal('2.0'),
            return_on_equity=Decimal('0.15'),
            return_on_assets=Decimal('0.08'),
            investing_cash_flow=Decimal('-100000'),
            extraction_confidence=0.95
        )
        
        assert full_metrics.get_completeness_score() == 1.0
        
        # Partial metrics
        partial_metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            net_income=Decimal('150000'),
            extraction_confidence=0.8
        )
        
        completeness = partial_metrics.get_completeness_score()
        assert 0.0 < completeness < 1.0
    
    def test_get_key_metrics(self):
        """Test key metrics extraction"""
        metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            net_income=Decimal('150000'),
            ebitda=Decimal('200000'),
            total_assets=Decimal('5000000'),
            extraction_confidence=0.92
        )
        
        key_metrics = metrics.get_key_metrics()
        
        assert key_metrics['revenue'] == Decimal('1000000')
        assert key_metrics['net_income'] == Decimal('150000')
        assert key_metrics['ebitda'] == Decimal('200000')
        assert key_metrics['total_assets'] == Decimal('5000000')
    
    def test_is_profitable(self):
        """Test profitability check"""
        profitable_metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            net_income=Decimal('150000'),
            extraction_confidence=0.9
        )
        
        loss_metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            net_income=Decimal('-50000'),
            extraction_confidence=0.9
        )
        
        no_income_metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            extraction_confidence=0.9
        )
        
        assert profitable_metrics.is_profitable() is True
        assert loss_metrics.is_profitable() is False
        assert no_income_metrics.is_profitable() is None
    
    def test_to_dict(self):
        """Test dictionary conversion"""
        metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            net_income=Decimal('150000'),
            extraction_confidence=0.92,
            currency="USD",
            reporting_period="2023-Q4"
        )
        
        metrics_dict = metrics.to_dict()
        
        assert metrics_dict['revenue'] == 1000000.0
        assert metrics_dict['net_income'] == 150000.0
        assert metrics_dict['extraction_confidence'] == 0.92
        assert metrics_dict['currency'] == "USD"
        assert metrics_dict['reporting_period'] == "2023-Q4"
        assert 'completeness_score' in metrics_dict


class TestValidationResult:
    """Test cases for ValidationResult value object"""
    
    def test_validation_result_creation(self):
        """Test basic validation result creation"""
        result = ValidationResult(
            is_valid=True,
            confidence_score=0.95,
            validation_messages=["All checks passed"],
            warnings=["Minor issue detected"],
            errors=[],
            validation_method="automated"
        )
        
        assert result.is_valid is True
        assert result.confidence_score == 0.95
        assert "All checks passed" in result.validation_messages
        assert "Minor issue detected" in result.warnings
        assert len(result.errors) == 0
    
    def test_confidence_score_validation(self):
        """Test confidence score validation"""
        with pytest.raises(ValueError, match="Confidence score debe estar entre 0.0 y 1.0"):
            ValidationResult(
                is_valid=True,
                confidence_score=1.5  # Invalid
            )
    
    def test_get_overall_quality_score(self):
        """Test overall quality score calculation"""
        result = ValidationResult(
            is_valid=True,
            confidence_score=0.9,
            accuracy_score=0.85,
            consistency_score=0.88,
            completeness_score=0.92
        )
        
        quality_score = result.get_overall_quality_score()
        expected = (0.9 + 0.85 + 0.88 + 0.92) / 4
        assert abs(quality_score - expected) < 0.001
    
    def test_has_critical_errors(self):
        """Test critical error detection"""
        critical_result = ValidationResult(
            is_valid=False,
            confidence_score=0.3,
            errors=["Critical data corruption detected", "Invalid format"]
        )
        
        non_critical_result = ValidationResult(
            is_valid=False,
            confidence_score=0.7,
            errors=["Minor calculation error", "Missing optional field"]
        )
        
        assert critical_result.has_critical_errors() is True
        assert non_critical_result.has_critical_errors() is False
    
    def test_get_summary(self):
        """Test validation summary"""
        result = ValidationResult(
            is_valid=True,
            confidence_score=0.92,
            accuracy_score=0.88,
            warnings=["Minor issue"],
            errors=[]
        )
        
        summary = result.get_summary()
        
        assert summary['is_valid'] is True
        assert summary['confidence_score'] == 0.92
        assert summary['total_errors'] == 0
        assert summary['total_warnings'] == 1
        assert summary['has_critical_errors'] is False
        assert 'validation_timestamp' in summary


class TestScrapingConfiguration:
    """Test cases for ScrapingConfiguration value object"""
    
    def test_scraping_configuration_creation(self):
        """Test basic scraping configuration creation"""
        config = ScrapingConfiguration(
            base_url="https://example.com",
            max_pages=15,
            delay_between_requests=2.5,
            document_links_selector="a[href*='.pdf']"
        )
        
        assert config.base_url == "https://example.com"
        assert config.max_pages == 15
        assert config.delay_between_requests == 2.5
        assert config.document_links_selector == "a[href*='.pdf']"
    
    def test_base_url_validation(self):
        """Test base URL validation"""
        with pytest.raises(ValueError, match="base_url debe comenzar con http"):
            ScrapingConfiguration(
                base_url="invalid-url",
                max_pages=10
            )
    
    def test_max_pages_validation(self):
        """Test max pages validation"""
        with pytest.raises(ValueError, match="max_pages debe ser mayor a 0"):
            ScrapingConfiguration(
                base_url="https://example.com",
                max_pages=0
            )
    
    def test_delay_validation(self):
        """Test delay validation"""
        with pytest.raises(ValueError, match="delay_between_requests no puede ser negativo"):
            ScrapingConfiguration(
                base_url="https://example.com",
                delay_between_requests=-1.0
            )
    
    def test_should_process_url(self):
        """Test URL processing logic"""
        config = ScrapingConfiguration(
            base_url="https://example.com",
            url_patterns=['report', 'financial'],
            exclude_patterns=['draft', 'preview']
        )
        
        assert config.should_process_url("https://example.com/financial-report.pdf") is True
        assert config.should_process_url("https://example.com/draft-report.pdf") is False
        assert config.should_process_url("https://example.com/other-document.pdf") is False
    
    def test_get_selenium_options(self):
        """Test Selenium options generation"""
        config = ScrapingConfiguration(
            base_url="https://example.com",
            use_headless=True,
            window_size=(1920, 1080),
            user_agent="TestAgent/1.0"
        )
        
        options = config.get_selenium_options()
        
        assert options['headless'] is True
        assert options['window_size'] == (1920, 1080)
        assert options['user_agent'] == "TestAgent/1.0"


# ==================== PYTEST FIXTURES ====================

@pytest.fixture
def sample_financial_document():
    """Sample financial document for testing"""
    return FinancialDocument(
        url="https://example.com/q4-2023-report.pdf",
        title="Q4 2023 Financial Results",
        document_type=DocumentType.QUARTERLY_REPORT,
        year=2023,
        quarter=Quarter.Q4
    )


@pytest.fixture
def sample_financial_metrics():
    """Sample financial metrics for testing"""
    return FinancialMetrics(
        revenue=Decimal('1000000'),
        net_income=Decimal('150000'),
        ebitda=Decimal('200000'),
        total_assets=Decimal('5000000'),
        shareholders_equity=Decimal('2000000'),
        operating_cash_flow=Decimal('300000'),
        extraction_confidence=0.92,
        currency="USD",
        reporting_period="2023-Q4"
    )


@pytest.fixture
def sample_extraction_job():
    """Sample extraction job for testing"""
    return ExtractionJob(
        name="Test Extraction Job",
        company_url="https://example.com/investors",
        target_years=[2022, 2023, 2024],
        document_types=[DocumentType.QUARTERLY_REPORT, DocumentType.ANNUAL_REPORT]
    )


@pytest.fixture
def sample_company_profile():
    """Sample company profile for testing"""
    return CompanyProfile(
        name="Example Corp",
        ticker_symbol="EXAM",
        base_url="https://example.com",
        reports_url="https://example.com/investors/reports",
        sector="Technology",
        industry="Software"
    )


# ==================== PARAMETRIZED TESTS ====================

@pytest.mark.parametrize("year,should_be_valid", [
    (2000, True),
    (2023, True),
    (2024, True),
    (1999, False),
    (2030, False),
    (1800, False)
])
def test_financial_document_year_validation(year, should_be_valid):
    """Test financial document year validation with various inputs"""
    if should_be_valid:
        doc = FinancialDocument(
            url="https://example.com/report.pdf",
            year=year
        )
        assert doc.year == year
    else:
        with pytest.raises(ValueError):
            FinancialDocument(
                url="https://example.com/report.pdf",
                year=year
            )


@pytest.mark.parametrize("confidence,should_be_valid", [
    (0.0, True),
    (0.5, True),
    (1.0, True),
    (-0.1, False),
    (1.1, False),
    (2.0, False)
])
def test_financial_metrics_confidence_validation(confidence, should_be_valid):
    """Test financial metrics confidence validation"""
    if should_be_valid:
        metrics = FinancialMetrics(
            revenue=Decimal('1000000'),
            extraction_confidence=confidence
        )
        assert metrics.extraction_confidence == confidence
    else:
        with pytest.raises(ValueError):
            FinancialMetrics(
                revenue=Decimal('1000000'),
                extraction_confidence=confidence
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])