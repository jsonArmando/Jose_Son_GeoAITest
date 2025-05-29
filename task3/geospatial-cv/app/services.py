import cv2
import numpy as np
import easyocr
from ultralytics import YOLO
import re
import redis
import json
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import asyncio
import uuid
import logging

logger = logging.getLogger(__name__)

# Los modelos ahora se importan donde se usan o se pasan como dependencias.
# Para esta estructura, asumimos que se importan desde un módulo 'models'.
from .models import Coordinate, DetectedObject, RegionOfInterest, ProcessingResultData

class GeospatialProcessor:
    def __init__(self, redis_host: str = 'localhost', yolo_model_path: str = 'models/yolov8n.pt'):
        self.yolo_model_path = Path(yolo_model_path) # Usar Path object
        if not self.yolo_model_path.exists():
            logger.warning(f"Modelo YOLO no encontrado en {self.yolo_model_path}. La detección de objetos podría fallar.")
        # Carga del modelo podría fallar, manejarlo apropiadamente.
        try:
            self.yolo_model = YOLO(str(self.yolo_model_path))
        except Exception as e:
            logger.critical(f"Fallo al cargar el modelo YOLO desde {self.yolo_model_path}: {e}", exc_info=True)
            raise # Relanzar para que la app sepa que el procesador no es funcional

        logger.info("Inicializando EasyOCR Reader...")
        try:
            self.ocr_reader = easyocr.Reader(['en']) # Puede tomar tiempo y descargar modelos
            logger.info("EasyOCR Reader inicializado.")
        except Exception as e:
            logger.critical(f"Fallo al inicializar EasyOCR Reader: {e}", exc_info=True)
            raise

        self.redis_client: Optional[redis.Redis] = None
        if redis_host:
            try:
                self.redis_client = redis.Redis(host=redis_host, port=6379, decode_responses=True)
                self.redis_client.ping()
                logger.info(f"Conectado exitosamente a Redis en {redis_host}:6379.")
            except redis.exceptions.ConnectionError as e:
                logger.warning(f"No se pudo conectar a Redis en {redis_host}:6379. El caché estará deshabilitado. Error: {e}")
                self.redis_client = None
        else:
            logger.info("No se proporcionó host de Redis. El caché estará deshabilitado.")


    async def _run_in_threadpool(self, func, *args, **kwargs):
        """Ejecuta una función síncrona en el threadpool del event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs) # None usa el default ThreadPoolExecutor

    async def process_map_image(self, image_path: str, job_id: str) -> ProcessingResultData:
        """
        Procesa la imagen del mapa y devuelve los datos del resultado.
        Lanza excepciones si el procesamiento falla.
        """
        logger.info(f"Iniciando process_map_image para job_id: {job_id}, imagen: {image_path}")
        
        # Cargar imagen
        image = await self._run_in_threadpool(cv2.imread, image_path)
        if image is None:
            logger.error(f"No se pudo cargar la imagen: {image_path} para job_id: {job_id}")
            raise ValueError(f"No se pudo cargar la imagen: {image_path}")

        # Detección de elementos cartográficos (YOLO)
        # Notar que _detect_cartographic_elements_sync ahora es un método regular
        detected_objects_list = await self._run_in_threadpool(self._detect_cartographic_elements_sync, image)
        
        # Extracción de coordenadas (OCR)
        coordinates_list = await self._run_in_threadpool(self._extract_coordinates_sync, image, detected_objects_list)
        
        # Análisis espacial y extracción de regiones
        regions_list = await self._run_in_threadpool(self._analyze_spatial_relationships_sync, image, coordinates_list, detected_objects_list, job_id)
        
        logger.info(f"Procesamiento de imagen completado para job_id: {job_id}")
        
        return ProcessingResultData(
            detected_objects=detected_objects_list,
            coordinates=coordinates_list,
            regions=regions_list
        )

    # --- Métodos síncronos de procesamiento (ejecutados en threadpool) ---
    def _detect_cartographic_elements_sync(self, image: np.ndarray) -> List[DetectedObject]:
        logger.debug(f"Ejecutando YOLO en imagen de tamaño: {image.shape}")
        results = self.yolo_model(image, conf=0.25) # Síncrono
        detected_objects = []
        class_mapping = {0: 'text', 1: 'legend', 2: 'scale_bar', 3: 'grid_line'} 

        for result_item in results:
            if result_item.boxes is not None:
                for box in result_item.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    cls_idx = int(box.cls[0].cpu().numpy())
                    class_name = class_mapping.get(cls_idx, f'coco_class_{cls_idx}') # Adaptar si tienes un modelo personalizado
                    detected_objects.append(DetectedObject(
                        bbox=[x1, y1, x2, y2],
                        class_name=class_name,
                        confidence=conf
                    ))
        logger.debug(f"YOLO detectó {len(detected_objects)} objetos.")
        return detected_objects

    def _extract_coordinates_sync(self, image: np.ndarray, detected_objects: List[DetectedObject]) -> List[Coordinate]:
        # (Implementación similar a la anterior, pero asegúrate que devuelve List[Coordinate])
        logger.debug("Extrayendo coordenadas con OCR...")
        # ... (tu lógica de OCR) ...
        return [] # Placeholder

    def _analyze_spatial_relationships_sync(self, image: np.ndarray, coordinates: List[Coordinate], 
                                           detected_objects: List[DetectedObject], job_id: str) -> List[RegionOfInterest]:
        # (Implementación similar a la anterior, pero asegúrate que devuelve List[RegionOfInterest])
        logger.debug("Analizando relaciones espaciales...")
        # ... (tu lógica de análisis) ...
        return [] # Placeholder

    def _extract_image_segment_sync(self, image: np.ndarray, bbox: List[int], job_id: str, uploads_dir: Path) -> str:
        """Extrae y guarda un segmento de imagen, devolviendo el nombre del archivo."""
        x1, y1, x2, y2 = bbox
        if not (0 <= y1 < y2 <= image.shape[0] and 0 <= x1 < x2 <= image.shape[1]):
            logger.warning(f"Bbox inválido para segmentar: {bbox} para imagen {image.shape}, job {job_id}")
            # Podrías lanzar un error o devolver un nombre de archivo indicativo de error
            return f"error_segment_bbox_{job_id}_{uuid.uuid4().hex[:8]}.jpg"

        segment = image[y1:y2, x1:x2]
        segment_filename = f"segment_{job_id}_{uuid.uuid4().hex[:8]}.jpg"
        segment_full_path = uploads_dir / segment_filename
        
        try:
            cv2.imwrite(str(segment_full_path), segment)
            logger.info(f"Segmento guardado: {segment_full_path} para job {job_id}")
            return segment_filename
        except Exception as e:
            logger.error(f"Error al guardar segmento {segment_full_path} para job {job_id}: {e}", exc_info=True)
            # Podrías lanzar un error o devolver un nombre de archivo indicativo de error
            return f"error_segment_save_{job_id}_{uuid.uuid4().hex[:8]}.jpg"

    # ... (otros métodos helpers como _dms_to_decimal, _parse_coordinate_text, etc. sin cambios funcionales)

    # --- Gestión de Caché (Ejemplo) ---
    async def get_cached_result(self, job_id: str) -> Optional[ProcessingResultData]:
        if not self.redis_client:
            return None
        try:
            cached_json = await self._run_in_threadpool(self.redis_client.get, f"job_result:{job_id}")
            if cached_json:
                logger.info(f"Cache hit para resultado de job: {job_id}")
                return ProcessingResultData.model_validate_json(cached_json)
        except Exception as e:
            logger.warning(f"Error al obtener resultado de caché para job {job_id}: {e}", exc_info=True)
        return None

    async def cache_result(self, job_id: str, result_data: ProcessingResultData, ttl: int = 3600):
        if not self.redis_client:
            return
        try:
            result_json = result_data.model_dump_json()
            await self._run_in_threadpool(self.redis_client.setex, f"job_result:{job_id}", ttl, result_json)
            logger.info(f"Resultado para job {job_id} cacheado por {ttl} segundos.")
        except Exception as e:
            logger.warning(f"Error al cachear resultado para job {job_id}: {e}", exc_info=True)