import fitz  # PyMuPDF
import os
from pathlib import Path
import base64
from typing import List, Dict
import logging

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PDFImageExtractor:
    """
    Extractor de imágenes de PDF optimizado con filtrado básico
    para imágenes pequeñas e intento de mejorar la calidad.
    Ahora también detecta y renderiza tablas vectoriales/de texto como imágenes.
    """

    def __init__(self, images_dir: str = "images", min_width: int = 100, min_height: int = 100, render_dpi: int = 150):
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.min_width = min_width
        self.min_height = min_height
        self.render_dpi = render_dpi # DPI para renderizar tablas
        logger.info(f"PDFImageExtractor inicializado. Directorio de imágenes: {self.images_dir}, Filtro de tamaño: >{min_width}x{min_height}px, DPI para renderizar tablas: {self.render_dpi}")

    def _is_significant_overlap(self, bbox1: fitz.Rect, bbox2: fitz.Rect, threshold: float = 0.75) -> bool:
        """
        Verifica si dos rectángulos (bboxes) tienen una superposición significativa (IoU).
        """
        intersection = fitz.Rect(bbox1) # Crear una copia para no modificar el original
        intersection.intersect(bbox2)
        
        if intersection.is_empty:
            return False

        area1 = bbox1.width * bbox1.height
        area2 = bbox2.width * bbox2.height
        intersection_area = intersection.width * intersection.height

        if area1 == 0 or area2 == 0: # Evitar división por cero si un área es 0
            return False

        union_area = area1 + area2 - intersection_area
        if union_area == 0: # Evitar división por cero si la unión es 0 (áreas idénticas y 0)
             return True # Considerar superposición total si ambas áreas son 0 y se intersectan (aunque raro)
        
        iou = intersection_area / union_area
        return iou > threshold

    def extract_images(self, pdf_path: str, document_id: str) -> List[Dict]:
        try:
            pdf_document = fitz.open(pdf_path)
            extracted_images_data = []
            image_counter = 0 # Contador global para todas las imágenes (raster y renderizadas)

            logger.info(f"Procesando PDF: {pdf_path} para el ID de documento: {document_id}")

            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                extracted_raster_bboxes_on_page = [] # Almacenar bboxes de imágenes raster ya extraídas en esta página

                # --- PASO 1: Extraer imágenes rasterizadas existentes ---
                logger.info(f"Página {page_num + 1}/{len(pdf_document)}: Buscando imágenes rasterizadas.")
                img_list_on_page = page.get_images(full=True)
                
                logger.info(f"Página {page_num + 1}: {len(img_list_on_page)} objetos de imagen encontrados antes de filtrar (raster).")

                for img_index_on_page, img_info in enumerate(img_list_on_page):
                    xref = img_info[0]
                    if xref == 0:
                        logger.debug(f"Omitiendo imagen inline (xref=0) en la página {page_num + 1}")
                        continue

                    try:
                        base_image = pdf_document.extract_image(xref)
                        if not base_image:
                            logger.warning(f"No se pudo extraer la imagen con xref {xref} en la página {page_num + 1}")
                            continue
                        
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        width = base_image["width"]
                        height = base_image["height"]

                        if width < self.min_width or height < self.min_height:
                            logger.info(f"Imagen rasterizada omitida debido al tamaño: {width}x{height} (xref: {xref}, página: {page_num + 1})")
                            continue
                        
                        # Obtener el bounding box de la imagen rasterizada para posible deduplicación
                        try:
                            # get_image_bbox puede tomar el item de get_images() o el xref
                            img_bbox = page.get_image_bbox(img_info) 
                            extracted_raster_bboxes_on_page.append(img_bbox)
                        except Exception as bbox_ex:
                            logger.warning(f"No se pudo obtener el bbox para la imagen raster xref {xref} en la página {page_num + 1}: {bbox_ex}. Se continuará sin deduplicación para esta imagen.")


                        image_filename = f"{document_id}_p{page_num + 1}_raster_{img_index_on_page}_idx{image_counter}.{image_ext}"
                        image_path = self.images_dir / image_filename

                        with open(image_path, "wb") as img_file:
                            img_file.write(image_bytes)
                        logger.debug(f"Imagen rasterizada extraída a: {image_path}")

                        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

                        extracted_images_data.append({
                            "image_id": f"{document_id}_p{page_num + 1}_raster_{img_index_on_page}_idx{image_counter}",
                            "document_id": document_id,
                            "page_number": page_num + 1,
                            "image_index_on_page": img_index_on_page, # Índice de la imagen raster en la página
                            "global_image_index": image_counter,
                            "filename": image_filename,
                            "initial_file_path": str(image_path),
                            "format": image_ext,
                            "width": width,
                            "height": height,
                            "size_bytes": len(image_bytes),
                            "base64_data": image_base64,
                            "source_type": "raster" # Indica que es una imagen raster original
                        })
                        image_counter += 1
                    
                    except Exception as e:
                        logger.error(f"Error extrayendo imagen raster específica (xref: {xref}, página: {page_num + 1}): {e}", exc_info=True)
                        continue
                
                # --- PASO 2: Detectar y renderizar tablas vectoriales/de texto ---
                logger.info(f"Página {page_num + 1}/{len(pdf_document)}: Buscando tablas para renderizar.")
                try:
                    # Opciones de find_tables(): strategy="lines", "text", "both". Default es "fancy".
                    # Otras opciones como snap_tolerance, join_tolerance pueden ser útiles.
                    tables_on_page = page.find_tables() 
                except Exception as ft_e:
                    logger.warning(f"Error al ejecutar find_tables en la página {page_num + 1}: {ft_e}. Se omitirán las tablas renderizadas para esta página.")
                    tables_on_page = [] # Devuelve un TableFinder, accedemos a .tables

                logger.info(f"Página {page_num + 1}: {len(tables_on_page.tables)} tablas encontradas por find_tables.")

                for table_index_on_page, table in enumerate(tables_on_page.tables): # tables_on_page es un TableFinder
                    table_bbox = fitz.Rect(table.bbox) # table.bbox es una tupla (x0, y0, x1, y1)

                    # Comprobación de superposición básica con imágenes raster ya extraídas
                    is_duplicate = False
                    for raster_bbox in extracted_raster_bboxes_on_page:
                        if self._is_significant_overlap(table_bbox, raster_bbox):
                            logger.info(f"Tabla renderizada en la página {page_num + 1}, tabla idx {table_index_on_page} parece ser un duplicado de una imagen raster ya extraída. Omitiendo.")
                            is_duplicate = True
                            break
                    if is_duplicate:
                        continue

                    table_width = table_bbox.width
                    table_height = table_bbox.height

                    if table_width < self.min_width or table_height < self.min_height:
                        logger.info(f"Tabla renderizada omitida en la página {page_num + 1} debido al tamaño: {table_width:.2f}x{table_height:.2f}")
                        continue

                    try:
                        # Renderizar la región de la tabla a un pixmap
                        pix = page.get_pixmap(clip=table_bbox, dpi=self.render_dpi)
                        table_image_bytes = pix.tobytes("png") # Guardar como PNG
                        table_image_ext = "png"
                    except Exception as render_e:
                        logger.warning(f"No se pudo renderizar la tabla {table_index_on_page} en la página {page_num + 1} a imagen: {render_e}")
                        continue
                    
                    if not table_image_bytes:
                        logger.warning(f"La imagen de la tabla renderizada está vacía para la tabla {table_index_on_page} en la página {page_num + 1}")
                        continue

                    image_filename = f"{document_id}_p{page_num + 1}_table_{table_index_on_page}_idx{image_counter}.{table_image_ext}"
                    image_path = self.images_dir / image_filename
                    current_image_id = f"{document_id}_p{page_num + 1}_table_{table_index_on_page}_idx{image_counter}"

                    with open(image_path, "wb") as img_file:
                        img_file.write(table_image_bytes)
                    logger.debug(f"Imagen de tabla renderizada y guardada en: {image_path}")

                    image_base64 = base64.b64encode(table_image_bytes).decode('utf-8')

                    extracted_images_data.append({
                        "image_id": current_image_id,
                        "document_id": document_id,
                        "page_number": page_num + 1,
                        "image_index_on_page": table_index_on_page, # Índice de la tabla detectada en la página
                        "global_image_index": image_counter,
                        "filename": image_filename,
                        "initial_file_path": str(image_path),
                        "format": table_image_ext,
                        "width": pix.width, # Ancho del pixmap renderizado
                        "height": pix.height, # Alto del pixmap renderizado
                        "size_bytes": len(table_image_bytes),
                        "base64_data": image_base64,
                        "source_type": "rendered_table" # Indica que es una tabla renderizada
                    })
                    image_counter += 1
            
            pdf_document.close()
            logger.info(f"PDF {pdf_path} procesado. Imágenes totales para clasificación: {len(extracted_images_data)}")
            return extracted_images_data
            
        except Exception as e:
            logger.error(f"Error crítico procesando PDF {pdf_path}: {e}", exc_info=True)
            if 'pdf_document' in locals() and pdf_document: # Asegurarse de cerrar el documento si está abierto
                pdf_document.close()
            return []

