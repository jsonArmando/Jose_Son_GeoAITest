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
    Optimized PDF image extractor with basic filtering
    for small images and an attempt to improve quality.
    """

    def __init__(self, images_dir: str = "images", min_width: int = 100, min_height: int = 100):
        self.images_dir = Path(images_dir) 
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.min_width = min_width
        self.min_height = min_height
        logger.info(f"PDFImageExtractor initialized. Image directory: {self.images_dir}, Size filter: >{min_width}x{min_height}px")

    def extract_images(self, pdf_path: str, document_id: str) -> List[Dict]:
        try:
            pdf_document = fitz.open(pdf_path)
            extracted_images_data = []
            image_counter = 0 

            logger.info(f"Processing PDF: {pdf_path} for document ID: {document_id}")

            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                img_list = page.get_images(full=True) 

                logger.info(f"Page {page_num + 1}/{len(pdf_document)}: {len(img_list)} image objects found before filtering.")

                for img_index_on_page, img_info in enumerate(img_list):
                    xref = img_info[0]
                    if xref == 0: 
                        logger.debug(f"Skipping inline image (xref=0) on page {page_num + 1}")
                        continue

                    try:
                        base_image = pdf_document.extract_image(xref)
                        if not base_image:
                            logger.warning(f"Could not extract image with xref {xref} on page {page_num + 1}")
                            continue
                            
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        width = base_image["width"]
                        height = base_image["height"]

                        if width < self.min_width or height < self.min_height:
                            logger.info(f"Image skipped due to size: {width}x{height} (xref: {xref}, page: {page_num + 1})")
                            continue

                        image_filename = f"{document_id}_p{page_num + 1}_idx{image_counter}.{image_ext}"
                        image_path = self.images_dir / image_filename

                        with open(image_path, "wb") as img_file:
                            img_file.write(image_bytes)
                        logger.debug(f"Image extracted to: {image_path}")

                        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

                        extracted_images_data.append({
                            "image_id": f"{document_id}_p{page_num + 1}_idx{image_counter}",
                            "document_id": document_id,
                            "page_number": page_num + 1, 
                            "image_index_on_page": img_index_on_page, 
                            "global_image_index": image_counter, 
                            "filename": image_filename,
                            "initial_file_path": str(image_path), 
                            "format": image_ext,
                            "width": width,
                            "height": height,
                            "size_bytes": len(image_bytes),
                            "base64_data": image_base64
                        })
                        image_counter += 1
                        
                    except Exception as e:
                        logger.error(f"Error extracting specific image (xref: {xref}, page: {page_num + 1}): {e}", exc_info=True)
                        continue
            
            pdf_document.close()
            logger.info(f"PDF {pdf_path} processed. Total images for classification: {len(extracted_images_data)}")
            return extracted_images_data
            
        except Exception as e:
            logger.error(f"Critical error processing PDF {pdf_path}: {e}", exc_info=True)
            return []

if __name__ == '__main__':
    test_pdf_path = "test_document.pdf" 
    doc_id_test = "test_doc_001"
    
    if not os.path.exists(test_pdf_path):
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            c = canvas.Canvas(test_pdf_path, pagesize=letter)
            c.drawString(100, 750, "Page 1 with test text.")
            c.showPage()
            c.save()
            logger.info(f"Test PDF '{test_pdf_path}' created. Add images manually for better testing.")
        except ImportError:
            logger.warning("ReportLab not installed. Cannot create test PDF. Ensure 'test_document.pdf' exists and has images.")

    if os.path.exists(test_pdf_path):
        main_images_dir_test = Path("test_run_extracted_images")
        extractor = PDFImageExtractor(images_dir=str(main_images_dir_test), min_width=50, min_height=50)
        images = extractor.extract_images(test_pdf_path, doc_id_test)
        if images:
            logger.info(f"Images extracted from test PDF ({doc_id_test}) when running script directly:")
            for img_data in images:
                logger.info(f"  - ID: {img_data['image_id']}, Initial Path: {img_data['initial_file_path']}")
        else:
            logger.info(f"No images were extracted (or none passed the filter) from test PDF: {test_pdf_path}")
    else:
        logger.error(f"Test PDF file '{test_pdf_path}' does not exist. Please create it or specify a valid path and ensure it contains images.")