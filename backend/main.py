"""
Groundwater AHP API - Main application
"""
import sys
import os
from pathlib import Path

# Define FRONTEND_DIR
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = os.getenv("DATA_DIR", "/tmp/groundwater-data")

import logging
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === FIX: Add these missing variables ===
# Job tracking
jobs_queue = {}
results_cache = {}

print(f"🔍 DATA_DIR environment variable: {os.getenv('DATA_DIR')}")
print(f"🔍 Current working directory: {os.getcwd()}")
print(f"🔍 Can write to /tmp: {os.access('/tmp', os.W_OK)}")

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uuid
import hashlib
import json

# Now import from backend module
from backend.models import GroundwaterRequest, GroundwaterResponse, WEIGHTING_SCHEMES
from backend.leafmap_processor import LeafmapGroundwaterProcessor

app = FastAPI(title="Groundwater AHP Platform", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize processor
processor = LeafmapGroundwaterProcessor(data_dir=os.getenv("DATA_DIR"))

# Serve frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Then wrap your root endpoint with error handling:
@app.get("/")
async def root():
    """Serve the main HTML interface"""
    try:
        index_path = FRONTEND_DIR / "index.html"
        logger.info(f"Attempting to serve: {index_path}")
        logger.info(f"File exists: {index_path.exists()}")
        
        if not index_path.exists():
            logger.error(f"index.html not found at {index_path}")
            # List directory contents
            if FRONTEND_DIR.exists():
                logger.info(f"Frontend dir contents: {list(FRONTEND_DIR.glob('*'))}")
            return JSONResponse(
                status_code=404,
                content={"error": "index.html not found", "path": str(index_path)}
            )
        
        return FileResponse(str(index_path))
    except Exception as e:
        logger.error(f"Error serving root: {e}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "trace": traceback.format_exc()}
        )

@app.get("/api/test")
async def test():
    """Simple test endpoint"""
    return {
        "status": "ok",
        "message": "API is working",
        "frontend_exists": FRONTEND_DIR.exists(),
        "index_exists": (FRONTEND_DIR / "index.html").exists(),
        "data_dir": DATA_DIR
    }

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "processor": "leafmap"}

@app.get("/api/study-areas")
async def get_study_areas():
    """Predefined study areas in Kenya"""
    areas = [
        {"name": "lake_naivasha", "description": "Lake Naivasha Basin", 
         "extent": [36.2, -0.8, 36.5, -0.6]},
        {"name": "nairobi", "description": "Nairobi Area", 
         "extent": [36.7, -1.4, 37.0, -1.2]},
        {"name": "coastal", "description": "Coastal Kenya", 
         "extent": [39.5, -4.2, 39.8, -4.0]},
        {"name": "current", "description": "Current Study Area", 
         "extent": [36.7, -1.5, 36.9, -1.3]}
    ]
    return {"study_areas": areas}

@app.get("/api/weighting-schemes")
async def get_weighting_schemes():
    return {"schemes": WEIGHTING_SCHEMES}

@app.post("/api/groundwater/analyze", response_model=GroundwaterResponse)
async def analyze_groundwater(request: GroundwaterRequest, background_tasks: BackgroundTasks):
    """Analyze groundwater potential using AHP"""
    try:
        job_id = str(uuid.uuid4())
        logger.info(f"Starting analysis job {job_id} with request: {request}")
        
        # Get weights based on scheme
        if request.weighting_scheme == "custom" and request.custom_weights:
            weights = request.custom_weights
        else:
            weights = WEIGHTING_SCHEMES.get(request.weighting_scheme, WEIGHTING_SCHEMES["balanced"])
        
        # Queue for processing
        jobs_queue[job_id] = {"status": "processing", "request": request.dict()}
        
        # Process in background
        background_tasks.add_task(
            process_groundwater_job,
            job_id, request.extent, weights, request.season
        )
        
        return GroundwaterResponse(
            job_id=job_id,
            status="processing",
            weights_used=weights
        )
    except Exception as e:
        logger.error(f"Error in analyze_groundwater: {e}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "trace": traceback.format_exc()}
        )

async def process_groundwater_job(job_id: str, extent: list, weights: dict, season: str):
    """Background processing of groundwater analysis"""
    try:
        logger.info(f"Processing job {job_id} with extent {extent}")
        
        # Run leafmap analysis
        result = processor.full_ahp_analysis(
            extent=extent,
            weights=weights,
            season=season
        )
        
        # Store result
        results_cache[job_id] = result
        jobs_queue[job_id] = {"status": "completed", "result": result}
        logger.info(f"Job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        logger.error(traceback.format_exc())
        jobs_queue[job_id] = {"status": "failed", "error": str(e)}

@app.get("/api/groundwater/status/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    
    job = jobs[job_id]
    
    if job["status"] == "completed":
        # Generate cache key from job
        cache_key = hashlib.md5(str(job["result"]).encode()).hexdigest()
        return {
            "job_id": job_id,
            "status": "completed",
            "result_url": f"/results/{cache_key}.html",
            "thumbnail_url": f"/thumbnails/{cache_key}.png",
            "statistics": job["result"]["statistics"]
        }
    elif job["status"] == "failed":
        return {"job_id": job_id, "status": "failed", "error": job["error"]}
    else:
        return {"job_id": job_id, "status": "processing"}

@app.get("/results/{cache_key}.html")
async def get_result_html(cache_key: str):
    if cache_key not in results_cache:
        raise HTTPException(404, "Result not found")
    
    html_content = results_cache[cache_key]["interactive_html"]
    return HTMLResponse(content=html_content)

@app.get("/thumbnails/{cache_key}.png")
async def get_thumbnail(cache_key: str):
    if cache_key not in results_cache:
        raise HTTPException(404, "Thumbnail not found")
    
    return FileResponse(results_cache[cache_key]["thumbnail_path"])
