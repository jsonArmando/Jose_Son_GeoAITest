# app/config.py
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Carga las variables de entorno del archivo .env
# Esto es útil especialmente para desarrollo local. En producción, las variables
# de entorno suelen ser gestionadas por el sistema de orquestación (ej. Docker Compose, Kubernetes).
load_dotenv()

class Settings(BaseSettings):
    """
    Configuraciones de la aplicación cargadas desde variables de entorno.
    Pydantic BaseSettings automáticamente lee las variables de entorno
    que coinciden con los nombres de los atributos de esta clase.
    """
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/financial_reports_db")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
    START_YEAR: int = int(os.getenv("START_YEAR", "2021"))
    END_YEAR: int = int(os.getenv("END_YEAR", "2024"))
    
    # URL del sitio de Torex Gold para los informes financieros
    TOREX_REPORTS_URL: str = "https://torexgold.com/investors/financial-reports/"

    # Configuración para el logging (opcional, pero bueno tenerlo)
    LOG_LEVEL: str = "INFO"

    class Config:
        # Si tienes un archivo .env, Pydantic lo leerá automáticamente.
        # Para mayor claridad, lo cargamos explícitamente arriba con load_dotenv().
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = "ignore" # Ignora variables de entorno extra que no estén definidas en Settings

# Instancia global de las configuraciones para ser importada en otros módulos
settings = Settings()

# Validación simple al cargar la configuración
if settings.GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE" or not settings.GEMINI_API_KEY:
    print("ADVERTENCIA: GEMINI_API_KEY no está configurada. Por favor, añádela a tu archivo .env o como variable de entorno.")

if "user:password@db" in settings.DATABASE_URL and (settings.DATABASE_URL.startswith("postgresql://user:password@db")):
     print(f"INFO: Usando configuración de base de datos por defecto: {settings.DATABASE_URL}")

