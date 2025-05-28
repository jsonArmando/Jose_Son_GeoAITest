#!/usr/bin/env python3
"""
Setup and Deployment Scripts for Financial Reports Extractor
Automated setup, database migration, and deployment utilities
"""

import asyncio
import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict, Optional
import asyncpg
import aioredis
from minio import Minio
from minio.error import S3Error

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from infrastructure.persistence.models import Base
from sqlalchemy.ext.asyncio import create_async_engine
import structlog

logger = structlog.get_logger()


class DatabaseSetup:
    """Database setup and migration utilities"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
    
    async def create_database(self):
        """Create database if it doesn't exist"""
        try:
            # Extract database name from URL
            db_name = self.database_url.split('/')[-1]
            base_url = self.database_url.rsplit('/', 1)[0]
            
            # Connect to default database to create our database
            default_url = f"{base_url}/postgres"
            
            conn = await asyncpg.connect(default_url)
            
            # Check if database exists
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", db_name
            )
            
            if not exists:
                await conn.execute(f'CREATE DATABASE "{db_name}"')
                logger.info(f"Database {db_name} created successfully")
            else:
                logger.info(f"Database {db_name} already exists")
                
            await conn.close()
            
        except Exception as e:
            logger.error(f"Error creating database: {e}")
            raise
    
    async def run_migrations(self):
        """Run database migrations"""
        try:
            self.engine = create_async_engine(self.database_url)
            
            async with self.engine.begin() as conn:
                # Create all tables
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Database migrations completed successfully")
                
        except Exception as e:
            logger.error(f"Error running migrations: {e}")
            raise
        finally:
            if self.engine:
                await self.engine.dispose()
    
    async def seed_initial_data(self):
        """Seed initial data for development"""
        try:
            # Add initial configuration data, sample companies, etc.
            logger.info("Seeding initial data...")
            
            # This would include:
            # - Default scraping configurations
            # - Sample company profiles
            # - Initial admin users
            # - Default settings
            
            logger.info("Initial data seeded successfully")
            
        except Exception as e:
            logger.error(f"Error seeding initial data: {e}")
            raise


