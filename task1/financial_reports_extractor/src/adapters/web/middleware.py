"""
Custom Middleware for FastAPI Application
Handles logging, metrics, rate limiting, and request processing
"""

import time
import uuid
from typing import Callable, Optional
import json

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog
from prometheus_client import Counter, Histogram, Gauge

from .dependencies import get_metrics_service


# ==================== METRICS SETUP ====================

# Request metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

# Application metrics
EXTRACTION_JOBS_ACTIVE = Gauge(
    'extraction_jobs_active_total',
    'Number of active extraction jobs'
)

DATABASE_CONNECTIONS = Gauge(
    'database_connections_active',
    'Number of active database connections'
)


# ==================== REQUEST LOGGING MIDDLEWARE ====================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured request/response logging
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = structlog.get_logger("api")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID for tracing
        request_id = str(uuid.uuid4())
        
        # Add request ID to request state
        request.state.request_id = request_id
        
        # Start timing
        start_time = time.time()
        
        # Extract request information
        method = request.method
        url = str(request.url)
        path = request.url.path
        user_agent = request.headers.get("user-agent", "")
        client_ip = self._get_client_ip(request)
        
        # Log request start
        await self._log_request_start(
            request_id, method, path, client_ip, user_agent
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log successful response
            await self._log_request_complete(
                request_id, method, path, response.status_code, 
                process_time, client_ip
            )
            
            # Add custom headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.4f}"
            
            return response
            
        except Exception as e:
            # Calculate processing time for errors
            process_time = time.time() - start_time
            
            # Log error
            await self._log_request_error(
                request_id, method, path, str(e), process_time, client_ip
            )
            
            # Return error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_server_error",
                    "message": "An internal error occurred",
                    "request_id": request_id,
                    "timestamp": time.time()
                },
                headers={"X-Request-ID": request_id}
            )
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        # Check for forwarded headers (from load balancers/proxies)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection IP
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"
    
    async def _log_request_start(
        self, 
        request_id: str, 
        method: str, 
        path: str, 
        client_ip: str, 
        user_agent: str
    ):
        """Log request start"""
        self.logger.info(
            "Request started",
            request_id=request_id,
            method=method,
            path=path,
            client_ip=client_ip,
            user_agent=user_agent,
            event_type="request_start"
        )
    
    async def _log_request_complete(
        self, 
        request_id: str, 
        method: str, 
        path: str, 
        status_code: int,
        process_time: float, 
        client_ip: str
    ):
        """Log successful request completion"""
        self.logger.info(
            "Request completed",
            request_id=request_id,
            method=method,
            path=path,
            status_code=status_code,
            process_time_seconds=process_time,
            client_ip=client_ip,
            event_type="request_complete"
        )
    
    async def _log_request_error(
        self, 
        request_id: str, 
        method: str, 
        path: str, 
        error: str,
        process_time: float, 
        client_ip: str
    ):
        """Log request error"""
        self.logger.error(
            "Request failed",
            request_id=request_id,
            method=method,
            path=path,
            error=error,
            process_time_seconds=process_time,
            client_ip=client_ip,
            event_type="request_error"
        )


# ==================== METRICS MIDDLEWARE ====================