if __name__ == '__main__':
    test_pdf_path = "test_document.pdf" 
    doc_id_test = "test_doc_001"
    
    # Crear un PDF de prueba simple si no existe (este PDF de prueba NO tendrá tablas vectoriales complejas)
    # Para probar la extracción de tablas, necesitarás un PDF que SÍ las contenga.
    if not os.path.exists(test_pdf_path):
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.units import inch

            logger.info(f"Creando PDF de prueba '{test_pdf_path}'...")
            c = canvas.Canvas(test_pdf_path, pagesize=letter)
            c.drawString(1*inch, 10*inch, "Página 1 con texto de prueba.")
            
            # Simular una tabla simple con líneas (esto es vectorial)
            c.drawString(1*inch, 9*inch, "Tabla Vectorial Simple:")
            xlist = [1*inch, 2.5*inch, 4*inch]
            ylist = [8*inch, 8.5*inch]
            c.grid(xlist, ylist)
            c.drawString(xlist[0]+0.1*inch, ylist[0]+0.05*inch, "Celda A1")
            c.drawString(xlist[1]+0.1*inch, ylist[0]+0.05*inch, "Celda B1")

            # Añadir una imagen de prueba (simulando una imagen raster)
            # (Necesitarías tener una imagen 'test_image.png' o similar en el directorio)
            # try:
            #     test_image_path = "test_image.png" # Asegúrate que esta imagen exista
            #     if os.path.exists(test_image_path):
            #         c.drawImage(test_image_path, 1*inch, 5*inch, width=2*inch, height=2*inch)
            #     else:
            #         logger.warning(f"Imagen de prueba '{test_image_path}' no encontrada. No se añadirá al PDF de prueba.")
            # except Exception as img_err:
            #     logger.warning(f"No se pudo añadir la imagen de prueba al PDF: {img_err}")

            c.showPage()
            c.save()
            logger.info(f"PDF de prueba '{test_pdf_path}' creado. Este PDF contiene una tabla vectorial simple.")
            logger.info("Para pruebas más exhaustivas, usa PDFs que contengan tablas complejas.")
        except ImportError:
            logger.warning("ReportLab no está instalado. No se puede crear el PDF de prueba. Asegúrate que 'test_document.pdf' exista y contenga imágenes y/o tablas.")
        except Exception as pdf_gen_err:
            logger.error(f"Error creando PDF de prueba: {pdf_gen_err}")


    if os.path.exists(test_pdf_path):
        main_images_dir_test = Path("test_run_extracted_images_con_tablas")
        # Configura el extractor con parámetros de prueba, incluyendo DPI
        extractor = PDFImageExtractor(images_dir=str(main_images_dir_test), min_width=50, min_height=50, render_dpi=96)
        images = extractor.extract_images(test_pdf_path, doc_id_test)
        
        if images:
            logger.info(f"Imágenes extraídas del PDF de prueba ({doc_id_test}) al ejecutar el script directamente:")
            for img_data in images:
                logger.info(f"  - ID: {img_data['image_id']}, Ruta Inicial: {img_data['initial_file_path']}, Tipo: {img_data.get('source_type', 'desconocido')}, Dimensiones: {img_data['width']}x{img_data['height']}")
        else:
            logger.info(f"No se extrajeron imágenes (o ninguna pasó el filtro) del PDF de prueba: {test_pdf_path}")
    else:
        logger.error(f"El archivo PDF de prueba '{test_pdf_path}' no existe. Por favor, créalo o especifica una ruta válida y asegúrate que contenga imágenes y/o tablas.")