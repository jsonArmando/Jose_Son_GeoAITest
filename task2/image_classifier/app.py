from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import sqlite3
import os
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import openai
# import httpx # Not explicitly needed if openai handles client creation internally
from pdf_processor import PDFImageExtractor 
from typing import List, Dict, Optional, Any
import asyncio
import base64
import shutil 

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Image Extraction and Classification API",
    description="Extracts images from PDF documents and classifies them as 'Map', 'Table', or 'Picture'.",
    version="1.1.5" 
)

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("The OPENAI_API_KEY environment variable is not set.")
openai.api_key = OPENAI_API_KEY
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o") 
logger.info(f"Using OpenAI model: {OPENAI_MODEL}")

# Directories
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "uploads_data")
IMAGES_BASE_DIR = BASE_DIR / os.getenv("IMAGES_DIR", "extracted_images_data")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_BASE_DIR.mkdir(parents=True, exist_ok=True) 

VALID_CLASSIFICATIONS = ["Map", "Table", "Picture"]
ERROR_API_CATEGORY = "ErrorAPI" 
UNKNOWN_RESPONSE_CATEGORY = "Original" 
CATEGORIES_FOLDERS = VALID_CLASSIFICATIONS + [ERROR_API_CATEGORY, UNKNOWN_RESPONSE_CATEGORY]

for category_folder_name in CATEGORIES_FOLDERS:
    (IMAGES_BASE_DIR / category_folder_name).mkdir(parents=True, exist_ok=True)

DB_FILE = BASE_DIR / "database.db"

