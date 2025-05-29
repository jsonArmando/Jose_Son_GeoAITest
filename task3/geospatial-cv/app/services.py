import cv2
import numpy as np
import easyocr
from ultralytics import YOLO
from shapely.geometry import Polygon, Point
import re
import redis
import json
from typing import List, Dict, Tuple
from .models import Coordinate, DetectedObject, RegionOfInterest, ProcessingResult

class GeospatialProcessor:
    def __init__(self):
        self.yolo_model = YOLO('models/yolov8n.pt')  # Base model, ideally fine-tuned
        self.ocr_reader = easyocr.Reader(['en'])
        self.redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)
        
        # Patterns for coordinate detection
        self.coord_patterns = [
            r'(\d{1,3}[°º]\d{1,2}[\'′]\d{1,2}[\"″][NS])',  # DMS format
            r'(\d{1,3}\.\d+[°º][NS])',                       # Decimal degrees
            r'(\d{1,3}[°º]\d{1,2}[\'′][NS])',               # DM format
            r'(\d+\.\d+[,\s]+\d+\.\d+)',                    # Decimal lat,lon
        ]
    
    async def process_map(self, image_path: str, job_id: str) -> ProcessingResult:
        """Main processing pipeline"""
        try:
            # Step 1: Load and preprocess image
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Cannot load image: {image_path}")
            
            # Step 2: YOLO Detection for cartographic elements
            detected_objects = self._detect_cartographic_elements(image)
            
            # Step 3: OCR on detected text regions
            coordinates = self._extract_coordinates(image, detected_objects)
            
            # Step 4: Geometric analysis and region extraction
            regions = self._analyze_spatial_relationships(image, coordinates, detected_objects)
            
            # Step 5: Create result
            result = ProcessingResult(
                job_id=job_id,
                status="completed",
                detected_objects=detected_objects,
                coordinates=coordinates,
                regions=regions
            )
            
            # Cache result
            self.redis_client.setex(f"job:{job_id}", 3600, json.dumps(result.__dict__, default=str))
            
            return result
            
        except Exception as e:
            error_result = ProcessingResult(
                job_id=job_id,
                status=f"failed: {str(e)}",
                detected_objects=[],
                coordinates=[],
                regions=[]
            )
            self.redis_client.setex(f"job:{job_id}", 3600, json.dumps(error_result.__dict__, default=str))
            return error_result
    
    def _detect_cartographic_elements(self, image: np.ndarray) -> List[DetectedObject]:
        """Detect cartographic elements using YOLO"""
        results = self.yolo_model(image, conf=0.25)
        detected_objects = []
        
        for result in results:
            if result.boxes is not None:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = box.conf[0].cpu().numpy()
                    cls = int(box.cls[0].cpu().numpy())
                    
                    # Map classes to cartographic elements (simplified)
                    class_mapping = {0: 'text', 1: 'legend', 2: 'scale_bar', 3: 'grid_line'}
                    class_name = class_mapping.get(cls, 'unknown')
                    
                    detected_objects.append(DetectedObject(
                        bbox=[int(x1), int(y1), int(x2), int(y2)],
                        class_name=class_name,
                        confidence=float(conf)
                    ))
        
        return detected_objects
    
    def _extract_coordinates(self, image: np.ndarray, detected_objects: List[DetectedObject]) -> List[Coordinate]:
        """Extract coordinates using OCR on detected text regions"""
        coordinates = []
        
        # Filter text objects
        text_objects = [obj for obj in detected_objects if obj.class_name == 'text']
        
        for text_obj in text_objects:
            x1, y1, x2, y2 = text_obj.bbox
            roi = image[y1:y2, x1:x2]
            
            # OCR on region
            ocr_results = self.ocr_reader.readtext(roi)
            
            for (bbox, text, confidence) in ocr_results:
                if confidence > 0.5:
                    # Try to parse coordinates
                    coord = self._parse_coordinate_text(text)
                    if coord:
                        coordinates.append(Coordinate(
                            lat=coord[0],
                            lon=coord[1], 
                            confidence=confidence,
                            text=text
                        ))
        
        return coordinates
    
    def _parse_coordinate_text(self, text: str) -> Tuple[float, float] | None:
        """Parse coordinate text to lat/lon"""
        text = text.strip().upper()
        
        # Simple decimal degree pattern
        decimal_match = re.search(r'(\d+\.\d+)[,\s]+(\d+\.\d+)', text)
        if decimal_match:
            lat, lon = float(decimal_match.group(1)), float(decimal_match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return (lat, lon)
        
        # DMS pattern (simplified)
        dms_match = re.search(r'(\d+)[°º](\d+)[\'′]?(\d+)?[\"″]?([NS])', text)
        if dms_match:
            deg, min_val, sec_val, direction = dms_match.groups()
            decimal = float(deg) + float(min_val)/60
            if sec_val:
                decimal += float(sec_val)/3600
            if direction == 'S':
                decimal = -decimal
            if -90 <= decimal <= 90:
                return (decimal, 0)  # Simplified - need both lat and lon
        
        return None
    
    def _analyze_spatial_relationships(self, image: np.ndarray, coordinates: List[Coordinate], 
                                     detected_objects: List[DetectedObject]) -> List[RegionOfInterest]:
        """Analyze spatial relationships and extract regions"""
        regions = []
        
        if not coordinates:
            return regions
        
        # Group coordinates that are spatially close
        coord_groups = self._group_nearby_coordinates(coordinates)
        
        for group in coord_groups:
            if len(group) >= 2:
                # Calculate bounding region
                lats = [c.lat for c in group]
                lons = [c.lon for c in group]
                
                # Convert to pixel coordinates (simplified)
                pixel_bbox = self._geo_to_pixel_bbox(image, min(lats), max(lats), min(lons), max(lons))
                
                # Extract segment
                segment_path = self._extract_image_segment(image, pixel_bbox)
                
                regions.append(RegionOfInterest(
                    coordinates=group,
                    segment_path=segment_path,
                    bbox=pixel_bbox
                ))
        
        return regions
    
    def _group_nearby_coordinates(self, coordinates: List[Coordinate]) -> List[List[Coordinate]]:
        """Group spatially nearby coordinates"""
        if not coordinates:
            return []
        
        groups = []
        used = set()
        
        for i, coord1 in enumerate(coordinates):
            if i in used:
                continue
                
            group = [coord1]
            used.add(i)
            
            for j, coord2 in enumerate(coordinates[i+1:], i+1):
                if j in used:
                    continue
                    
                # Simple distance threshold
                if abs(coord1.lat - coord2.lat) < 1.0 and abs(coord1.lon - coord2.lon) < 1.0:
                    group.append(coord2)
                    used.add(j)
            
            groups.append(group)
        
        return groups
    
    def _geo_to_pixel_bbox(self, image: np.ndarray, min_lat: float, max_lat: float, 
                          min_lon: float, max_lon: float) -> List[int]:
        """Convert geographic bounds to pixel coordinates (simplified)"""
        h, w = image.shape[:2]
        
        # Simplified linear mapping - in reality needs proper projection
        x1 = int((min_lon + 180) / 360 * w)
        x2 = int((max_lon + 180) / 360 * w)
        y1 = int((90 - max_lat) / 180 * h)
        y2 = int((90 - min_lat) / 180 * h)
        
        return [max(0, x1), max(0, y1), min(w, x2), min(h, y2)]
    
    def _extract_image_segment(self, image: np.ndarray, bbox: List[int]) -> str:
        """Extract and save image segment"""
        x1, y1, x2, y2 = bbox
        segment = image[y1:y2, x1:x2]
        
        segment_path = f"uploads/segment_{hash(str(bbox))}.jpg"
        cv2.imwrite(segment_path, segment)
        
        return segment_path