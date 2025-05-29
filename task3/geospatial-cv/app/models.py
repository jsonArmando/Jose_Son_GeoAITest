
from pydantic import BaseModel
from typing import List, Tuple, Optional
from dataclasses import dataclass
import sqlite3
from pathlib import Path

class Coordinate(BaseModel):
    lat: float
    lon: float
    confidence: float
    text: str

class DetectedObject(BaseModel):
    bbox: List[int]  # [x1, y1, x2, y2]
    class_name: str
    confidence: float

class RegionOfInterest(BaseModel):
    coordinates: List[Coordinate]
    segment_path: str
    bbox: List[int]

@dataclass
class ProcessingResult:
    job_id: str
    status: str
    detected_objects: List[DetectedObject]
    coordinates: List[Coordinate]
    regions: List[RegionOfInterest]

class Database:
    def __init__(self, db_path: str = "geospatial.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processing_jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT,
                    image_path TEXT,
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    def save_job(self, job_id: str, status: str, image_path: str, result: str = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processing_jobs (id, status, image_path, result) VALUES (?, ?, ?, ?)",
                (job_id, status, image_path, result)
            )
    
    def get_job(self, job_id: str) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "status": row[1], 
                    "image_path": row[2],
                    "result": row[3],
                    "created_at": row[4]
                }
            return None