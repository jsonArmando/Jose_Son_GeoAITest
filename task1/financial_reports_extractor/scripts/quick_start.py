#!/usr/bin/env python3
"""
Quick Start Script for Financial Reports Extractor
Automated setup and demonstration of the complete system
"""

import asyncio
import os
import sys
import time
import subprocess
import json
from pathlib import Path
from typing import Dict, List
import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text

console = Console()

class QuickStartGuide:
    """Interactive quick start guide for the Financial Reports Extractor"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.base_url = "http://localhost:8000"
        
    def display_welcome(self):
        """Display welcome message and project overview"""
        welcome_text = """
🏗️ Financial Reports Extractor - Hexagonal Architecture with AI Agents

This system demonstrates a complete production-ready application for extracting 
financial data from corporate reports using advanced AI techniques.

Key Features:
• 🤖 AI-Powered extraction with GPT-4 and Claude
• 🕷️ Intelligent web scraping that adapts to different sites  
• 🏛️ Clean Hexagonal Architecture with proper separation of concerns
• 📊 Multi-modal processing (text, tables, images)
• ✅ Advanced validation and quality assurance
• 🚀 Production-ready with Kubernetes, monitoring, and CI/CD
• 📈 Real-time analytics and dashboards

Architecture Overview:
┌─────────────────────────────────────────────────────────────┐
│                    🌐 PRESENTATION LAYER                    │
│           FastAPI • WebSocket • Prometheus Metrics         │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                   💼 APPLICATION LAYER                      │
│              Use Cases • Orchestration • Services          │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                     🏛️ DOMAIN LAYER                         │
│            Entities • Value Objects • Business Rules       │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                  🔧 INFRASTRUCTURE LAYER                    │
│    PostgreSQL • Redis • MinIO • Selenium • AI Agents      │
└─────────────────────────────────────────────────────────────┘
        """
        
        console.print(Panel(welcome_text, title="🚀 Welcome to Financial Reports Extractor", border_style="blue"))
    
    def show_project_structure(self):
        """Display the project structure"""
        console.print("\n📁 Project Structure Overview:", style="bold blue")
        
        tree = Tree("📂 financial_reports_extractor/")
        
        # Source code
        src_tree = tree.add("📂 src/")
        src_tree.add("🏛️ domain/ - Business logic and entities")
        src_tree.add("💼 application/ - Use cases and orchestration") 
        src_tree.add("🔧 infrastructure/ - External services implementation")
        src_tree.add("🔌 adapters/ - Web API, AI agents, persistence")
        
        # Tests
        tests_tree = tree.add("🧪 tests/")
        tests_tree.add("🔬 unit/ - Unit tests for domain logic")
        tests_tree.add("🔗 integration/ - Integration tests")
        tests_tree.add("🎯 e2e/ - End-to-end workflow tests")
        
        # Configuration
        config_tree = tree.add("⚙️ config/")
        config_tree.add("🐳 docker-compose.yml - Development environment")
        config_tree.add("☸️ k8s/ - Kubernetes production deployment")
        config_tree.add("🚀 .github/workflows/ - CI/CD pipeline")
        
        # Scripts and docs
        tree.add("📜 scripts/ - Setup and deployment utilities")
        tree.add("📚 docs/ - Technical documentation")
        tree.add("📋 README.md - Complete project documentation")
        
        console.print(tree)
    
    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are installed"""
        console.print("\n🔍 Checking Prerequisites...", style="bold yellow")
        
        prerequisites = [
            ("Python 3.11+", ["python", "--version"]),
            ("Docker", ["docker", "--version"]),
            ("Docker Compose", ["docker-compose", "--version"]),
            ("Git", ["git", "--version"])
        ]
        
        all_good = True
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
            for name, command in prerequisites:
                task = progress.add_task(f"Checking {name}...", total=1)
                
                try:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        console.print(f"✅ {name}: {result.stdout.strip().split()[0] if result.stdout else 'OK'}")
                    else:
                        console.print(f"❌ {name}: Not found or not working")
                        all_good = False
                except Exception as e:
                    console.print(f"❌ {name}: Error checking - {e}")
                    all_good = False
                
                progress.update(task, advance=1)
        
        return all_good
    
    def setup_environment(self):
        """Set up the development environment"""
        console.print("\n🛠️ Setting up Development Environment...", style="bold green")
        
        # Create .env if it doesn't exist
        env_file = self.project_root / ".env"
        if not env_file.exists():
            console.print("📝 Creating .env file from template...")
            env_example = self.project_root / ".env.example"
            if env_example.exists():
                env_file.write_text(env_example.read_text())
                console.print("✅ .env file created - Please add your API keys!")
            else:
                console.print("⚠️ .env.example not found, creating minimal .env")
                env_file.write_text("""
# Development Environment Configuration
ENVIRONMENT=development
LOG_LEVEL=INFO
SECRET_KEY=dev-secret-key-change-in-production

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres123@localhost:5432/financial_reports

# Cache
REDIS_URL=redis://:redis123@localhost:6379/0

# AI Services (ADD YOUR KEYS HERE!)
OPENAI_API_KEY=your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# Storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123

# Selenium
SELENIUM_HUB_URL=http://localhost:4444/wd/hub
                """)
        
        # Start Docker services
        console.print("🐳 Starting Docker services...")
        try:
            subprocess.run([
                "docker-compose", "up", "-d", 
                "postgres", "redis", "minio", "selenium-hub", "selenium-chrome"
            ], check=True, cwd=self.project_root)
            console.print("✅ Infrastructure services started")
        except subprocess.CalledProcessError as e:
            console.print(f"❌ Error starting Docker services: {e}")
            return False
        
        # Wait for services to be ready
        console.print("⏳ Waiting for services to be ready...")
        time.sleep(10)
        
        # Install Python dependencies
        console.print("📦 Installing Python dependencies...")
        try:
            subprocess.run([
                sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
            ], check=True, cwd=self.project_root)
            console.print("✅ Dependencies installed")
        except subprocess.CalledProcessError as e:
            console.print(f"❌ Error installing dependencies: {e}")
            return False
        
        # Run database migrations
        console.print("🗄️ Running database migrations...")
        try:
            subprocess.run([
                sys.executable, "scripts/setup.py", "migrate"
            ], check=True, cwd=self.project_root)
            console.print("✅ Database migrations completed")
        except subprocess.CalledProcessError as e:
            console.print(f"❌ Error running migrations: {e}")
            return False
        
        return True
    
    def start_application(self):
        """Start the main application"""
        console.print("\n🚀 Starting Financial Reports Extractor API...", style="bold green")
        
        # Start the FastAPI application in the background
        try:
            subprocess.Popen([
                sys.executable, "-m", "uvicorn", 
                "src.adapters.web.main:app", 
                "--reload", "--host", "0.0.0.0", "--port", "8000"
            ], cwd=self.project_root)
            
            console.print("⏳ Waiting for API to start...")
            time.sleep(5)
            
            # Check if API is running
            return self.check_api_health()
            
        except Exception as e:
            console.print(f"❌ Error starting application: {e}")
            return False
    
    async def check_api_health(self) -> bool:
        """Check if the API is healthy"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", timeout=10)
                if response.status_code == 200:
                    console.print("✅ API is running and healthy!")
                    return True
                else:
                    console.print(f"❌ API health check failed: {response.status_code}")
                    return False
        except Exception as e:
            console.print(f"❌ Could not connect to API: {e}")
            return False
    
    async def run_demo_extraction(self):
        """Run a demonstration extraction"""
        console.print("\n🎯 Running Demonstration Extraction...", style="bold magenta")
        
        # Demo extraction request
        demo_request = {
            "company_url": "https://torexgold.com/investors/financial-reports/",
            "company_name": "Torex Gold Resources Inc.",
            "target_years": [2023, 2024],
            "document_types": ["quarterly_report", "annual_report"],
            "job_name": "Quick Start Demo - Torex Gold"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                # Create extraction job
                console.print("📝 Creating extraction job...")
                response = await client.post(
                    f"{self.base_url}/extraction/jobs",
                    json=demo_request,
                    timeout=30
                )
                
                if response.status_code == 200:
                    job_data = response.json()
                    job_id = job_data["job_id"]
                    console.print(f"✅ Job created: {job_id}")
                    
                    # Simulate job monitoring
                    console.print("⏳ Monitoring job progress...")
                    for i in range(5):
                        await asyncio.sleep(2)
                        status_response = await client.get(f"{self.base_url}/extraction/jobs/{job_id}")
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            console.print(f"📊 Progress: {status_data.get('progress_percentage', 0):.1f}%")
                        
                    console.print("✅ Demo extraction job submitted successfully!")
                    return True
                else:
                    console.print(f"❌ Failed to create job: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            console.print(f"❌ Demo extraction failed: {e}")
            return False
    
    def display_next_steps(self):
        """Display next steps and useful information"""
        console.print("\n🎉 Setup Complete! Next Steps:", style="bold green")
        
        # Create a table with useful information
        table = Table(title="🔗 Useful Links and Commands")
        table.add_column("Service", style="cyan")
        table.add_column("URL/Command", style="magenta")
        table.add_column("Description", style="white")
        
        table.add_row("API Documentation", "http://localhost:8000/docs", "Interactive API documentation")
        table.add_row("Health Check", "http://localhost:8000/health", "Application health status")
        table.add_row("Metrics", "http://localhost:8000/metrics", "Prometheus metrics")
        table.add_row("MinIO Console", "http://localhost:9001", "File storage management")
        table.add_row("Database", "localhost:5432", "PostgreSQL database")
        table.add_row("Redis", "localhost:6379", "Cache and sessions")
        table.add_row("Tests", "pytest tests/", "Run all tests")
        table.add_row("Logs", "docker-compose logs -f", "View application logs")
        
        console.print(table)
        
        # Architecture highlights
        console.print("\n🏛️ Architecture Highlights:", style="bold blue")
        highlights = [
            "✨ Clean Hexagonal Architecture with proper separation of concerns",
            "🤖 AI Agents: Intelligent Scraping, Multi-Modal Extraction, Smart Validation",
            "🔄 Event-driven architecture with async processing",
            "📊 Real-time monitoring and observability",
            "🧪 Comprehensive testing strategy (Unit, Integration, E2E)",
            "🚀 Production-ready with Kubernetes deployment",
            "🔐 Security-first design with proper authentication and validation"
        ]
        
        for highlight in highlights:
            console.print(f"  {highlight}")
        
        # Sample API calls
        console.print("\n📋 Sample API Calls:", style="bold yellow")
        
        api_examples = """