def init_database():
    logger.info(f"Initializing database at: {DB_FILE}")
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # Ensure this schema matches the one that includes 'image_path'
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                upload_time TEXT NOT NULL,
                status TEXT DEFAULT 'pending', 
                total_images_found INTEGER DEFAULT 0, 
                total_images_extracted INTEGER DEFAULT 0, 
                total_images_classified INTEGER DEFAULT 0,
                error_message TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_classifications (
                id TEXT PRIMARY KEY, 
                image_id TEXT NOT NULL UNIQUE, 
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                global_image_index INTEGER NOT NULL, 
                image_filename TEXT NOT NULL,
                image_path TEXT NOT NULL, 
                classification TEXT, 
                raw_openai_response TEXT, 
                confidence REAL, 
                processing_time_seconds REAL,
                classified_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
            )
        """)
        conn.commit()
    logger.info("Database initialized/verified.")

init_database()
pdf_extractor = PDFImageExtractor(str(IMAGES_BASE_DIR), min_width=150, min_height=150)

class ImageClassifier:
    def __init__(self, model_name: str = OPENAI_MODEL):
        self.model_name = model_name
        if not openai.api_key:
             logger.warning("OpenAI API Key is not configured upon ImageClassifier initialization.")

    async def classify_image_openai(self, image_base64: str, image_id_for_log: str) -> Dict[str, Any]:
        logger.info(f"Classifying image {image_id_for_log} with model {self.model_name}")
        start_time = datetime.now(timezone.utc)
        
        if not openai.api_key:
            logger.error("OpenAI API Key not configured. Cannot classify.")
            return {"classification": ERROR_API_CATEGORY, "raw_response": "OpenAI API Key missing",
                    "confidence": 0.0, "processing_time_seconds": 0.0}
        
        try:
            # Reverted to simpler client initialization.
            # The OpenAI library handles httpx client creation internally.
            # It should also pick up standard proxy env vars (HTTP_PROXY, HTTPS_PROXY) if set.
            client = openai.AsyncOpenAI(max_retries=1) # Still keep max_retries low due to quota issues
            
            response = await client.chat.completions.create(
                model=self.model_name,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", 
                         "text": ("Analyze this image carefully. Considering its content and structure, "
                                  "classify it as exactly one of the following categories: "
                                  "'Map' (if it primarily shows geographical areas, routes, or locations), "
                                  "'Table' (if it primarily consists of data organized in rows and columns), "
                                  "or 'Picture' (for any other type of illustration, photograph, diagram not fitting Map/Table, or complex graphics). "
                                  "Respond with only the single chosen classification word (Map, Table, or Picture). Do not add any other text or punctuation.")},
                        {"type": "image_url",
                         "image_url": { "url": f"data:image/jpeg;base64,{image_base64}", "detail": "low" }}
                    ]}],
                max_tokens=20, 
                temperature=0.0 
            )

            raw_classification = response.choices[0].message.content.strip()
            logger.debug(f"Raw OpenAI response for {image_id_for_log}: '{raw_classification}'")
            
            normalized_class = raw_classification.lower()
            final_class = UNKNOWN_RESPONSE_CATEGORY 
            
            if any(cat.lower() == normalized_class for cat in VALID_CLASSIFICATIONS):
                final_class = next(cat for cat in VALID_CLASSIFICATIONS if cat.lower() == normalized_class)
            elif "map" in normalized_class: final_class = "Map"
            elif "table" in normalized_class: final_class = "Table"
            elif "picture" in normalized_class: final_class = "Picture"

            confidence = 0.95 
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"Image {image_id_for_log} classified as '{final_class}' (raw: '{raw_classification}') in {processing_time:.2f}s.")
            
            return {"classification": final_class, "raw_response": raw_classification,
                    "confidence": confidence, "processing_time_seconds": processing_time}
            
        except openai.RateLimitError as rle:
            logger.error(f"OpenAI RateLimitError (likely insufficient quota) for {image_id_for_log}: {rle.message}", exc_info=False) # Log only message for RLE
            error_info = f"OpenAI RateLimitError: {rle.type if rle.type else type(rle).__name__} - {rle.message}"
            return {"classification": ERROR_API_CATEGORY, "raw_response": error_info,
                    "confidence": 0.0, "processing_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds()}
        except openai.APIError as apie: 
            logger.error(f"OpenAI APIError for {image_id_for_log}: {apie}", exc_info=True)
            error_info = f"OpenAI APIError: {apie.type if apie.type else type(apie).__name__}"
            return {"classification": ERROR_API_CATEGORY, "raw_response": error_info,
                    "confidence": 0.0, "processing_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds()}
        except Exception as e: 
            logger.error(f"Generic error classifying image {image_id_for_log}: {e}", exc_info=True)
            error_info = f"Generic Classification Error: {type(e).__name__}"
            return {"classification": ERROR_API_CATEGORY, "raw_response": error_info,
                    "confidence": 0.0, "processing_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds()}
        # No 'finally' block needed to close client if openai library manages it.
        

image_classifier_instance = ImageClassifier()

def db_execute(query: str, params: tuple = ()):
    try:
        with sqlite3.connect(DB_FILE, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor
    except sqlite3.Error as e:
        logger.error(f"Database error: {e} executing query: {query[:100]}", exc_info=True)
        raise 

def save_classification_to_db(image_id: str, document_id: str, page_num: int, global_idx: int, 
                              img_filename: str, img_final_relative_path: str,
                              classification_result: Dict):
    logger.debug(f"Saving classification for image {image_id} from doc {document_id} to path {img_final_relative_path}")
    db_execute("""
        INSERT INTO image_classifications 
        (id, image_id, document_id, page_number, global_image_index, image_filename, image_path,
         classification, raw_openai_response, confidence, processing_time_seconds, classified_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(uuid.uuid4()), image_id, document_id, page_num, global_idx, img_filename,
        img_final_relative_path, 
        classification_result["classification"], classification_result.get("raw_response", ""),
        classification_result["confidence"], classification_result["processing_time_seconds"],
        datetime.now(timezone.utc).isoformat()
    ))

