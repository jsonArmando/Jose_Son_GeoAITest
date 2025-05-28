"""
Integration Tests for FastAPI Application
Tests the complete API functionality with real HTTP requests
"""

import pytest
import asyncio
import json
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from src.adapters.web.main import app
from src.domain.entities import DocumentType
from src.adapters.web.schemas import (
    ExtractionJobRequest,
    ExtractionJobResponse,
    FinancialDocumentResponse
)


class TestHealthEndpoints:
    """Test health check endpoints"""
    
    def test_health_check(self):
        """Test basic health check endpoint"""
        with TestClient(app) as client:
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "timestamp" in data
            assert data["service"] == "financial-reports-extractor"
    
    def test_readiness_check(self):
        """Test readiness check endpoint"""
        with TestClient(app) as client:
            response = client.get("/health/ready")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert "checks" in data
            assert data["checks"]["database"] == "ok"


class TestExtractionEndpoints:
    """Test extraction job endpoints"""
    
    @pytest.fixture
    def valid_extraction_request(self):
        """Valid extraction job request"""
        return {
            "company_url": "https://torexgold.com/investors/financial-reports/",
            "company_name": "Torex Gold Resources Inc.",
            "target_years": [2022, 2023, 2024],
            "document_types": ["quarterly_report", "annual_report"],
            "job_name": "Test Extraction Job"
        }
    
    @patch('src.adapters.web.main.get_use_cases')
    def test_create_extraction_job_success(self, mock_get_use_cases, valid_extraction_request):
        """Test successful extraction job creation"""
        
        # Mock use cases
        mock_use_cases = {
            'extract_reports': AsyncMock(),
            'get_job_status': AsyncMock(),
            'list_documents': AsyncMock(),
            'retry_extraction': AsyncMock()
        }
        mock_get_use_cases.return_value = mock_use_cases
        
        with TestClient(app) as client:
            response = client.post(
                "/extraction/jobs",
                json=valid_extraction_request
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "started"
            assert data["message"] == "Extraction job started successfully"
            assert data["estimated_completion_minutes"] == 15
    
    def test_create_extraction_job_invalid_request(self):
        """Test extraction job creation with invalid request"""
        invalid_request = {
            "company_url": "not-a-valid-url",  # Invalid URL
            "company_name": "Test Company",
            "target_years": [1999, 2030]  # Invalid years
        }
        
        with TestClient(app) as client:
            response = client.post(
                "/extraction/jobs",
                json=invalid_request
            )
            
            assert response.status_code == 422  # Validation error
            data = response.json()
            assert "detail" in data
    
    def test_create_extraction_job_missing_fields(self):
        """Test extraction job creation with missing required fields"""
        incomplete_request = {
            "company_name": "Test Company"  # Missing required fields
        }
        
        with TestClient(app) as client:
            response = client.post(
                "/extraction/jobs",
                json=incomplete_request
            )
            
            assert response.status_code == 422
    
    @patch('src.adapters.web.main.get_use_cases')
    def test_get_extraction_job_status(self, mock_get_use_cases):
        """Test getting extraction job status"""
        job_id = str(uuid4())
        
        # Mock job status response
        mock_job_status = {
            "job_id": job_id,
            "name": "Test Job",
            "status": "completed",
            "progress_percentage": 100.0,
            "total_documents": 5,
            "processed_documents": 5,
            "successful_documents": 4,
            "failed_documents": 1,
            "success_rate": 80.0,
            "duration_seconds": 120.5,
            "created_at": "2024-01-15T10:30:00Z",
            "started_at": "2024-01-15T10:30:15Z",
            "completed_at": "2024-01-15T10:32:15Z",
            "documents": []
        }
        
        mock_status_use_case = AsyncMock()
        mock_status_use_case.execute.return_value = mock_job_status
        
        mock_use_cases = {
            'get_job_status': mock_status_use_case
        }
        mock_get_use_cases.return_value = mock_use_cases
        
        with TestClient(app) as client:
            response = client.get(f"/extraction/jobs/{job_id}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == job_id
            assert data["status"] == "completed"
            assert data["success_rate"] == 80.0
    
    @patch('src.adapters.web.main.get_use_cases')
    def test_get_nonexistent_job_status(self, mock_get_use_cases):
        """Test getting status of non-existent job"""
        job_id = str(uuid4())
        
        mock_status_use_case = AsyncMock()
        mock_status_use_case.execute.return_value = None  # Job not found
        
        mock_use_cases = {
            'get_job_status': mock_status_use_case
        }
        mock_get_use_cases.return_value = mock_use_cases
        
        with TestClient(app) as client:
            response = client.get(f"/extraction/jobs/{job_id}")
            
            assert response.status_code == 404
            data = response.json()
            assert data["detail"] == "Job not found"
    
    def test_get_job_status_invalid_uuid(self):
        """Test getting job status with invalid UUID"""
        with TestClient(app) as client:
            response = client.get("/extraction/jobs/invalid-uuid")
            
            assert response.status_code == 422  # Validation error


class TestDocumentEndpoints:
    """Test document-related endpoints"""
    
    @patch('src.adapters.web.main.get_use_cases')
    def test_list_documents_no_filters(self, mock_get_use_cases):
        """Test listing documents without filters"""
        
        # Mock documents response
        mock_documents = [
            {
                "id": str(uuid4()),
                "title": "Q4 2023 Report",
                "url": "https://example.com/q4-2023.pdf",
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
            },
            {
                "id": str(uuid4()),
                "title": "2023 Annual Report",
                "url": "https://example.com/annual-2023.pdf",
                "document_type": "annual_report",
                "year": 2023,
                "quarter": None,
                "status": "completed",
                "confidence_level": 0.85,
                "validation_score": 0.90,
                "file_size_bytes": 5242880,
                "created_at": "2024-01-15T11:00:00Z",
                "updated_at": "2024-01-15T11:10:00Z",
                "error_messages": []
            }
        ]
        
        mock_list_use_case = AsyncMock()
        mock_list_use_case.execute.return_value = mock_documents
        
        mock_use_cases = {
            'list_documents': mock_list_use_case
        }
        mock_get_use_cases.return_value = mock_use_cases
        
        with TestClient(app) as client:
            response = client.get("/documents")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["title"] == "Q4 2023 Report"
            assert data[1]["title"] == "2023 Annual Report"
    
    @patch('src.adapters.web.main.get_use_cases')
    def test_list_documents_with_filters(self, mock_get_use_cases):
        """Test listing documents with filters"""
        
        mock_list_use_case = AsyncMock()
        mock_list_use_case.execute.return_value = []
        
        mock_use_cases = {
            'list_documents': mock_list_use_case
        }
        mock_get_use_cases.return_value = mock_use_cases
        
        with TestClient(app) as client:
            response = client.get(
                "/documents",
                params={
                    "company_name": "Torex Gold",
                    "year": 2023,
                    "document_type": "quarterly_report",
                    "status": "completed",
                    "limit": 20,
                    "offset": 0
                }
            )
            
            assert response.status_code == 200
            
            # Verify use case was called with correct parameters
            mock_list_use_case.execute.assert_called_once_with(
                company_name="Torex Gold",
                year=2023,
                document_type="quarterly_report",
                status="completed",
                limit=20,
                offset=0
            )
    
    def test_list_documents_invalid_parameters(self):
        """Test listing documents with invalid parameters"""
        with TestClient(app) as client:
            # Invalid year
            response = client.get("/documents", params={"year": 1999})
            assert response.status_code == 422
            
            # Invalid limit
            response = client.get("/documents", params={"limit": 0})
            assert response.status_code == 422
            
            # Invalid offset
            response = client.get("/documents", params={"offset": -1})
            assert response.status_code == 422
    
    @patch('src.adapters.web.main.get_use_cases')
    def test_retry_document_extraction_success(self, mock_get_use_cases):
        """Test successful document extraction retry"""
        document_id = str(uuid4())
        
        mock_retry_use_case = AsyncMock()
        mock_retry_use_case.execute.return_value = True  # Successful retry
        
        mock_use_cases = {
            'retry_extraction': mock_retry_use_case
        }
        mock_get_use_cases.return_value = mock_use_cases
        
        with TestClient(app) as client:
            response = client.post(f"/documents/{document_id}/retry")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "retry completed successfully" in data["message"]
    
    @patch('src.adapters.web.main.get_use_cases')
    def test_retry_document_extraction_failure(self, mock_get_use_cases):
        """Test failed document extraction retry"""
        document_id = str(uuid4())
        
        mock_retry_use_case = AsyncMock()
        mock_retry_use_case.execute.return_value = False  # Failed retry
        
        mock_use_cases = {
            'retry_extraction': mock_retry_use_case
        }
        mock_get_use_cases.return_value = mock_use_cases
        
        with TestClient(app) as client:
            response = client.post(f"/documents/{document_id}/retry")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "cannot be retried" in data["message"]


class TestAnalyticsEndpoints:
    """Test analytics endpoints"""
    
    def test_get_analytics_summary(self):
        """Test analytics summary endpoint"""
        with TestClient(app) as client:
            response = client.get("/analytics/summary")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify expected fields are present
            expected_fields = [
                "total_documents_processed",
                "successful_extractions", 
                "failed_extractions",
                "average_confidence_score",
                "total_companies",
                "extraction_success_rate",
                "average_processing_time_seconds",
                "period_days"
            ]
            
            for field in expected_fields:
                assert field in data
                assert isinstance(data[field], (int, float))
    
    def test_get_analytics_summary_custom_period(self):
        """Test analytics summary with custom period"""
        with TestClient(app) as client:
            response = client.get("/analytics/summary", params={"period_days": 60})
            
            assert response.status_code == 200
            data = response.json()
            assert data["period_days"] == 60
    
    def test_get_analytics_summary_invalid_period(self):
        """Test analytics summary with invalid period"""
        with TestClient(app) as client:
            # Period too small
            response = client.get("/analytics/summary", params={"period_days": 0})
            assert response.status_code == 422
            
            # Period too large
            response = client.get("/analytics/summary", params={"period_days": 400})
            assert response.status_code == 422
    
    def test_get_company_analytics(self):
        """Test company analytics endpoint"""
        with TestClient(app) as client:
            response = client.get("/analytics/companies")
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            
            if data:  # If there are companies in the response
                company = data[0]
                expected_fields = [
                    "company_name",
                    "documents_processed",
                    "success_rate",
                    "average_confidence",
                    "last_extraction"
                ]
                
                for field in expected_fields:
                    assert field in company


class TestMiddleware:
    """Test custom middleware functionality"""
    
    def test_request_id_header(self):
        """Test that request ID is added to response headers"""
        with TestClient(app) as client:
            response = client.get("/health")
            
            assert response.status_code == 200
            assert "X-Request-ID" in response.headers
            assert "X-Process-Time" in response.headers
    
    def test_cors_headers(self):
        """Test CORS headers are present"""
        with TestClient(app) as client:
            # Preflight request
            response = client.options(
                "/health",
                headers={"Origin": "http://localhost:3000"}
            )
            
            # Verify CORS headers
            assert "Access-Control-Allow-Origin" in response.headers
            assert "Access-Control-Allow-Methods" in response.headers
    
    def test_security_headers(self):
        """Test security headers are present"""
        with TestClient(app) as client:
            response = client.get("/health")
            
            security_headers = [
                "X-Content-Type-Options",
                "X-Frame-Options",
                "X-XSS-Protection",
                "Referrer-Policy"
            ]
            
            for header in security_headers:
                assert header in response.headers


class TestErrorHandling:
    """Test error handling and responses"""
    
    def test_404_error_handling(self):
        """Test 404 error handling"""
        with TestClient(app) as client:
            response = client.get("/nonexistent-endpoint")
            
            assert response.status_code == 404
            data = response.json()
            assert "error" in data
            assert "timestamp" in data
    
    def test_validation_error_handling(self):
        """Test validation error handling"""
        with TestClient(app) as client:
            # Send invalid JSON to extraction endpoint
            invalid_request = {
                "company_url": "not-a-url",
                "target_years": ["not-a-number"]
            }
            
            response = client.post("/extraction/jobs", json=invalid_request)
            
            assert response.status_code == 422
            data = response.json()
            assert "detail" in data
    
    def test_method_not_allowed(self):
        """Test method not allowed error"""
        with TestClient(app) as client:
            # Try to POST to a GET-only endpoint
            response = client.post("/health")
            
            assert response.status_code == 405


class TestAsyncEndpoints:
    """Test asynchronous endpoint behavior"""
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            # Make multiple concurrent requests
            tasks = [
                client.get("/health"),
                client.get("/analytics/summary"),
                client.get("/documents"),
                client.get("/analytics/companies")
            ]
            
            responses = await asyncio.gather(*tasks)
            
            # Verify all requests succeeded
            for response in responses:
                assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_long_running_request_timeout(self):
        """Test timeout handling for long-running requests"""
        
        # Mock a slow use case
        with patch('src.adapters.web.main.get_use_cases') as mock_get_use_cases:
            
            async def slow_execute(*args, **kwargs):
                await asyncio.sleep(2)  # Simulate slow operation
                return []
            
            mock_use_case = AsyncMock()
            mock_use_case.execute.side_effect = slow_execute
            
            mock_use_cases = {
                'list_documents': mock_use_case
            }
            mock_get_use_cases.return_value = mock_use_cases
            
            async with httpx.AsyncClient(
                app=app, 
                base_url="http://test",
                timeout=1.0  # 1 second timeout
            ) as client:
                try:
                    response = await client.get("/documents")
                    # Should timeout before completing
                    assert False, "Request should have timed out"
                except httpx.TimeoutException:
                    # Expected timeout
                    pass


# ==================== FIXTURES AND HELPERS ====================

@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_extraction_result():
    """Mock extraction result for testing"""
    return {
        "job_id": str(uuid4()),
        "total_documents": 5,
        "successful_extractions": 4,
        "failed_extractions": 1,
        "average_confidence": 0.87,
        "processing_time_seconds": 245.6,
        "documents": []
    }


class APITestHelper:
    """Helper class for API testing"""
    
    @staticmethod
    def create_test_client():
        """Create test client with all middleware"""
        return TestClient(app)
    
    @staticmethod
    def assert_error_response(response, expected_status: int):
        """Assert error response format"""
        assert response.status_code == expected_status
        data = response.json()
        assert "error" in data
        assert "message" in data
        assert "timestamp" in data
    
    @staticmethod
    def assert_success_response(response, expected_fields: list):
        """Assert successful response format"""
        assert response.status_code == 200
        data = response.json()
        for field in expected_fields:
            assert field in data


# ==================== PERFORMANCE TESTS ====================

@pytest.mark.slow
class TestAPIPerformance:
    """Performance tests for API endpoints"""
    
    def test_health_endpoint_performance(self):
        """Test health endpoint response time"""
        import time
        
        with TestClient(app) as client:
            start_time = time.time()
            response = client.get("/health")
            end_time = time.time()
            
            assert response.status_code == 200
            assert (end_time - start_time) < 0.1  # Should respond in < 100ms
    
    @pytest.mark.asyncio
    async def test_concurrent_request_handling(self):
        """Test API handling multiple concurrent requests"""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            
            # Create many concurrent requests
            num_requests = 50
            tasks = [client.get("/health") for _ in range(num_requests)]
            
            start_time = asyncio.get_event_loop().time()
            responses = await asyncio.gather(*tasks)
            end_time = asyncio.get_event_loop().time()
            
            # Verify all requests succeeded
            for response in responses:
                assert response.status_code == 200
            
            # Verify reasonable performance
            total_time = end_time - start_time
            assert total_time < 5.0  # Should handle 50 requests in < 5 seconds
            
            print(f"Handled {num_requests} concurrent requests in {total_time:.2f} seconds")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])