# Create an extraction job
curl -X POST "http://localhost:8000/extraction/jobs" \\
  -H "Content-Type: application/json" \\
  -d '{
    "company_url": "https://torexgold.com/investors/financial-reports/",
    "company_name": "Torex Gold Resources Inc.",
    "target_years": [2023, 2024],
    "document_types": ["quarterly_report", "annual_report"]
  }'

# Check job status
curl "http://localhost:8000/extraction/jobs/{job_id}"

# List extracted documents
curl "http://localhost:8000/documents"

# Get analytics
curl "http://localhost:8000/analytics/summary"
        """
        
        console.print(Panel(api_examples, title="API Examples", border_style="yellow"))
        
        # Development tips
        console.print("\n💡 Development Tips:", style="bold cyan")
        tips = [
            "📝 Edit .env to add your OpenAI API key for full functionality",
            "🔧 Use 'docker-compose logs -f api' to view application logs",
            "🧪 Run 'pytest tests/unit/' for fast unit tests",
            "📊 Monitor metrics at http://localhost:8000/metrics",
            "🚀 Deploy to production with 'python scripts/setup.py deploy-k8s'",
            "📚 Check README.md for complete documentation"
        ]
        
        for tip in tips:
            console.print(f"  {tip}")
    
    def display_architecture_summary(self):
        """Display a comprehensive architecture summary"""
        console.print("\n🏗️ Architecture Summary", style="bold blue")
        
        architecture_info = """
