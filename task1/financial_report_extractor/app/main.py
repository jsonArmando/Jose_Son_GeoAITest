# app/main.py
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware # <--- IMPORTACIÓN AÑADIDA
from sqlalchemy.orm import Session
from typing import List, Optional

from adapters import db_adapter, report_fetcher_adapter
from core import schemas, use_cases
from config import settings 

app = FastAPI(
    title="Financial Report Extractor API",
    description="API para extraer datos de informes financieros usando Arquitectura Hexagonal y AI Agents.",
    version="0.1.0"
)

# --- CONFIGURACIÓN DE CORS ---
origins = [
    "http://localhost",         # Si accedes directamente a la API desde el navegador en localhost
    "http://localhost:3000",    # El origen de tu frontend React en desarrollo
    # "https://tu-dominio-de-frontend-desplegado.com" # Ejemplo para producción
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # Lista de orígenes permitidos
    allow_credentials=True,      # Permite cookies (si las usaras)
    allow_methods=["*"],         # Permite todos los métodos (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],         # Permite todas las cabeceras
)
# --- FIN DE CONFIGURACIÓN DE CORS ---

@app.on_event("startup")
def on_startup():
    print("Aplicación iniciándose...")
    print(f"Usando DATABASE_URL: {settings.DATABASE_URL[:settings.DATABASE_URL.find('@') + 1]}********")
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("ADVERTENCIA SERIA: GEMINI_API_KEY no está configurada. Las funciones de IA no operarán.")
    else:
        print("GEMINI_API_KEY configurada.")
    db_adapter.create_db_tables()
    print("Tablas de la base de datos verificadas/creadas.")
    print("API lista. Documentación interactiva en /docs")

def get_db_session():
    db = db_adapter.SessionLocal()
    try:
        yield db
    finally:
        db.close()

API_V1_PREFIX = "/api/v1"

@app.post(f"{API_V1_PREFIX}/reports/trigger-extraction", response_model=schemas.TriggerExtractionResponse)
async def trigger_extraction_process_endpoint(
    background_tasks: BackgroundTasks,
    request_body: Optional[schemas.TriggerExtractionRequest] = None,
):
    start_year_req = settings.START_YEAR
    end_year_req = settings.END_YEAR

    if request_body:
        if request_body.start_year is not None:
            start_year_req = request_body.start_year
        if request_body.end_year is not None:
            end_year_req = request_body.end_year
            
    if start_year_req > end_year_req:
        raise HTTPException(status_code=400, detail="El año de inicio no puede ser mayor que el año de fin.")

    try:
        report_infos = report_fetcher_adapter.fetch_financial_report_urls(start_year_req, end_year_req)
        
        if not report_infos:
            return schemas.TriggerExtractionResponse(
                message="No se encontraron informes en el sitio web para el rango de años especificado. No se inició procesamiento en segundo plano.",
                reports_identified_count=0,
                report_urls_found=[]
            )
        
        background_tasks.add_task(use_cases.orchestrate_report_extraction_process, 
                                  db_adapter.SessionLocal, 
                                  start_year_req, 
                                  end_year_req)
        
        return schemas.TriggerExtractionResponse(
            message=f"Proceso de extracción iniciado en segundo plano para {len(report_infos)} informes identificados. Consulta /summary para ver el progreso.",
            reports_identified_count=len(report_infos),
            report_urls_found=[r.report_url for r in report_infos]
        )
    except NameError as ne: 
        print(f"NameError en trigger_extraction_process_endpoint: {ne}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(ne)}")
    except Exception as e:
        print(f"Error al intentar obtener URLs para trigger_extraction: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar la solicitud de extracción: {str(e)}")


@app.get(f"{API_V1_PREFIX}/reports/extracted-data/{{report_id}}", response_model=schemas.ExtractedReportDataResponse)
def get_extracted_data(report_id: int, db: Session = Depends(get_db_session)):
    report_data = use_cases.get_report_data_by_id(db, report_id)
    if report_data is None:
        raise HTTPException(status_code=404, detail=f"Informe con ID {report_id} no encontrado.")
    return report_data

@app.get(f"{API_V1_PREFIX}/reports/summary", response_model=schemas.AllReportsSummaryResponse)
def get_reports_summary(db: Session = Depends(get_db_session)):
    summary_data = use_cases.get_all_reports_summary(db)
    return summary_data

@app.get(f"{API_V1_PREFIX}/reports/annual-table/{{year}}", response_model=Optional[schemas.AnnualReportTableResponse])
def get_annual_table_view(year: int, db: Session = Depends(get_db_session)):
    table_data = use_cases.get_formatted_annual_table(db, year)
    if not table_data: # Si devuelve None, significa que no hay datos o informes procesados
        # Devolver un 404 es apropiado si no hay datos para ese año.
        # El mensaje de log "No se encontraron informes procesados..." ya se imprime en use_cases.
        raise HTTPException(status_code=404, detail=f"No se encontraron datos consolidados para el año {year} o no hay informes procesados con éxito.")
    return table_data


@app.get("/")
def read_root():
    return {"message": "Bienvenido a la API de Extracción de Informes Financieros. Visita /docs para la documentación."}
