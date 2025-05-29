from pydantic import BaseModel, Field
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import sqlite3
from pathlib import Path
import json
import datetime # Para timestamps

# --- Tipos de Datos del Dominio ---
class Coordinate(BaseModel):
    lat: float
    lon: float
    confidence: float
    text: str

class DetectedObject(BaseModel):
    bbox: List[int] = Field(..., min_length=4, max_length=4) # Ejemplo de validación
    class_name: str
    confidence: float

class RegionOfInterest(BaseModel):
    coordinates: List[Coordinate]
    segment_path: str # Nombre del archivo del segmento
    bbox: List[int] = Field(..., min_length=4, max_length=4)

# --- Resultado del Procesamiento ---
# Usaremos un modelo Pydantic para el resultado completo para facilitar la serialización/deserialización
class ProcessingResultData(BaseModel):
    detected_objects: List[DetectedObject] = []
    coordinates: List[Coordinate] = []
    regions: List[RegionOfInterest] = []

class JobStatus(BaseModel):
    job_id: str
    status: str # "processing", "completed", "failed"
    message: Optional[str] = None
    image_path: Optional[str] = None
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    result: Optional[ProcessingResultData] = None # Resultado estructurado
    error_info: Optional[str] = None # Para detalles del error si status es "failed"

    class Config:
        orm_mode = True # Para compatibilidad con ORM si se usa
        json_encoders = {
            datetime.datetime: lambda v: v.isoformat() if v else None
        }


# --- Lógica de Base de Datos ---
class DatabaseManager:
    def __init__(self, db_path: str = "geospatial_jobs.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # Acceder a columnas por nombre
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processing_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    image_path TEXT,
                    result_data TEXT, -- JSON string del ProcessingResultData
                    error_info TEXT,
                    message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)
            # No se necesita trigger si actualizamos updated_at desde la aplicación
            conn.commit()

    def create_job(self, job_id: str, image_path: str, filename: str, file_size: int) -> JobStatus:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        initial_status = "processing"
        message = f"Análisis del mapa '{filename}' (tamaño: {file_size} bytes) iniciado."

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO processing_jobs (job_id, status, image_path, message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, initial_status, image_path, message, now_iso, now_iso)
            )
            conn.commit()
        logger.info(f"Job {job_id} creado en BD. Estado: {initial_status}, Imagen: {image_path}")
        return JobStatus(
            job_id=job_id,
            status=initial_status,
            image_path=image_path,
            message=message,
            created_at=datetime.datetime.fromisoformat(now_iso)
        )

    def update_job_completed(self, job_id: str, result_data: ProcessingResultData):
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result_json = result_data.model_dump_json() # Usar Pydantic para serializar

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE processing_jobs
                SET status = ?, result_data = ?, error_info = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                ("completed", result_json, now_iso, job_id)
            )
            conn.commit()
        logger.info(f"Job {job_id} actualizado a 'completed'. Resultado guardado.")


    def update_job_failed(self, job_id: str, error_message: str):
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE processing_jobs
                SET status = ?, error_info = ?, result_data = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                ("failed", error_message, now_iso, job_id)
            )
            conn.commit()
        logger.warning(f"Job {job_id} actualizado a 'failed'. Error: {error_message}")

    def get_job(self, job_id: str) -> Optional[JobStatus]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM processing_jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                result_data_json = row["result_data"]
                result_data_obj = None
                if result_data_json:
                    try:
                        result_data_obj = ProcessingResultData.model_validate_json(result_data_json)
                    except Exception as e:
                        logger.error(f"Error al deserializar result_data para job {job_id}: {e}. Se retornará None para el resultado.")
                        # Podrías incluso actualizar el job aquí para marcar este problema si es necesario.

                return JobStatus(
                    job_id=row["job_id"],
                    status=row["status"],
                    image_path=row["image_path"],
                    message=row["message"],
                    created_at=datetime.datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                    result=result_data_obj,
                    error_info=row["error_info"]
                )
            return None