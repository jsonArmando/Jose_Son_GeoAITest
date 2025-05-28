# app/main.py
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from app.adapters import db_adapter
from app.core import schemas, use_cases
from app.config import settings # Para acceder a START_YEAR, END_YEAR por defecto

# --- Creación de la aplicación FastAPI ---
app = FastAPI(
    title="Financial Report Extractor API",
    description="API para extraer datos de informes financieros usando Arquitectura Hexagonal y AI Agents.",
    version="0.1.0"
)

# --- Evento de inicio de la aplicación: Crear tablas en la DB ---
@app.on_event("startup")
def on_startup():
    """
    Al iniciar la aplicación, se asegura de que todas las tablas
    de la base de datos estén creadas.
    """
    print("Aplicación iniciándose...")
    print(f"Usando DATABASE_URL: {settings.DATABASE_URL[:settings.DATABASE_URL.find('@') + 1]}********") # No loguear pass
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("ADVERTENCIA SERIA: GEMINI_API_KEY no está configurada. Las funciones de IA no operarán.")
    else:
        print("GEMINI_API_KEY configurada.")
    db_adapter.create_db_tables()
    print("Tablas de la base de datos verificadas/creadas.")
    print("API lista. Documentación interactiva en /docs")


# --- Dependencias ---
# Para inyectar la sesión de base de datos en los endpoints
def get_db_session():
    db = db_adapter.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Endpoints de la API ---

API_V1_PREFIX = "/api/v1"

@app.post(f"{API_V1_PREFIX}/reports/trigger-extraction", response_model=schemas.TriggerExtractionResponse)
async def trigger_extraction_process(
    background_tasks: BackgroundTasks, # Para ejecutar el proceso en segundo plano
    request_body: Optional[schemas.TriggerExtractionRequest] = None, # Hacer el body opcional
    db: Session = Depends(get_db_session)
):
    """
    Inicia el proceso de extracción de informes financieros.
    Este proceso puede ser largo, por lo que se ejecuta en segundo plano.
    """
    start_year_req = settings.START_YEAR
    end_year_req = settings.END_YEAR

    if request_body:
        if request_body.start_year is not None:
            start_year_req = request_body.start_year
        if request_body.end_year is not None:
            end_year_req = request_body.end_year
            
    if start_year_req > end_year_req:
        raise HTTPException(status_code=400, detail="El año de inicio no puede ser mayor que el año de fin.")

    # Para esta versión simplificada, la orquestación es síncrona dentro de la tarea de fondo.
    # En una app real, esto podría delegarse a un worker Celery.
    
    # Primero, obtener la lista de URLs para dar una respuesta inmediata.
    # La lógica de scraping es rápida.
    try:
        report_infos = report_fetcher_adapter.fetch_financial_report_urls(start_year_req, end_year_req)
        if not report_infos:
            return schemas.TriggerExtractionResponse(
                message="No se encontraron informes en el sitio web para el rango de años especificado. No se inició procesamiento en segundo plano.",
                reports_identified_count=0,
                report_urls_found=[]
            )
        
        # Disparar la tarea de fondo para el procesamiento completo
        # Pasamos los mismos años para que el use_case vuelva a hacer el fetch (o podríamos pasar report_infos)
        # Para consistencia, dejamos que el use_case haga el fetch de nuevo.
        background_tasks.add_task(use_cases.orchestrate_report_extraction_process, db, start_year_req, end_year_req)
        
        return schemas.TriggerExtractionResponse(
            message=f"Proceso de extracción iniciado en segundo plano para {len(report_infos)} informes identificados. Consulta /summary para ver el progreso.",
            reports_identified_count=len(report_infos),
            report_urls_found=[r.report_url for r in report_infos]
        )
    except Exception as e:
        # Capturar cualquier excepción durante el fetch inicial para responder adecuadamente
        print(f"Error al intentar obtener URLs para trigger_extraction: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener lista inicial de informes: {str(e)}")


@app.get(f"{API_V1_PREFIX}/reports/extracted-data/{{report_id}}", response_model=schemas.ExtractedReportDataResponse)
def get_extracted_data(report_id: int, db: Session = Depends(get_db_session)):
    """
    Obtiene los datos extraídos y el score de precisión para un informe específico por su ID.
    """
    report_data = use_cases.get_report_data_by_id(db, report_id)
    if report_data is None:
        raise HTTPException(status_code=404, detail=f"Informe con ID {report_id} no encontrado.")
    return report_data

@app.get(f"{API_V1_PREFIX}/reports/summary", response_model=schemas.AllReportsSummaryResponse)
def get_reports_summary(db: Session = Depends(get_db_session)):
    """
    Obtiene un resumen de todos los informes procesados, su estado y scores.
    """
    summary_data = use_cases.get_all_reports_summary(db)
    return summary_data

# --- Rutas Adicionales (Opcional) ---
@app.get("/")
def read_root():
    """Ruta raíz simple para verificar que la API está funcionando."""
    return {"message": "Bienvenido a la API de Extracción de Informes Financieros. Visita /docs para la documentación."}

# Nota: Para una aplicación de producción, se añadiría manejo de errores más robusto,
# logging centralizado, autenticación/autorización si es necesario, etc.
# El uso de BackgroundTasks es una simplificación; Celery sería más robusto para tareas largas.