async def process_document_async(document_id: str, pdf_path_str: str):
    logger.info(f"Starting asynchronous processing for document {document_id} from {pdf_path_str}")
    try:
        db_execute("UPDATE documents SET status = ? WHERE id = ?", ("processing", document_id))

        extracted_images_metadata = pdf_extractor.extract_images(pdf_path_str, document_id)
        num_extracted = len(extracted_images_metadata)
        logger.info(f"Document {document_id}: {num_extracted} images passed initial filter and were extracted.")
        db_execute("UPDATE documents SET total_images_extracted = ? WHERE id = ?", (num_extracted, document_id))
        
        successfully_classified_count = 0
        
        if num_extracted > 0:
            # IMPORTANT: If OpenAI quota issues persist, this semaphore won't fix it.
            # It helps manage request rates for transient limits, not hard quota limits.
            semaphore = asyncio.Semaphore(1) # Keep low if quota is an issue, or adjust based on your OpenAI plan's rate limits.
            
            classification_tasks = []
            for image_data in extracted_images_metadata:
                task = image_classifier_instance.classify_image_openai(
                    image_data["base64_data"], image_data["image_id"]
                )
                classification_tasks.append((task, image_data))

            async def classify_with_semaphore(task_coro, img_data_ref):
                async with semaphore:
                    result = await task_coro
                    return result, img_data_ref

            results_with_data = await asyncio.gather(*(
                classify_with_semaphore(task_coro, img_data) for task_coro, img_data in classification_tasks
            ))

            for classification_result, image_data_ref in results_with_data:
                category_for_folder = classification_result["classification"]
                
                if category_for_folder not in CATEGORIES_FOLDERS:
                    logger.warning(f"Unexpected classification '{category_for_folder}' for image {image_data_ref['image_id']}. Using '{UNKNOWN_RESPONSE_CATEGORY}' for folder.")
                    category_for_folder = UNKNOWN_RESPONSE_CATEGORY

                initial_path = Path(image_data_ref["initial_file_path"])
                target_category_folder = IMAGES_BASE_DIR / category_for_folder
                
                # Ensure target directory exists (should have been created at startup)
                target_category_folder.mkdir(parents=True, exist_ok=True)
                
                final_image_path_on_disk = target_category_folder / initial_path.name
                db_image_path = f"{category_for_folder}/{initial_path.name}"

                try:
                    if initial_path.exists():
                        shutil.move(str(initial_path), str(final_image_path_on_disk))
                        logger.info(f"Moved image {initial_path.name} to {final_image_path_on_disk}")
                    else:
                        logger.warning(f"Initial image file not found for moving: {initial_path}. Classification: {category_for_folder}")
                        # Path in DB will point to a non-existent file if it was already gone.
                except Exception as move_err:
                    logger.error(f"Error moving image {initial_path.name} to {final_image_path_on_disk}: {move_err}. Image remains at {initial_path}")
                    db_image_path = f"{ERROR_API_CATEGORY}/{initial_path.name}" # Or save original path

                save_classification_to_db(
                    document_id=document_id, image_id=image_data_ref["image_id"],
                    page_num=image_data_ref["page_number"], global_idx=image_data_ref["global_image_index"],
                    img_filename=initial_path.name, 
                    img_final_relative_path=db_image_path, 
                    classification_result=classification_result
                )
                
                if classification_result["classification"] in VALID_CLASSIFICATIONS: 
                    successfully_classified_count += 1
                else:
                     logger.warning(f"Image {image_data_ref['image_id']} had classification '{classification_result['classification']}'. Raw response: '{classification_result.get('raw_response')}'")

        logger.info(f"Document {document_id}: {successfully_classified_count}/{num_extracted} images classified into Map/Table/Picture.")
        db_execute("UPDATE documents SET status = ?, total_images_classified = ? WHERE id = ?",
                   ("completed", successfully_classified_count, document_id))
        logger.info(f"Document {document_id} processing completed.")
        
    except Exception as e:
        logger.error(f"Critical error processing document {document_id}: {e}", exc_info=True)
        try:
            db_execute("UPDATE documents SET status = ?, error_message = ? WHERE id = ?",
                       ("failed", str(e), document_id))
        except Exception as db_e_fail:
            logger.error(f"Could not update status to 'failed' for {document_id} after error: {db_e_fail}")
    finally:
        try:
            Path(pdf_path_str).unlink(missing_ok=True)
            logger.info(f"Temporary PDF file {pdf_path_str} deleted.")
        except Exception as e_del:
            logger.error(f"Error deleting temporary PDF file {pdf_path_str}: {e_del}")

# --- Endpoints (upload_pdf, get_document_status, list_documents, health_check) remain the same ---
# --- Ensure they are correctly implemented as in your previous working versions ---

