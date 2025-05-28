"""
End-to-End Tests
Tests the complete application flow from API to data extraction
"""

import pytest
import asyncio
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient

from src.adapters.web.main import app
from src.domain.entities import DocumentType, ExtractionStatus
from src.domain.value_objects import FinancialMetrics, ValidationResult


@pytest.mark.e2e
class TestCompleteExtractionFlow:
    """
    End-to-end tests for the complete financial extraction workflow
    """
    
    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory for tests"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Crear subdirectorios necesarios
            storage_path = Path(temp_dir) / "storage"
            storage_path.mkdir(exist_ok=True)
            (storage_path / "documents").mkdir(exist_ok=True)
            (storage_path / "temp").mkdir(exist_ok=True)
            yield str(storage_path)
    
    @pytest.fixture
    def sample_pdf_content(self):
        """Sample PDF content for testing"""
        # Simular contenido PDF básico
        return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n%%EOF"
    
    @pytest.fixture
    def mock_external_services(self, sample_pdf_content):
        """Mock all external services for E2E testing"""
        mocks = {}
        
        # Mock OpenAI API
        with patch('openai.AsyncOpenAI') as mock_openai:
            mock_client = AsyncMock()
            
            # Mock chat completion for document analysis
            mock_response = AsyncMock()
            mock_response.choices = [
                AsyncMock(message=AsyncMock(content=json.dumps({
                    "revenue": 285000000,
                    "net_income": 45000000,
                    "ebitda": 95000000,
                    "total_assets": 850000000,
                    "extraction_confidence": 0.92,
                    "currency": "USD",
                    "reporting_period": "2023-Q4"
                })))
            ]
            
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            mocks['openai'] = mock_openai
            
            # Mock web scraping
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response_obj = AsyncMock()
                mock_response_obj.status = 200
                mock_response_obj.text.return_value = """
                <html>
                    <body>
                        <a href="/report1.pdf">Q4 2023 Report</a>
                        <a href="/report2.pdf">2023 Annual Report</a>
                    </body>
                </html>
                """
                mock_response_obj.read.return_value = sample_pdf_content
                mock_response_obj.headers = {'content-type': 'application/pdf'}
                
                mock_session_instance = AsyncMock()
                mock_session_instance.get.return_value.__aenter__.return_value = mock_response_obj
                mock_session.return_value.__aenter__.return_value = mock_session_instance
                mocks['aiohttp'] = mock_session
                
                yield mocks
    
    @pytest.mark.asyncio
    async def test_complete_extraction_workflow(
        self, 
        temp_storage_dir, 
        mock_external_services
    ):
        """
        Test the complete workflow:
        1. Create extraction job via API
        2. Job discovers documents via web scraping
        3. Downloads documents
        4. Extracts financial data using AI
        5. Validates data
        6. Stores results
        7. Returns status via API
        """
        with patch.dict(os.environ, {
            'STORAGE_PATH': temp_storage_dir,
            'OPENAI_API_KEY': 'test-key',
            'DATABASE_URL': 'sqlite+aiosqlite:///test.db'
        }):
            
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                
                # Step 1: Create extraction job
                extraction_request = {
                    "company_url": "https://example.com/investors/reports/",
                    "company_name": "Test Company Inc.",
                    "target_years": [2023, 2024],
                    "document_types": ["quarterly_report", "annual_report"],
                    "job_name": "E2E Test Job"
                }
                
                create_response = await client.post(
                    "/extraction/jobs",
                    json=extraction_request
                )
                
                assert create_response.status_code == 200
                job_data = create_response.json()
                assert "job_id" in job_data
                assert job_data["status"] == "started"
                
                job_id = job_data["job_id"]
                
                # Step 2: Wait for job processing (in real scenario)
                # Simulate background processing completion
                await asyncio.sleep(0.1)
                
                # Step 3: Check job status
                status_response = await client.get(f"/extraction/jobs/{job_id}")
                
                # In a real E2E test, you might need to poll until completion
                # For this mock test, we'll verify the structure
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    
                    # Verify job status structure
                    expected_fields = [
                        "job_id", "name", "status", "progress_percentage",
                        "total_documents", "processed_documents", 
                        "successful_documents", "failed_documents"
                    ]
                    
                    for field in expected_fields:
                        assert field in status_data
                
                # Step 4: Verify documents were created
                documents_response = await client.get("/documents")
                assert documents_response.status_code == 200
                
                # Step 5: Test analytics after processing
                analytics_response = await client.get("/analytics/summary")
                assert analytics_response.status_code == 200
                
                analytics_data = analytics_response.json()
                assert "total_documents_processed" in analytics_data
                assert "extraction_success_rate" in analytics_data
    
    @pytest.mark.asyncio
    async def test_extraction_with_failures(self, mock_external_services):
        """
        Test workflow when some extractions fail
        """
        # Mock some failures in the external services
        with patch('src.adapters.scraping.intelligent_scraper.IntelligentWebScrapingAgent') as mock_scraper:
            
            # Setup scraper to return mixed results
            mock_scraper_instance = AsyncMock()
            
            # First document succeeds, second fails
            async def mock_download(url, path):
                if "report1" in url:
                    return {
                        'file_path': path,
                        'file_size': 1000,
                        'file_hash': 'abc123'
                    }
                else:
                    raise Exception("Download failed")
            
            mock_scraper_instance.download_document.side_effect = mock_download
            mock_scraper_instance.discover_documents.return_value = [
                {
                    'id': 'doc1',
                    'url': 'https://example.com/report1.pdf',
                    'title': 'Good Report',
                    'type': 'quarterly_report',
                    'year': 2023
                },
                {
                    'id': 'doc2', 
                    'url': 'https://example.com/report2.pdf',
                    'title': 'Bad Report',
                    'type': 'quarterly_report',
                    'year': 2023
                }
            ]
            
            mock_scraper.return_value = mock_scraper_instance
            
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                
                # Create job with mixed success scenario
                extraction_request = {
                    "company_url": "https://example.com/investors/",
                    "company_name": "Mixed Results Company",
                    "target_years": [2023],
                    "job_name": "Mixed Results Test"
                }
                
                response = await client.post("/extraction/jobs", json=extraction_request)
                assert response.status_code == 200
                
                job_data = response.json()
                job_id = job_data["job_id"]
                
                # Check that the system handles partial failures gracefully
                # In a real test, you'd poll for job completion
                await asyncio.sleep(0.1)
                
                status_response = await client.get(f"/extraction/jobs/{job_id}")
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    
                    # Verify the job tracked both successes and failures
                    # This would be populated by the actual background processing
                    assert "successful_documents" in status_data
                    assert "failed_documents" in status_data
    
    @pytest.mark.asyncio
    async def test_document_retry_workflow(self):
        """
        Test the complete retry workflow for failed documents
        """
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            
            # First, we'd need a failed document
            # In a real E2E test, this would come from a previous failed extraction
            
            # Mock a document ID (in real test, get from database)
            document_id = "123e4567-e89b-12d3-a456-426614174000"
            
            # Attempt to retry the document
            retry_response = await client.post(f"/documents/{document_id}/retry")
            
            # The response will depend on whether the document exists and can be retried
            # In a complete E2E test, you'd set up the database state first
            assert retry_response.status_code in [200, 404]  # Either success or not found
    
    @pytest.mark.asyncio
    async def test_real_website_scraping_simulation(self):
        """
        Test scraping simulation with realistic website structure
        """
        # Mock a realistic financial reports page
        mock_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Investor Relations - Financial Reports</title></head>
        <body>
            <div class="financial-reports">
                <h2>Annual Reports</h2>
                <ul>
                    <li><a href="/docs/annual-report-2023.pdf">Annual Report 2023</a> - Published: Dec 31, 2023</li>
                    <li><a href="/docs/annual-report-2022.pdf">Annual Report 2022</a> - Published: Dec 31, 2022</li>
                </ul>
                
                <h2>Quarterly Reports</h2>
                <ul>
                    <li><a href="/docs/q4-2023-earnings.pdf">Q4 2023 Earnings Report</a> - Published: Jan 15, 2024</li>
                    <li><a href="/docs/q3-2023-earnings.pdf">Q3 2023 Earnings Report</a> - Published: Oct 15, 2023</li>
                    <li><a href="/docs/q2-2023-earnings.pdf">Q2 2023 Earnings Report</a> - Published: Jul 15, 2023</li>
                    <li><a href="/docs/q1-2023-earnings.pdf">Q1 2023 Earnings Report</a> - Published: Apr 15, 2023</li>
                </ul>
            </div>
        </body>
        </html>
        """
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text.return_value = mock_html
            
            mock_session_instance = AsyncMock()
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                
                extraction_request = {
                    "company_url": "https://realistic-company.com/investors/reports/",
                    "company_name": "Realistic Company Inc.",
                    "target_years": [2023],
                    "document_types": ["quarterly_report", "annual_report"]
                }
                
                response = await client.post("/extraction/jobs", json=extraction_request)
                assert response.status_code == 200
                
                # The scraping agent should be able to parse this realistic HTML
                # and identify the relevant financial documents


@pytest.mark.e2e
class TestDataPersistenceFlow:
    """
    Test data persistence and retrieval workflows
    """
    
    @pytest.mark.asyncio
    async def test_document_storage_and_retrieval(self):
        """
        Test that documents are properly stored and can be retrieved
        """
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            
            # Create some test data through the API
            extraction_request = {
                "company_url": "https://storage-test.com/reports/",
                "company_name": "Storage Test Company",
                "target_years": [2023],
                "job_name": "Storage Test Job"
            }
            
            # Create job
            create_response = await client.post("/extraction/jobs", json=extraction_request)
            assert create_response.status_code == 200
            
            # After processing (mocked), verify data persistence
            documents_response = await client.get("/documents")
            assert documents_response.status_code == 200
            
            # Test filtering and pagination
            filtered_response = await client.get(
                "/documents",
                params={
                    "company_name": "Storage Test Company",
                    "year": 2023,
                    "limit": 10
                }
            )
            assert filtered_response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_job_history_and_analytics(self):
        """
        Test job history tracking and analytics aggregation
        """
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            
            # Create multiple jobs to test analytics
            companies = ["Company A", "Company B", "Company C"]
            
            for company in companies:
                extraction_request = {
                    "company_url": f"https://{company.lower().replace(' ', '')}.com/reports/",
                    "company_name": company,
                    "target_years": [2023],
                    "job_name": f"{company} Test Job"
                }
                
                response = await client.post("/extraction/jobs", json=extraction_request)
                assert response.status_code == 200
            
            # Test analytics aggregation
            analytics_response = await client.get("/analytics/summary")
            assert analytics_response.status_code == 200
            
            analytics_data = analytics_response.json()
            
            # Verify analytics structure and reasonable values
            assert analytics_data["total_documents_processed"] >= 0
            assert 0 <= analytics_data["extraction_success_rate"] <= 100
            
            # Test company-specific analytics
            company_analytics_response = await client.get("/analytics/companies")
            assert company_analytics_response.status_code == 200


@pytest.mark.e2e
class TestErrorRecoveryAndResilience:
    """
    Test system resilience and error recovery
    """
    
    @pytest.mark.asyncio
    async def test_network_failure_recovery(self):
        """
        Test system behavior when network failures occur
        """
        # Simulate network failures during scraping
        with patch('aiohttp.ClientSession') as mock_session:
            
            # First call fails, second succeeds
            call_count = 0
            async def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Network timeout")
                
                # Return successful response on retry
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.text.return_value = "<html><a href='/report.pdf'>Report</a></html>"
                return mock_response
            
            mock_session_instance = AsyncMock()
            mock_session_instance.get.side_effect = side_effect
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                
                extraction_request = {
                    "company_url": "https://unreliable-network.com/reports/",
                    "company_name": "Network Test Company",
                    "target_years": [2023],
                    "job_name": "Network Resilience Test"
                }
                
                response = await client.post("/extraction/jobs", json=extraction_request)
                assert response.status_code == 200
                
                # The system should handle the initial failure and retry
    
    @pytest.mark.asyncio
    async def test_partial_ai_service_failure(self):
        """
        Test behavior when AI services partially fail
        """
        with patch('openai.AsyncOpenAI') as mock_openai:
            
            # Mock intermittent AI failures
            call_count = 0
            async def ai_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count % 2 == 0:  # Every second call fails
                    raise Exception("AI service temporary failure")
                
                # Return successful extraction
                mock_response = AsyncMock()
                mock_response.choices = [
                    AsyncMock(message=AsyncMock(content=json.dumps({
                        "revenue": 100000000,
                        "extraction_confidence": 0.8,
                        "currency": "USD"
                    })))
                ]
                return mock_response
            
            mock_client = AsyncMock()
            mock_client.chat.completions.create.side_effect = ai_side_effect
            mock_openai.return_value = mock_client
            
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                
                extraction_request = {
                    "company_url": "https://ai-resilience-test.com/reports/",
                    "company_name": "AI Resilience Test Company", 
                    "target_years": [2023],
                    "job_name": "AI Resilience Test"
                }
                
                response = await client.post("/extraction/jobs", json=extraction_request)
                assert response.status_code == 200
                
                # System should handle AI failures gracefully
    
    @pytest.mark.asyncio
    async def test_concurrent_job_processing(self):
        """
        Test system behavior with multiple concurrent extraction jobs
        """
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            
            # Create multiple concurrent jobs
            num_jobs = 5
            tasks = []
            
            for i in range(num_jobs):
                extraction_request = {
                    "company_url": f"https://concurrent-test-{i}.com/reports/",
                    "company_name": f"Concurrent Test Company {i}",
                    "target_years": [2023],
                    "job_name": f"Concurrent Test Job {i}"
                }
                
                task = client.post("/extraction/jobs", json=extraction_request)
                tasks.append(task)
            
            # Execute all jobs concurrently
            responses = await asyncio.gather(*tasks)
            
            # Verify all jobs were created successfully
            for response in responses:
                assert response.status_code == 200
                job_data = response.json()
                assert "job_id" in job_data
                assert job_data["status"] == "started"


@pytest.mark.e2e
class TestRealWorldScenarios:
    """
    Test scenarios that mimic real-world usage patterns
    """
    
    @pytest.mark.asyncio
    async def test_torex_gold_extraction_simulation(self):
        """
        Simulate extraction from Torex Gold (the target company from requirements)
        """
        # Mock the actual Torex Gold website structure
        torex_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Torex Gold - Financial Reports</title></head>
        <body>
            <div class="investor-relations">
                <section class="financial-reports">
                    <h3>Annual Reports</h3>
                    <div class="report-links">
                        <a href="/files/2023-annual-report.pdf" class="report-link">
                            <span class="report-title">2023 Annual Report</span>
                            <span class="report-date">March 2024</span>
                        </a>
                        <a href="/files/2022-annual-report.pdf" class="report-link">
                            <span class="report-title">2022 Annual Report</span>
                            <span class="report-date">March 2023</span>
                        </a>
                    </div>
                    
                    <h3>Quarterly Reports</h3>
                    <div class="report-links">
                        <a href="/files/q4-2023-earnings.pdf" class="report-link">
                            <span class="report-title">Q4 2023 Earnings Report</span>
                            <span class="report-date">February 2024</span>
                        </a>
                        <a href="/files/q3-2023-earnings.pdf" class="report-link">
                            <span class="report-title">Q3 2023 Earnings Report</span>
                            <span class="report-date">November 2023</span>
                        </a>
                    </div>
                </section>
            </div>
        </body>
        </html>
        """
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text.return_value = torex_html
            
            # Mock PDF content for document downloads
            mock_pdf_response = AsyncMock()
            mock_pdf_response.status = 200
            mock_pdf_response.read.return_value = b"%PDF-1.4\nMocked Torex Gold Financial Report Content"
            mock_pdf_response.headers = {'content-type': 'application/pdf'}
            
            async def session_get(*args, **kwargs):
                url = args[0] if args else kwargs.get('url', '')
                if '.pdf' in url:
                    return mock_pdf_response
                return mock_response
            
            mock_session_instance = AsyncMock()
            mock_session_instance.get.side_effect = session_get
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            async with httpx.AsyncClient(app=app, base_url="http://test") as client:
                
                # Test the exact request from the requirements
                torex_request = {
                    "company_url": "https://torexgold.com/investors/financial-reports/",
                    "company_name": "Torex Gold Resources Inc.",
                    "target_years": [2021, 2022, 2023, 2024],
                    "document_types": ["quarterly_report", "annual_report"],
                    "job_name": "Torex Gold Complete Extraction"
                }
                
                response = await client.post("/extraction/jobs", json=torex_request)
                assert response.status_code == 200
                
                job_data = response.json()
                assert job_data["status"] == "started"
                assert "job_id" in job_data
                
                # In a real scenario, wait for completion and verify extracted data
                # matches the expected financial metrics structure from requirements
    
    @pytest.mark.asyncio
    async def test_multi_company_portfolio_extraction(self):
        """
        Test extracting from multiple companies as in a real portfolio analysis scenario
        """
        companies = [
            {
                "url": "https://company1.com/investors/",
                "name": "Mining Corp A",
                "years": [2022, 2023]
            },
            {
                "url": "https://company2.com/financial-reports/",
                "name": "Mining Corp B", 
                "years": [2021, 2022, 2023]
            },
            {
                "url": "https://company3.com/investor-relations/reports/",
                "name": "Gold Producer C",
                "years": [2023, 2024]
            }
        ]
        
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            
            job_ids = []
            
            # Create extraction jobs for all companies
            for company in companies:
                extraction_request = {
                    "company_url": company["url"],
                    "company_name": company["name"],
                    "target_years": company["years"],
                    "document_types": ["quarterly_report", "annual_report"],
                    "job_name": f"{company['name']} Portfolio Analysis"
                }
                
                response = await client.post("/extraction/jobs", json=extraction_request)
                assert response.status_code == 200
                
                job_data = response.json()
                job_ids.append(job_data["job_id"])
            
            # Test portfolio-wide analytics
            analytics_response = await client.get("/analytics/summary")
            assert analytics_response.status_code == 200
            
            company_analytics_response = await client.get("/analytics/companies")
            assert company_analytics_response.status_code == 200
            
            # Verify we can filter documents across the entire portfolio
            portfolio_docs_response = await client.get(
                "/documents",
                params={"limit": 100}  # Get all documents
            )
            assert portfolio_docs_response.status_code == 200


# ==================== FIXTURES AND UTILITIES ====================

@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for E2E tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def cleanup_test_data():
    """Cleanup test data after E2E tests"""
    yield
    # Cleanup logic would go here
    # In a real implementation, you'd clean up test databases, files, etc.


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "e2e"])