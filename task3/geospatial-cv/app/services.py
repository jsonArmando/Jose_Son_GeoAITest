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

# Configuración del logger
logger = logging.getLogger(__name__)

# Los modelos ahora se importan donde se usan o se pasan como dependencias.
from .models import Coordinate, DetectedObject, RegionOfInterest, ProcessingResultData

class GeospatialProcessor:
    def __init__(self, redis_host: str = 'localhost', yolo_model_path: str = 'models/yolov8n.pt'):
        self.yolo_model_path = Path(yolo_model_path)
        
        # Inicializar YOLO solo si el modelo existe
        self.yolo_model = None
        if self.yolo_model_path.exists():
            try:
                self.yolo_model = YOLO(str(self.yolo_model_path))
                logger.info(f"Modelo YOLO cargado desde {self.yolo_model_path}")
            except Exception as e:
                logger.warning(f"Error al cargar YOLO: {e}. Continuando sin detección YOLO.")
        else:
            logger.info(f"Modelo YOLO no encontrado en {self.yolo_model_path}. Usando detección alternativa.")

        logger.info("Inicializando EasyOCR Reader...")
        try:
            self.ocr_reader = easyocr.Reader(['en'], gpu=False)  # Deshabilitar GPU para mayor compatibilidad
            logger.info("EasyOCR Reader inicializado correctamente.")
        except Exception as e:
            logger.error(f"Fallo al inicializar EasyOCR Reader: {e}", exc_info=True)
            raise

        # Redis (opcional)
        self.redis_client: Optional[redis.Redis] = None
        if redis_host and redis_host != 'localhost':
            try:
                self.redis_client = redis.Redis(host=redis_host, port=6379, decode_responses=True)
                self.redis_client.ping()
                logger.info(f"Conectado a Redis en {redis_host}:6379.")
            except:
                logger.info("Redis no disponible. Caché deshabilitado.")
                self.redis_client = None

    async def _run_in_threadpool(self, func, *args, **kwargs):
        """Ejecuta една función síncrona en el threadpool del event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)

    async def process_map_image(self, image_path: str, job_id: str) -> ProcessingResultData:
        """
        Procesa la imagen del mapa y devuelve los datos del resultado.
        """
        logger.info(f"🔍 Iniciando análisis completo para job_id: {job_id}")
        
        # Cargar imagen
        image = await self._run_in_threadpool(cv2.imread, image_path)
        if image is None:
            logger.error(f"❌ No se pudo cargar la imagen: {image_path}")
            raise ValueError(f"No se pudo cargar la imagen: {image_path}")

        logger.info(f"📐 Imagen cargada: {image.shape[1]}x{image.shape[0]} pixels")

        # Preprocesar imagen para mejorar OCR
        processed_image = self._preprocess_image_for_ocr(image)

        # 1. Detección de objetos (YOLO si disponible, sino detección básica)
        detected_objects_list = await self._run_in_threadpool(
            self._detect_cartographic_elements_sync, image
        )
        
        # 2. Extracción de coordenadas con OCR mejorado
        coordinates_list = await self._run_in_threadpool(
            self._extract_coordinates_sync, processed_image, detected_objects_list
        )
        
        # 3. Análisis espacial mejorado
        regions_list = await self._run_in_threadpool(
            self._analyze_spatial_relationships_sync, image, coordinates_list, detected_objects_list, job_id
        )
        
        logger.info(f"✅ Procesamiento completado para job_id: {job_id}")
        logger.info(f"📊 Resultados: {len(detected_objects_list)} objetos, {len(coordinates_list)} coordenadas, {len(regions_list)} regiones")
        
        return ProcessingResultData(
            detected_objects=detected_objects_list,
            coordinates=coordinates_list,
            regions=regions_list
        )

    def _preprocess_image_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """Preprocesa la imagen para mejorar la precisión del OCR."""
        # Convertir a escala de grises
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Aplicar un filtro de suavizado para reducir ruido
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # Aplicar umbralización adaptativa para mejorar el contraste
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )
        
        return thresh

    def _detect_cartographic_elements_sync(self, image: np.ndarray) -> List[DetectedObject]:
        """Detecta elementos cartográficos usando YOLO o métodos alternativos."""
        logger.info("🔍 Iniciando detección de elementos cartográficos...")
        detected_objects = []
        
        if self.yolo_model:
            logger.info("🤖 Usando YOLO para detección de objetos...")
            try:
                results = self.yolo_model(image, conf=0.25, verbose=False)
                class_mapping = {0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane', 5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light', 10: 'fire hydrant', 11: 'stop sign', 12: 'parking meter', 13: 'bench', 14: 'bird', 15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep', 19: 'cow', 20: 'elephant', 21: 'bear', 22: 'zebra', 23: 'giraffe', 24: 'backpack', 25: 'umbrella', 26: 'handbag', 27: 'tie', 28: 'suitcase', 29: 'frisbee', 30: 'skis', 31: 'snowboard', 32: 'sports ball', 33: 'kite', 34: 'baseball bat', 35: 'baseball glove', 36: 'skateboard', 37: 'surfboard', 38: 'tennis racket', 39: 'bottle', 40: 'wine glass', 41: 'cup', 42: 'fork', 43: 'knife', 44: 'spoon', 45: 'bowl', 46: 'banana', 47: 'apple', 48: 'sandwich', 49: 'orange', 50: 'broccoli', 51: 'carrot', 52: 'hot dog', 53: 'pizza', 54: 'donut', 55: 'cake', 56: 'chair', 57: 'couch', 58: 'potted plant', 59: 'bed', 60: 'dining table', 61: 'toilet', 62: 'tv', 63: 'laptop', 64: 'mouse', 65: 'remote', 66: 'keyboard', 67: 'cell phone', 68: 'microwave', 69: 'oven', 70: 'toaster', 71: 'sink', 72: 'refrigerator', 73: 'book', 74: 'clock', 75: 'vase', 76: 'scissors', 77: 'teddy bear', 78: 'hair drier', 79: 'toothbrush'}

                for result_item in results:
                    if result_item.boxes is not None:
                        for box in result_item.boxes:
                            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                            conf = float(box.conf[0].cpu().numpy())
                            cls_idx = int(box.cls[0].cpu().numpy())
                            class_name = class_mapping.get(cls_idx, f'unknown_class_{cls_idx}')
                            
                            detected_objects.append(DetectedObject(
                                bbox=[x1, y1, x2, y2],
                                class_name=class_name,
                                confidence=conf
                            ))
                
                logger.info(f"🤖 YOLO detectó {len(detected_objects)} objetos")
                
            except Exception as e:
                logger.warning(f"⚠️ Error en detección YOLO: {e}")
        
        # Detección alternativa basada en contornos y formas
        logger.info("📐 Ejecutando detección alternativa basada en formas...")
        try:
            shape_objects = self._detect_shapes_and_text_regions(image)
            detected_objects.extend(shape_objects)
            logger.info(f"📐 Detección de formas encontró {len(shape_objects)} elementos adicionales")
        except Exception as e:
            logger.warning(f"⚠️ Error en detección de formas: {e}")
        
        logger.info(f"✅ Total de objetos detectados: {len(detected_objects)}")
        return detected_objects

    def _detect_shapes_and_text_regions(self, image: np.ndarray) -> List[DetectedObject]:
        """Detecta formas geométricas y regiones de texto."""
        detected_objects = []
        
        # Convertir a escala de grises
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Detectar contornos
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 100:  # Filtrar contornos muy pequeños
                x, y, w, h = cv2.boundingRect(contour)
                
                # Clasificar por forma aproximada
                approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
                vertices = len(approx)
                
                if vertices == 4:
                    class_name = "rectangle_region"
                elif vertices > 6:
                    class_name = "circle_region"
                else:
                    class_name = "polygon_region"
                
                detected_objects.append(DetectedObject(
                    bbox=[x, y, x + w, y + h],
                    class_name=class_name,
                    confidence=0.7
                ))
        
        return detected_objects

    def _extract_coordinates_sync(self, image: np.ndarray, detected_objects: List[DetectedObject]) -> List[Coordinate]:
        """Extrae coordenadas geográficas usando OCR mejorado."""
        logger.info("🔤 Iniciando extracción de coordenadas con OCR...")
        coordinates = []
        
        try:
            # Ejecutar OCR en toda la imagen
            logger.info("📖 Ejecutando OCR en imagen completa...")
            ocr_results = self.ocr_reader.readtext(image, detail=1, paragraph=False)
            logger.info(f"📖 OCR detectó {len(ocr_results)} elementos de texto")
            
            # Procesar cada resultado de OCR
            for i, (bbox_coords, text, confidence) in enumerate(ocr_results):
                logger.debug(f"📝 Texto {i+1}: '{text}' (confianza: {confidence:.2f})")
                
                # Intentar parsear coordenadas
                coord = self._parse_coordinate_text(text, confidence, bbox_coords)
                if coord:
                    coordinates.append(coord)
                    logger.info(f"🎯 Coordenada encontrada: {coord.lat}, {coord.lon} ('{text}')")
            
            # Buscar patrones específicos de coordenadas en los bordes
            coordinates.extend(self._extract_border_coordinates(image, ocr_results))
            
        except Exception as e:
            logger.error(f"❌ Error durante extracción de coordenadas: {e}", exc_info=True)
        
        logger.info(f"✅ Total de coordenadas extraídas: {len(coordinates)}")
        return coordinates

    def _extract_border_coordinates(self, image: np.ndarray, ocr_results: List) -> List[Coordinate]:
        """Extrae coordenadas específicamente de los bordes del mapa."""
        border_coords = []
        h, w = image.shape[:2]
        
        # Definir regiones de borde (15% de cada lado para cubrir más área)
        border_margin = 0.15
        top_region = int(h * border_margin)
        bottom_region = int(h * (1 - border_margin))
        left_region = int(w * border_margin)
        right_region = int(w * (1 - border_margin))
        
        logger.info("🔍 Buscando coordenadas en bordes del mapa...")
        
        for bbox_coords, text, confidence in ocr_results:
            # Obtener posición del centro del texto
            if len(bbox_coords) >= 4:
                center_x = sum(point[0] for point in bbox_coords) / len(bbox_coords)
                center_y = sum(point[1] for point in bbox_coords) / len(bbox_coords)
                
                # Verificar si está en los bordes
                is_border = (center_y < top_region or center_y > bottom_region or 
                           center_x < left_region or center_x > right_region)
                
                if is_border:
                    coord = self._parse_border_coordinate_text(text, confidence, bbox_coords, center_x, center_y)
                    if coord:
                        border_coords.append(coord)
                        logger.info(f"🎯 Coordenada de borde encontrada: {coord.text}")
        
        return border_coords

    def _parse_coordinate_text(self, text: str, confidence: float, bbox_coords=None) -> Optional[Coordinate]:
        """Parsea texto para extraer coordenadas geográficas, optimizado para UTM."""
        text = text.strip()
        
        # Patrones mejorados para UTM (como en la imagen: E 421500, N 4422150)
        patterns = [
            # Easting (E 421500)
            r'E\s*(\d{6})',
            # Northing (N 4422150)
            r'N\s*(\d{7})',
            # Coordenadas decimales (para otros formatos)
            r'(-?\d+\.?\d*)[°\s]*([NS])?[\s,]*(-?\d+\.?\d*)[°\s]*([EW])?',
            # Grados, minutos, segundos
            r'(-?\d+)[°]\s*(\d+)[\']\s*(\d+\.?\d*)[\"]\s*([NS])[\s,]*(-?\d+)[°]\s*(\d+)[\']\s*(\d+\.?\d*)[\"]\s*([EW])',
        ]
        
        for pattern_idx, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    if pattern_idx == 0:  # Easting (E 421500)
                        return Coordinate(
                            lat=0,  # Placeholder
                            lon=float(match.group(1)),
                            confidence=confidence,
                            text=text
                        )
                    elif pattern_idx == 1:  # Northing (N 4422150)
                        return Coordinate(
                            lat=float(match.group(1)),
                            lon=0,  # Placeholder
                            confidence=confidence,
                            text=text
                        )
                    elif pattern_idx == 2:  # Decimal
                        lat_val = float(match.group(1))
                        lon_val = float(match.group(3))
                        return Coordinate(
                            lat=lat_val,
                            lon=lon_val,
                            confidence=confidence,
                            text=text
                        )
                    elif pattern_idx == 3:  # DMS
                        lat_deg, lat_min, lat_sec, lat_dir = match.group(1), match.group(2), match.group(3), match.group(4)
                        lon_deg, lon_min, lon_sec, lon_dir = match.group(5), match.group(6), match.group(7), match.group(8)
                        
                        lat = float(lat_deg) + float(lat_min)/60 + float(lat_sec)/3600
                        lon = float(lon_deg) + float(lon_min)/60 + float(lon_sec)/3600
                        
                        if lat_dir.upper() == 'S':
                            lat = -lat
                        if lon_dir.upper() == 'W':
                            lon = -lon
                            
                        return Coordinate(
                            lat=lat,
                            lon=lon,
                            confidence=confidence,
                            text=text
                        )
                except (ValueError, IndexError) as e:
                    logger.debug(f"Error parseando coordenada '{text}': {e}")
                    continue
        
        return None

    def _parse_border_coordinate_text(self, text: str, confidence: float, bbox_coords, center_x: float, center_y: float) -> Optional[Coordinate]:
        """Parsea coordenadas específicamente encontradas en bordes."""
        easting_pattern = r'E\s*(\d{6})'
        northing_pattern = r'N\s*(\d{7})'
        
        easting_match = re.search(easting_pattern, text)
        northing_match = re.search(northing_pattern, text)
        
        if easting_match:
            return Coordinate(
                lat=center_y,  # Usar posición en imagen como referencia
                lon=float(easting_match.group(1)),
                confidence=confidence,
                text=text
            )
        elif northing_match:
            return Coordinate(
                lat=float(northing_match.group(1)),
                lon=center_x,  # Usar posición en imagen como referencia
                confidence=confidence,
                text=text
            )
        
        return None

    def _analyze_spatial_relationships_sync(self, image: np.ndarray, coordinates: List[Coordinate], 
                                           detected_objects: List[DetectedObject], job_id: str) -> List[RegionOfInterest]:
        """Analiza relaciones espaciales y crea regiones de interés."""
        logger.info("🗺️ Analizando relaciones espaciales...")
        regions = []
        
        try:
            # Crear regiones basadas en coordenadas encontradas
            for i, coord in enumerate(coordinates):
                logger.info(f"🎯 Procesando coordenada {i+1}: {coord.text}")
                
                # Crear bbox alrededor del área de la coordenada
                if coord.lat != 0 and coord.lon != 0:
                    # Ajustar escala para UTM (simplificado: usar posición relativa)
                    center_x = min(max(int((coord.lon - 421500) / 10), 0), image.shape[1] - 100)
                    center_y = min(max(int((coord.lat - 4422150) / 10), 0), image.shape[0] - 100)
                else:
                    center_x = image.shape[1] // 2
                    center_y = image.shape[0] // 2
                
                # Crear bbox de región
                region_size = 150  # Aumentar tamaño para cubrir más área
                bbox = [
                    max(0, center_x - region_size//2),
                    max(0, center_y - region_size//2),
                    min(image.shape[1], center_x + region_size//2),
                    min(image.shape[0], center_y + region_size//2)
                ]
                
                # Extraer segmento de imagen
                segment_filename = self._extract_image_segment_sync(
                    image, bbox, job_id, Path("uploads")
                )
                
                region = RegionOfInterest(
                    coordinates=[coord],
                    segment_path=segment_filename,
                    bbox=bbox
                )
                regions.append(region)
                logger.info(f"✅ Región creada: {segment_filename}")
            
            # Si no hay coordenadas, crear al menos una región de ejemplo
            if not regions and detected_objects:
                logger.info("🔧 Creando región de ejemplo basada en objetos detectados...")
                obj = detected_objects[0]
                segment_filename = self._extract_image_segment_sync(
                    image, obj.bbox, job_id, Path("uploads")
                )
                
                region = RegionOfInterest(
                    coordinates=[],
                    segment_path=segment_filename,
                    bbox=obj.bbox
                )
                regions.append(region)
        
        except Exception as e:
            logger.error(f"❌ Error en análisis espacial: {e}", exc_info=True)
        
        logger.info(f"✅ Total de regiones creadas: {len(regions)}")
        return regions

    def _extract_image_segment_sync(self, image: np.ndarray, bbox: List[int], job_id: str, uploads_dir: Path) -> str:
        """Extrae y guarda un segmento de imagen."""
        x1, y1, x2, y2 = bbox
        
        # Validar bbox
        if not (0 <= y1 < y2 <= image.shape[0] and 0 <= x1 < x2 <= image.shape[1]):
            logger.warning(f"⚠️ Bbox inválido: {bbox}, ajustando...")
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
            if x1 >= x2 or y1 >= y2:
                x1, y1, x2, y2 = 0, 0, min(100, image.shape[1]), min(100, image.shape[0])

        try:
            segment = image[y1:y2, x1:x2]
            segment_filename = f"segment_{job_id}_{uuid.uuid4().hex[:8]}.jpg"
            segment_full_path = uploads_dir / segment_filename
            
            # Asegurar que el directorio existe
            uploads_dir.mkdir(parents=True, exist_ok=True)
            
            success = cv2.imwrite(str(segment_full_path), segment)
            if success:
                logger.info(f"💾 Segmento guardado: {segment_filename}")
                return segment_filename
            else:
                logger.error(f"❌ Fallo al guardar segmento: {segment_full_path}")
                return f"error_save_{job_id}_{uuid.uuid4().hex[:8]}.jpg"
                
        except Exception as e:
            logger.error(f"❌ Error extrayendo segmento: {e}", exc_info=True)
            return f"error_extract_{job_id}_{uuid.uuid4().hex[:8]}.jpg"

    # --- Gestión de Caché ---
    async def get_cached_result(self, job_id: str) -> Optional[ProcessingResultData]:
        if not self.redis_client:
            return None
        try:
            cached_json = await self._run_in_threadpool(self.redis_client.get, f"job_result:{job_id}")
            if cached_json:
                logger.info(f"📋 Cache hit para job: {job_id}")
                return ProcessingResultData.model_validate_json(cached_json)
        except Exception as e:
            logger.warning(f"⚠️ Error obteniendo caché para job {job_id}: {e}")
        return None

    async def cache_result(self, job_id: str, result_data: ProcessingResultData, ttl: int = 3600):
        if not self.redis_client:
            return
        try:
            result_json = result_data.model_dump_json()
            await self._run_in_threadpool(self.redis_client.setex, f"job_result:{job_id}", ttl, result_json)
            logger.info(f"💾 Resultado cacheado para job {job_id}")
        except Exception as e:
            logger.warning(f"⚠️ Error cacheando resultado para job {job_id}: {e}")