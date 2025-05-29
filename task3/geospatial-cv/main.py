from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
import uuid
import shutil
from pathlib import Path
import asyncio
from .services import GeospatialProcessor
from .models import Database, ProcessingResult

app = FastAPI(title="Geospatial Computer Vision API", version="1.0.0")

# Initialize services
processor = GeospatialProcessor()
db = Database()

# Ensure directories exist
Path("uploads").mkdir(exist_ok=True)
Path("models").mkdir(exist_ok=True)

@app.post("/api/v1/analyze-map")
async def analyze_map(file: UploadFile = File(...)):
    """Analyze map image for geospatial information"""
    
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Save uploaded file
    file_path = f"uploads/{job_id}_{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Save job to database
    db.save_job(job_id, "processing", file_path)
    
    # Process asynchronously
    asyncio.create_task(process_map_async(file_path, job_id))
    
    return JSONResponse({
        "job_id": job_id,
        "status": "processing",
        "message": "Map analysis started"
    })

async def process_map_async(file_path: str, job_id: str):
    """Async map processing"""
    result = await processor.process_map(file_path, job_id)
    
    # Update database
    db.save_job(job_id, result.status, file_path, str(result.__dict__))

@app.get("/api/v1/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and results"""
    
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JSONResponse({
        "job_id": job_id,
        "status": job["status"],
        "created_at": job["created_at"],
        "result": job["result"] if job["result"] else None
    })

@app.get("/api/v1/jobs/{job_id}/segments/{segment_name}")
async def get_segment(job_id: str, segment_name: str):
    """Download extracted segment"""
    
    segment_path = Path(f"uploads/{segment_name}")
    if not segment_path.exists():
        raise HTTPException(status_code=404, detail="Segment not found")
    
    return FileResponse(segment_path)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "geospatial-cv"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)