@app.post("/upload-pdf/", status_code=202)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    logger.info(f"Received upload request for file: {file.filename}")
    
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files (.pdf) are allowed.")
    
    if file.content_type and file.content_type != "application/pdf":
         logger.warning(f"Content-Type {file.content_type} is not application/pdf for {file.filename}.")

    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", 50)) * 1024 * 1024
    contents = await file.read()
    await file.seek(0) 

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File exceeds size limit of {MAX_FILE_SIZE // (1024*1024)}MB.")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="The PDF file is empty.")

    document_id = str(uuid.uuid4())
    safe_filename = f"{document_id}_{Path(file.filename).name}"
    file_path = UPLOAD_DIR / safe_filename
    
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(contents) 
        logger.info(f"File {file.filename} saved as {file_path} for doc ID {document_id}")
        
        db_execute("INSERT INTO documents (id, filename, upload_time, status) VALUES (?, ?, ?, ?)",
                   (document_id, file.filename, datetime.now(timezone.utc).isoformat(), 'queued'))
        
        background_tasks.add_task(process_document_async, document_id, str(file_path))
        
        return {"message": "PDF file received and scheduled for processing.",
                "document_id": document_id, "filename": file.filename,
                "status_url": app.url_path_for("get_document_status", document_id=document_id)}
        
    except sqlite3.Error as db_err:
        logger.error(f"Database error during upload of {file.filename}: {db_err}", exc_info=True)
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Internal server error (database): {db_err}")
    except Exception as e:
        logger.error(f"Error processing upload of {file.filename}: {e}", exc_info=True)
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

def _get_row_from_db(query: str, params: tuple) -> Optional[sqlite3.Row]:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row 
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"DB error getting row: {e}")
        return None

def _get_all_rows_from_db(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"DB error getting multiple rows: {e}")
        return []

@app.get("/status/{document_id}")
async def get_document_status(document_id: str):
    logger.info(f"Status request for document ID: {document_id}")
    
    doc_row = _get_row_from_db("SELECT * FROM documents WHERE id = ?", (document_id,))
    if not doc_row:
        raise HTTPException(status_code=404, detail="Document not found.")
    
    classifications_rows = _get_all_rows_from_db("""
        SELECT classification, confidence, image_filename, image_path, page_number, global_image_index, classified_at, raw_openai_response
        FROM image_classifications 
        WHERE document_id = ? ORDER BY page_number, global_image_index
    """, (document_id,))
    
    classified_images_details = []
    for row_data in classifications_rows:
        detail = dict(row_data)
        if detail.get("image_path") and isinstance(detail["image_path"], str):
            serve_path = detail["image_path"].lstrip('/')
            try:
                detail["image_serve_url"] = app.url_path_for("serve_classified_images", path=serve_path)
            except Exception as e:
                logger.warning(f"Could not generate serve URL for {serve_path}: {e}")
                detail["image_serve_url"] = None
        else:
            detail["image_serve_url"] = None
        classified_images_details.append(detail)

    summary = {
        cat: len([r for r in classified_images_details if r["classification"] == cat])
        for cat in CATEGORIES_FOLDERS 
    }
    summary["valid_classifications"] = {
        cat_valid: len([r for r in classified_images_details if r["classification"] == cat_valid])
        for cat_valid in VALID_CLASSIFICATIONS
    }

    return {"document_details": dict(doc_row),
            "classified_images": classified_images_details,
            "classification_summary": summary}

app.mount("/classified_images", StaticFiles(directory=IMAGES_BASE_DIR), name="serve_classified_images")

@app.get("/documents/")
async def list_documents(page: int = 1, page_size: int = 20):
    logger.info(f"Request to list documents: page {page}, page size {page_size}")
    offset = (page - 1) * page_size
    
    documents_rows = _get_all_rows_from_db("""
        SELECT id, filename, upload_time, status, total_images_extracted, total_images_classified, error_message
        FROM documents ORDER BY upload_time DESC LIMIT ? OFFSET ?
    """, (page_size, offset))
    
    total_count_row = _get_row_from_db("SELECT COUNT(*) as count FROM documents", ())
    total_count = total_count_row["count"] if total_count_row else 0
            
    return {"total_documents": total_count, "page": page, "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 0,
            "documents": [dict(row) for row in documents_rows]}

@app.get("/health")
async def health_check():
    db_ok = False
    try:
        with sqlite3.connect(DB_FILE, timeout=1) as conn:
            conn.cursor().execute("SELECT 1")
        db_ok = True
    except Exception as e:
        logger.error(f"Health check: DB Error - {e}")

    return {"status": "healthy" if db_ok else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database_status": "ok" if db_ok else "error"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("app:app", host=host, port=port, reload=True)