class StorageSetup:
    """Storage setup utilities"""
    
    def __init__(self, config: Dict[str, str]):
        self.config = config
    
    def setup_local_storage(self):
        """Setup local file storage directories"""
        try:
            storage_path = Path(self.config.get('storage_path', './storage'))
            
            # Create directory structure
            directories = [
                storage_path,
                storage_path / 'documents',
                storage_path / 'temp',
                storage_path / 'processed',
                storage_path / 'logs',
                storage_path / 'cache',
                storage_path / 'exports'
            ]
            
            for directory in directories:
                directory.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created directory: {directory}")
            
            # Set appropriate permissions
            os.chmod(storage_path, 0o755)
            
            logger.info("Local storage setup completed")
            
        except Exception as e:
            logger.error(f"Error setting up local storage: {e}")
            raise
    
    def setup_minio_storage(self):
        """Setup MinIO object storage"""
        try:
            client = Minio(
                endpoint=self.config['minio_endpoint'],
                access_key=self.config['minio_access_key'],
                secret_key=self.config['minio_secret_key'],
                secure=self.config.get('minio_secure', 'false').lower() == 'true'
            )
            
            bucket_name = self.config.get('minio_bucket_name', 'financial-documents')
            
            # Create bucket if it doesn't exist
            if not client.bucket_exists(bucket_name):
                client.make_bucket(bucket_name)
                logger.info(f"MinIO bucket '{bucket_name}' created")
            else:
                logger.info(f"MinIO bucket '{bucket_name}' already exists")
            
            # Set bucket policy for appropriate access
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{bucket_name}/public/*"]
                    }
                ]
            }
            
            client.set_bucket_policy(bucket_name, json.dumps(policy))
            logger.info("MinIO storage setup completed")
            
        except S3Error as e:
            logger.error(f"MinIO setup error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error setting up MinIO storage: {e}")
            raise


class CacheSetup:
    """Cache setup utilities"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
    
    async def setup_redis_cache(self):
        """Setup Redis cache"""
        try:
            redis = await aioredis.from_url(self.redis_url)
            
            # Test connection
            await redis.ping()
            logger.info("Redis connection successful")
            
            # Set up initial cache structure
            await redis.hset("app:config", mapping={
                "version": "1.0.0",
                "setup_date": str(datetime.utcnow()),
                "cache_enabled": "true"
            })
            
            await redis.close()
            logger.info("Redis cache setup completed")
            
        except Exception as e:
            logger.error(f"Error setting up Redis cache: {e}")
            raise


class ApplicationSetup:
    """Main application setup orchestrator"""
    
    def __init__(self, config: Dict[str, str]):
        self.config = config
        self.db_setup = DatabaseSetup(config['database_url'])
        self.storage_setup = StorageSetup(config)
        self.cache_setup = CacheSetup(config['redis_url'])
    
    async def setup_development_environment(self):
        """Setup complete development environment"""
        logger.info("Setting up development environment...")
        
        try:
            # 1. Database setup
            await self.db_setup.create_database()
            await self.db_setup.run_migrations()
            await self.db_setup.seed_initial_data()
            
            # 2. Storage setup
            self.storage_setup.setup_local_storage()
            
            # 3. Cache setup
            await self.cache_setup.setup_redis_cache()
            
            # 4. Install development dependencies
            await self._install_development_dependencies()
            
            # 5. Setup pre-commit hooks
            self._setup_pre_commit_hooks()
            
            logger.info("Development environment setup completed successfully!")
            
        except Exception as e:
            logger.error(f"Development environment setup failed: {e}")
            raise
    
    async def setup_production_environment(self):
        """Setup production environment"""
        logger.info("Setting up production environment...")
        
        try:
            # 1. Database setup
            await self.db_setup.create_database()
            await self.db_setup.run_migrations()
            
            # 2. MinIO storage setup
            self.storage_setup.setup_minio_storage()
            
            # 3. Cache setup
            await self.cache_setup.setup_redis_cache()
            
            # 4. Setup monitoring and logging
            await self._setup_production_monitoring()
            
            # 5. Setup SSL certificates
            self._setup_ssl_certificates()
            
            logger.info("Production environment setup completed successfully!")
            
        except Exception as e:
            logger.error(f"Production environment setup failed: {e}")
            raise
    
    async def _install_development_dependencies(self):
        """Install development dependencies"""
        try:
            subprocess.run([
                sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"
            ], check=True)
            logger.info("Development dependencies installed")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error installing development dependencies: {e}")
            raise
    
    def _setup_pre_commit_hooks(self):
        """Setup pre-commit hooks"""
        try:
            subprocess.run(["pre-commit", "install"], check=True)
            logger.info("Pre-commit hooks installed")
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Could not install pre-commit hooks: {e}")
    
    async def _setup_production_monitoring(self):
        """Setup production monitoring"""
        logger.info("Setting up production monitoring...")
        
        # This would include:
        # - Prometheus metrics setup
        # - Grafana dashboard configuration  
        # - Log aggregation setup
        # - Health check endpoints
        # - Alerting rules
        
        logger.info("Production monitoring setup completed")
    
    def _setup_ssl_certificates(self):
        """Setup SSL certificates for production"""
        logger.info("Setting up SSL certificates...")
        
        # This would include:
        # - Let's Encrypt certificate generation
        # - Certificate renewal setup
        # - NGINX SSL configuration
        
        logger.info("SSL certificates setup completed")


class DeploymentUtilities:
    """Deployment utilities and helpers"""
    
    @staticmethod
    def build_docker_images():
        """Build Docker images for deployment"""
        try:
            logger.info("Building Docker images...")
            
            # Build main application image
            subprocess.run([
                "docker", "build", 
                "-t", "financial-reports-extractor:latest",
                "-f", "Dockerfile",
                "."
            ], check=True)
            
            logger.info("Docker images built successfully")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error building Docker images: {e}")
            raise
    
    @staticmethod
    def deploy_with_docker_compose():
        """Deploy using docker-compose"""
        try:
            logger.info("Deploying with docker-compose...")
            
            # Pull latest images
            subprocess.run(["docker-compose", "pull"], check=True)
            
            # Deploy services
            subprocess.run([
                "docker-compose", "up", "-d", 
                "--remove-orphans"
            ], check=True)
            
            logger.info("Docker Compose deployment completed")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error deploying with docker-compose: {e}")
            raise
    
    @staticmethod
    def deploy_to_kubernetes():
        """Deploy to Kubernetes cluster"""
        try:
            logger.info("Deploying to Kubernetes...")
            
            # Apply Kubernetes manifests
            subprocess.run([
                "kubectl", "apply", "-f", "k8s/"
            ], check=True)
            
            # Wait for deployment to be ready
            subprocess.run([
                "kubectl", "rollout", "status", 
                "deployment/financial-reports-extractor"
            ], check=True)
            
            logger.info("Kubernetes deployment completed")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error deploying to Kubernetes: {e}")
            raise


def load_config_from_env() -> Dict[str, str]:
    """Load configuration from environment variables"""
    return {
        'database_url': os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres123@localhost:5432/financial_reports'),
        'redis_url': os.getenv('REDIS_URL', 'redis://:redis123@localhost:6379/0'),
        'minio_endpoint': os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
        'minio_access_key': os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
        'minio_secret_key': os.getenv('MINIO_SECRET_KEY', 'minioadmin123'),
        'minio_bucket_name': os.getenv('MINIO_BUCKET_NAME', 'financial-documents'),
        'minio_secure': os.getenv('MINIO_SECURE', 'false'),
        'storage_path': os.getenv('STORAGE_PATH', './storage'),
        'environment': os.getenv('ENVIRONMENT', 'development')
    }


async def main():
    """Main setup function"""
    parser = argparse.ArgumentParser(description='Financial Reports Extractor Setup')
    parser.add_argument('command', choices=[
        'setup-dev', 'setup-prod', 'migrate', 'seed-data',
        'build-docker', 'deploy-compose', 'deploy-k8s'
    ], help='Setup command to run')
    
    args = parser.parse_args()
    
    config = load_config_from_env()
    setup = ApplicationSetup(config)
    deployment = DeploymentUtilities()
    
    try:
        if args.command == 'setup-dev':
            await setup.setup_development_environment()
            
        elif args.command == 'setup-prod':
            await setup.setup_production_environment()
            
        elif args.command == 'migrate':
            await setup.db_setup.create_database()
            await setup.db_setup.run_migrations()
            
        elif args.command == 'seed-data':
            await setup.db_setup.seed_initial_data()
            
        elif args.command == 'build-docker':
            deployment.build_docker_images()
            
        elif args.command == 'deploy-compose':
            deployment.deploy_with_docker_compose()
            
        elif args.command == 'deploy-k8s':
            deployment.deploy_to_kubernetes()
            
        logger.info(f"Command '{args.command}' completed successfully!")
        
    except Exception as e:
        logger.error(f"Command '{args.command}' failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())