This project demonstrates a complete, production-ready implementation of:

🏛️ HEXAGONAL ARCHITECTURE (Ports & Adapters)
├── 🌐 Presentation Layer (FastAPI, WebSocket, Metrics)
├── 💼 Application Layer (Use Cases, Services, Orchestration)  
├── 🎯 Domain Layer (Entities, Value Objects, Business Rules)
└── 🔧 Infrastructure Layer (Database, Cache, Storage, AI)

🤖 SPECIALIZED AI AGENTS
├── 🕷️ Intelligent Scraping Agent (Adaptive web crawling)
├── 📊 Multi-Modal Extraction Agent (Text, Tables, Images)
└── ✅ Validation Agent (Quality assurance & accuracy)

🏭 PRODUCTION-READY FEATURES
├── 🚀 Kubernetes deployment with auto-scaling
├── 📈 Prometheus metrics & Grafana dashboards  
├── 🔄 CI/CD pipeline with GitHub Actions
├── 🧪 Comprehensive testing (Unit, Integration, E2E)
├── 🔐 Security scanning & best practices
└── 📚 Complete documentation & monitoring

🎯 TECHNICAL EXCELLENCE
├── ⚡ Async/await throughout for performance
├── 🎭 Dependency injection for testability
├── 🔒 Type hints and validation everywhere
├── 📊 Event-driven architecture
├── 🛡️ Error handling and resilience patterns
└── 🧹 Clean code principles & SOLID design
        """
        
        console.print(Panel(architecture_info, title="🏆 What Makes This Special", border_style="green"))

async def main():
    """Main quick start function"""
    guide = QuickStartGuide()
    
    # Welcome and overview
    guide.display_welcome()
    guide.show_project_structure()
    
    # Check prerequisites
    if not guide.check_prerequisites():
        console.print("\n❌ Please install missing prerequisites and try again.", style="bold red")
        return
    
    # Setup environment
    if not guide.setup_environment():
        console.print("\n❌ Environment setup failed. Please check the errors above.", style="bold red")
        return
    
    # Start application
    if not guide.start_application():
        console.print("\n❌ Failed to start application. Please check Docker services.", style="bold red")
        return
    
    # Run demo extraction
    await guide.run_demo_extraction()
    
    # Display next steps
    guide.display_next_steps()
    guide.display_architecture_summary()
    
    console.print("\n🎉 Financial Reports Extractor is ready to use!", style="bold green")
    console.print("Visit http://localhost:8000/docs for the interactive API documentation", style="blue")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n👋 Setup cancelled by user", style="yellow")
    except Exception as e:
        console.print(f"\n❌ Setup failed: {e}", style="bold red")