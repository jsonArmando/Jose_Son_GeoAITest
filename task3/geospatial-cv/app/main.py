import fastapi # Necesario para BackgroundTasks
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
import uuid
import shutil
from pathlib import Path
import os
import json
import logging
import datetime # Para JobStatus
import asyncio
logger = logging.getLogger(__name__)

# --- Configuración de Logging Global ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("geospatial_api")
# --- Fin Configuración de Logging ---

# --- Importaciones de la Aplicación ---
# Estas importaciones SON CRUCIALES y deben ser correctas para tu estructura de proyecto.
# Si main.py está en 'app/' y los otros en 'app/', y ejecutas desde el padre de 'app/':
from .models import (
    DatabaseManager, # <-- CORREGIDO: Se usa DatabaseManager en lugar de Database
    JobStatus,
    ProcessingResultData
)
from .services import GeospatialProcessor
# NO necesitas importar DetectedObject, Coordinate, RegionOfInterest aquí directamente
# porque ProcessingResultData y JobStatus los encapsulan, y Pydantic maneja su (de)serialización.

# --- Directorios de la Aplicación ---
APP_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = APP_ROOT.parent
UPLOADS_DIR = PROJECT_ROOT / "uploads"
MODELS_DIR = PROJECT_ROOT / "models" # Donde esperas el modelo YOLO

# Crear directorios si no existen
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# --- Inicialización de la Aplicación FastAPI ---
# ESTA LÍNEA DEBE ESTAR ANTES DE USAR @app.on_event o @app.ruta
app = FastAPI(
    title="Advanced Geospatial Computer Vision API",
    version="1.0.0",  # Cambiado de 2.0.0 a 1.0.0
    description="API optimizada para análisis geoespacial con manejo de tareas en segundo plano."
)
# --- FIN Inicialización de la Aplicación FastAPI ---

# --- Estado de la Aplicación y Dependencias ---
app_state = {} # Para mantener instancias de servicios si es necesario

# --- Eventos de Ciclo de Vida de la Aplicación ---
@app.on_event("startup")
async def startup_event():
    logger.info("Iniciando aplicación FastAPI...")
    # Configuración
    redis_host = os.getenv("REDIS_HOST", "localhost")
    yolo_model_path = str(MODELS_DIR / os.getenv("YOLO_MODEL_PATH", "yolov8n.pt"))

    try:
        # Usa DatabaseManager aquí
        app_state["db_manager"] = DatabaseManager(db_path=str(PROJECT_ROOT / "geospatial_jobs.db"))
        app_state["geospatial_processor"] = GeospatialProcessor(
            redis_host=redis_host,
            yolo_model_path=yolo_model_path
        )
        logger.info("DatabaseManager y GeospatialProcessor inicializados y listos.")
    except Exception as e:
        logger.critical(f"Error crítico durante el inicio de la aplicación: {e}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Cerrando aplicación FastAPI...")
    # Aquí podrías cerrar conexiones si fuera necesario

# --- Funciones de Dependencia ---
def get_db_manager() -> DatabaseManager: # Asegúrate que DatabaseManager esté importado
    db = app_state.get("db_manager")
    if db is None:
        # Esto no debería ocurrir si el evento startup se completó correctamente.
        logger.error("DatabaseManager no encontrado en app_state.")
        raise HTTPException(status_code=500, detail="Error interno del servidor: DatabaseManager no inicializado.")
    return db

def get_geospatial_processor() -> GeospatialProcessor: # Asegúrate que GeospatialProcessor esté importado
    processor = app_state.get("geospatial_processor")
    if processor is None:
        logger.error("GeospatialProcessor no encontrado en app_state.")
        raise HTTPException(status_code=500, detail="Error interno del servidor: GeospatialProcessor no inicializado.")
    return processor

# --- Tarea de Procesamiento en Segundo Plano ---
async def run_map_processing_task(
    job_id: str,
    image_path_str: str,
    db: DatabaseManager, # Se pasará la instancia
    processor: GeospatialProcessor # Se pasará la instancia
):
    logger.info(f"[BackgroundTask] Iniciando procesamiento para job_id: {job_id}, imagen: {image_path_str}")
    try:
        processing_result_data = await processor.process_map_image(image_path_str, job_id)
        db.update_job_completed(job_id, processing_result_data)
        logger.info(f"[BackgroundTask] Job {job_id} completado exitosamente.")
        # (Opcional) Cachear el resultado: await processor.cache_result(job_id, processing_result_data)
    except ValueError as ve:
        logger.error(f"[BackgroundTask] Error de valor procesando job {job_id}: {ve}", exc_info=True)
        db.update_job_failed(job_id, f"Error de procesamiento: {str(ve)}")
    except Exception as e:
        logger.error(f"[BackgroundTask] Error inesperado procesando job {job_id}: {e}", exc_info=True)
        db.update_job_failed(job_id, f"Error inesperado del servidor: {str(e)}")