class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware for collecting application metrics
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract labels
        method = request.method
        path = self._normalize_path(request.url.path)
        
        # Increment active requests
        ACTIVE_REQUESTS.inc()
        
        # Start timing
        start_time = time.time()
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Record metrics
            status_code = str(response.status_code)
            REQUEST_COUNT.labels(
                method=method, 
                endpoint=path, 
                status_code=status_code
            ).inc()
            
            REQUEST_DURATION.labels(
                method=method, 
                endpoint=path
            ).observe(duration)
            
            return response
            
        except Exception as e:
            # Record error metrics
            REQUEST_COUNT.labels(
                method=method, 
                endpoint=path, 
                status_code="500"
            ).inc()
            
            duration = time.time() - start_time
            REQUEST_DURATION.labels(
                method=method, 
                endpoint=path
            ).observe(duration)
            
            raise e
            
        finally:
            # Decrement active requests
            ACTIVE_REQUESTS.dec()
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path for metrics (remove IDs)"""
        # Replace UUIDs and numeric IDs with placeholders
        import re
        
        # UUID pattern
        uuid_pattern = r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        path = re.sub(uuid_pattern, '/{id}', path, flags=re.IGNORECASE)
        
        # Numeric ID pattern
        numeric_pattern = r'/\d+'
        path = re.sub(numeric_pattern, '/{id}', path)
        
        return path


# ==================== RATE LIMITING MIDDLEWARE ====================

class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Simple rate limiting middleware
    """
    
    def __init__(self, app: ASGIApp, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = {}  # In memory - use Redis for production
        self.logger = structlog.get_logger("rate_limiter")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = self._get_client_ip(request)
        current_time = int(time.time() / 60)  # Current minute
        
        # Initialize client data if not exists
        if client_ip not in self.requests:
            self.requests[client_ip] = {}
        
        # Clean old entries (older than 1 minute)
        self.requests[client_ip] = {
            minute: count 
            for minute, count in self.requests[client_ip].items() 
            if minute >= current_time - 1
        }
        
        # Count current minute requests
        current_requests = self.requests[client_ip].get(current_time, 0)
        
        # Check rate limit
        if current_requests >= self.requests_per_minute:
            self.logger.warning(
                "Rate limit exceeded",
                client_ip=client_ip,
                requests_per_minute=current_requests,
                limit=self.requests_per_minute
            )
            
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute.",
                    "retry_after": 60 - int(time.time() % 60)
                },
                headers={
                    "Retry-After": str(60 - int(time.time() % 60)),
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": str(max(0, self.requests_per_minute - current_requests - 1)),
                    "X-RateLimit-Reset": str((current_time + 1) * 60)
                }
            )
        
        # Increment request count
        self.requests[client_ip][current_time] = current_requests + 1
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers to response
        remaining = max(0, self.requests_per_minute - self.requests[client_ip][current_time])
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str((current_time + 1) * 60)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address"""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"


# ==================== SECURITY MIDDLEWARE ====================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware for adding security headers
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Content Security Policy (adjust based on your needs)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' https:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none'"
        )
        response.headers["Content-Security-Policy"] = csp
        
        return response


# ==================== ERROR HANDLING MIDDLEWARE ====================

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Global error handling and normalization middleware
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = structlog.get_logger("error_handler")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            return response
            
        except ValueError as e:
            # Validation errors
            return await self._handle_validation_error(request, e)
            
        except PermissionError as e:
            # Permission/authorization errors
            return await self._handle_permission_error(request, e)
            
        except TimeoutError as e:
            # Timeout errors
            return await self._handle_timeout_error(request, e)
            
        except Exception as e:
            # Generic server errors
            return await self._handle_server_error(request, e)
    
    async def _handle_validation_error(self, request: Request, error: ValueError) -> JSONResponse:
        """Handle validation errors"""
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        self.logger.warning(
            "Validation error",
            request_id=request_id,
            path=request.url.path,
            error=str(error)
        )
        
        return JSONResponse(
            status_code=400,
            content={
                "error": "validation_error",
                "message": str(error),
                "request_id": request_id,
                "timestamp": time.time()
            }
        )
    
    async def _handle_permission_error(self, request: Request, error: PermissionError) -> JSONResponse:
        """Handle permission errors"""
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        self.logger.warning(
            "Permission denied",
            request_id=request_id,
            path=request.url.path,
            error=str(error)
        )
        
        return JSONResponse(
            status_code=403,
            content={
                "error": "permission_denied",
                "message": "Insufficient permissions to access this resource",
                "request_id": request_id,
                "timestamp": time.time()
            }
        )
    
    async def _handle_timeout_error(self, request: Request, error: TimeoutError) -> JSONResponse:
        """Handle timeout errors"""
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        self.logger.error(
            "Request timeout",
            request_id=request_id,
            path=request.url.path,
            error=str(error)
        )
        
        return JSONResponse(
            status_code=504,
            content={
                "error": "request_timeout",
                "message": "Request timed out. Please try again later.",
                "request_id": request_id,
                "timestamp": time.time()
            }
        )
    
    async def _handle_server_error(self, request: Request, error: Exception) -> JSONResponse:
        """Handle generic server errors"""
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        self.logger.error(
            "Internal server error",
            request_id=request_id,
            path=request.url.path,
            error=str(error),
            error_type=type(error).__name__,
            exc_info=True
        )
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An internal error occurred. Please try again later.",
                "request_id": request_id,
                "timestamp": time.time()
            }
        )


# ==================== REQUEST CONTEXT MIDDLEWARE ====================

class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware for maintaining request context throughout the request lifecycle
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Initialize request context
        request.state.start_time = time.time()
        request.state.request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
        
        # Add useful context information
        request.state.user_agent = request.headers.get("user-agent", "")
        request.state.client_ip = self._get_client_ip(request)
        request.state.path = request.url.path
        request.state.method = request.method
        
        # Process request
        response = await call_next(request)
        
        # Add context to response headers (for debugging)
        if hasattr(request.state, 'request_id'):
            response.headers["X-Request-ID"] = request.state.request_id
        
        if hasattr(request.state, 'start_time'):
            duration = time.time() - request.state.start_time
            response.headers["X-Response-Time"] = f"{duration:.4f}s"
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address"""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"


# ==================== HEALTH CHECK MIDDLEWARE ====================

class HealthCheckMiddleware(BaseHTTPMiddleware):
    """
    Middleware that handles health checks efficiently
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Handle health checks quickly without going through full pipeline
        if request.url.path in ["/health", "/health/live"]:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "healthy",
                    "timestamp": time.time(),
                    "service": "financial-reports-extractor"
                }
            )
        
        # For other requests, continue with normal processing
        return await call_next(request)


# ==================== CORS CUSTOM MIDDLEWARE ====================

class CustomCORSMiddleware(BaseHTTPMiddleware):
    """
    Custom CORS middleware with additional security features
    """
    
    def __init__(
        self, 
        app: ASGIApp, 
        allowed_origins: list = None,
        allowed_methods: list = None,
        allowed_headers: list = None,
        expose_headers: list = None,
        max_age: int = 600
    ):
        super().__init__(app)
        self.allowed_origins = allowed_origins or ["*"]
        self.allowed_methods = allowed_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allowed_headers = allowed_headers or ["*"]
        self.expose_headers = expose_headers or ["X-Request-ID", "X-Response-Time"]
        self.max_age = max_age
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("origin")
        
        # Handle preflight requests
        if request.method == "OPTIONS":
            response = Response()
            self._add_cors_headers(response, origin)
            return response
        
        # Process regular request
        response = await call_next(request)
        self._add_cors_headers(response, origin)
        
        return response
    
    def _add_cors_headers(self, response: Response, origin: str = None):
        """Add CORS headers to response"""
        if origin and (origin in self.allowed_origins or "*" in self.allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
        elif "*" in self.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        
        response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allowed_methods)
        response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allowed_headers)
        response.headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
        response.headers["Access-Control-Max-Age"] = str(self.max_age)
        response.headers["Access-Control-Allow-Credentials"] = "true"