# --- Endpoints de la API ---
@app.post("/api/v1/analyze-map", response_model=JobStatus, status_code=202)  # Cambiado de v2 a v1
async def analyze_map_v1(  # Cambiado nombre de función
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: DatabaseManager = Depends(get_db_manager),
    processor: GeospatialProcessor = Depends(get_geospatial_processor)
):
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen.")

    job_id = str(uuid.uuid4())
    file_path = UPLOADS_DIR / f"{job_id}_{file.filename}"

    try:
        logger.info(f"Guardando archivo para nuevo job {job_id}: {file_path}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        file_size = file_path.stat().st_size
        logger.info(f"Archivo guardado: {file.filename}, Tamaño: {file_size} bytes.")
    except Exception as e:
        logger.error(f"Error al guardar archivo para job {job_id}: {e}", exc_info=True)
        if file.file and not file.file.closed: file.file.close()
        raise HTTPException(status_code=500, detail=f"No se pudo guardar el archivo: {e}")
    finally:
        if file.file and not file.file.closed: file.file.close()

    job_status_obj = db.create_job(job_id, str(file_path), file.filename, file_size)
    
    background_tasks.add_task(
        run_map_processing_task,
        job_id,
        str(file_path),
        db,
        processor
    )
    logger.info(f"Tarea en segundo plano añadida para job_id: {job_id}")
    
    return job_status_obj

@app.get("/api/v1/jobs/{job_id}", response_model=JobStatus)  # Cambiado de v2 a v1
async def get_job_status_v1(job_id: str, db: DatabaseManager = Depends(get_db_manager)):  # Cambiado nombre de función
    logger.info(f"Solicitando estado para job_id: {job_id}")
    job = db.get_job(job_id)
    if not job:
        logger.warning(f"Job no encontrado para job_id: {job_id}")
        raise HTTPException(status_code=404, detail="Job not found")
    logger.info(f"Retornando estado para job_id {job_id}: {job.status}")
    return job

@app.get("/api/v1/jobs/{job_id}/segments/{segment_filename}")  # Cambiado de v2 a v1
async def get_segment_v1(job_id: str, segment_filename: str, db: DatabaseManager = Depends(get_db_manager)):  # Cambiado nombre de función
    logger.info(f"Solicitando segmento '{segment_filename}' para job_id: {job_id}")
    
    if not segment_filename or ".." in segment_filename or "/" in segment_filename or "\\" in segment_filename :
        logger.warning(f"Intento de path traversal o nombre inválido para segmento: '{segment_filename}', job_id: {job_id}")
        raise HTTPException(status_code=400, detail="Nombre de segmento inválido.")

    job = db.get_job(job_id)
    if not job or not job.result: # job.result es ProcessingResultData
        # Si el job no existe o no tiene resultado (aún procesando o falló sin resultado)
        raise HTTPException(status_code=404, detail="Job o resultado del job no encontrado o aún no disponible.")
    
    segment_found = False
    for region in job.result.regions:
        if region.segment_path == segment_filename:
            segment_found = True
            break
    
    if not segment_found:
        logger.warning(f"Segmento '{segment_filename}' no pertenece o no encontrado en job {job_id}.")
        raise HTTPException(status_code=404, detail=f"Segmento '{segment_filename}' no encontrado para este job.")

    segment_path = UPLOADS_DIR / segment_filename
    if not segment_path.is_file():
        logger.warning(f"Archivo de segmento '{segment_filename}' no encontrado físicamente en {segment_path} para job_id: {job_id}")
        # Esto podría indicar un problema si el job dice que el segmento existe pero el archivo no está.
        raise HTTPException(status_code=404, detail=f"Archivo de segmento '{segment_filename}' no encontrado.")
    
    logger.info(f"Sirviendo segmento '{segment_filename}' para job_id: {job_id}")
    return FileResponse(str(segment_path))

@app.get("/health")
async def health_check_v1(processor: GeospatialProcessor = Depends(get_geospatial_processor)):  # Cambiado nombre de función
    redis_status = "disabled"
    if processor.redis_client:
        redis_status = "disconnected"
        try:
            ping_success = await asyncio.get_running_loop().run_in_executor(None, processor.redis_client.ping)
            if ping_success:
                redis_status = "connected"
        except Exception as e:
            logger.warning(f"Fallo en ping a Redis durante health check: {e}")
            redis_status = "ping_failed"
            
    health_data = {"api_status": "healthy", "service_name": "Geospatial CV API v1", "redis_status": redis_status}  # Cambiado de v2 a v1
    logger.debug(f"Health check response: {health_data}")
    return health_data

# --- Cómo ejecutar (desde el directorio raíz del proyecto, ej. 'geospatial-cv/') ---
# 1. (Opcional) Activa tu entorno virtual.
# 2. Ejecuta Uvicorn:
#    python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    logger.info("Ejecutando FastAPI app directamente (no recomendado para producción).")
    logger.info("Usa 'python -m uvicorn app.main:app --reload' para desarrollo.")
    # import uvicorn
    # uvicorn.run(app, host="0.0.0.0", port=8000)