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

# Job tracking - USE CONSISTENT VARIABLE NAMES
jobs = {}  # Changed from jobs_queue to jobs for consistency
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
try:
    processor = LeafmapGroundwaterProcessor(data_dir=os.getenv("DATA_DIR"))
    logger.info(f"✅ Processor initialized with data_dir: {processor.data_dir}")
except Exception as e:
    logger.error(f"❌ Failed to initialize processor: {e}")
    processor = None

# Serve frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    logger.info(f"✅ Mounted static files from {FRONTEND_DIR}")

@app.get("/")
async def root():
    """Serve the main HTML interface"""
    try:
        index_path = FRONTEND_DIR / "index.html"
        logger.info(f"Attempting to serve: {index_path}")
        
        if not index_path.exists():
            return JSONResponse(
                status_code=404,
                content={"error": "index.html not found"}
            )
        
        return FileResponse(str(index_path))
    except Exception as e:
        logger.error(f"Error serving root: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/test")
async def test():
    """Simple test endpoint"""
    return {
        "status": "ok",
        "message": "API is working",
        "frontend_exists": FRONTEND_DIR.exists(),
        "index_exists": (FRONTEND_DIR / "index.html").exists(),
        "data_dir": DATA_DIR,
        "processor_ok": processor is not None
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "processor": "leafmap",
        "processor_initialized": processor is not None
    }

@app.get("/api/debug/simple")
async def simple_debug():
    """Simple debug endpoint"""
    output_dir = os.path.join(DATA_DIR, "output")
    return {
        "status": "ok",
        "message": "Debug endpoint is working",
        "data_dir": DATA_DIR,
        "output_dir_exists": os.path.exists(output_dir),
        "jobs_count": len(jobs),
        "cache_count": len(results_cache)
    }

@app.get("/api/debug/check/{job_id}")
async def check_job_simple(job_id: str):
    """Simple job check"""
    result = {
        "job_id": job_id,
        "job_exists": job_id in jobs,
        "cache_exists": job_id in results_cache,
        "output_files": []
    }
    
    # Check output directory for any files with this job_id
    output_dir = os.path.join(DATA_DIR, "output")
    if os.path.exists(output_dir):
        for f in os.listdir(output_dir):
            if job_id in f or job_id.replace("-", "") in f:
                result["output_files"].append(f)
    
    return result

@app.get("/api/debug/processor")
async def debug_processor():
    """Test if processor is working"""
    if processor is None:
        return {"status": "error", "message": "Processor not initialized"}
    
    try:
        # Test directory creation
        processor._ensure_data_directories()
        
        return {
            "status": "ok",
            "data_dir": processor.data_dir,
            "dir_exists": os.path.exists(processor.data_dir),
            "writable": os.access(processor.data_dir, os.W_OK) if os.path.exists(processor.data_dir) else False
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "trace": traceback.format_exc()
        }

@app.get("/api/debug/results/{job_id}")
async def debug_results(job_id: str):
    """Debug endpoint to check result status"""
    debug_info = {
        "job_id": job_id,
        "job_exists": job_id in jobs,
        "cache_exists": job_id in results_cache,
        "data_dir": DATA_DIR,
        "output_dir_exists": os.path.exists(os.path.join(DATA_DIR, "output")),
        "files_found": []
    }
    
    if job_id in results_cache:
        result = results_cache[job_id]
        debug_info["result_keys"] = list(result.keys())
        
        # Check expected files
        if "interactive_url" in result:
            filename = result["interactive_url"].split("/")[-1]
            file_path = os.path.join(DATA_DIR, "output", filename)
            debug_info["html_file_exists"] = os.path.exists(file_path)
            debug_info["html_file_path"] = file_path
            
        if "thumbnail_path" in result:
            debug_info["thumb_file_exists"] = os.path.exists(result["thumbnail_path"])
    
    # List all files in output directory
    output_dir = os.path.join(DATA_DIR, "output")
    if os.path.exists(output_dir):
        debug_info["files_found"] = os.listdir(output_dir)[:10]
    
    return debug_info

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

@app.post("/api/groundwater/analyze")
async def analyze_groundwater(request: GroundwaterRequest, background_tasks: BackgroundTasks):
    """Analyze groundwater potential using AHP"""
    try:
        if processor is None:
            raise HTTPException(status_code=500, detail="Processor not initialized")
        
        job_id = str(uuid.uuid4())
        logger.info(f"Starting analysis job {job_id}")
        
        # Get weights based on scheme
        if request.weighting_scheme == "custom" and request.custom_weights:
            weights = request.custom_weights
        else:
            weights = WEIGHTING_SCHEMES.get(request.weighting_scheme, WEIGHTING_SCHEMES["balanced"])
        
        # Queue for processing - USE 'jobs' consistently
        jobs[job_id] = {"status": "processing", "request": request.dict()}
        
        # Process in background
        background_tasks.add_task(
            process_groundwater_job,
            job_id, request.extent, weights, request.season
        )
        
        return {
            "job_id": job_id,
            "status": "processing",
            "weights_used": weights
        }
    except Exception as e:
        logger.error(f"Error in analyze_groundwater: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

async def process_groundwater_job(job_id: str, extent: list, weights: dict, season: str):
    """Background processing of groundwater analysis"""
    logger.info(f"🚀 Starting job {job_id}")
    
    try:
        # Run leafmap analysis
        result = processor.full_ahp_analysis(
            extent=extent,
            weights=weights,
            season=season
        )
        logger.info(f"✅ Analysis complete for job {job_id}")
        
        # Store result - USE CONSISTENT VARIABLES
        results_cache[job_id] = result
        jobs[job_id] = {"status": "completed", "result": job_id}
        logger.info(f"Job {job_id} stored in cache")
        
    except Exception as e:
        logger.error(f"❌ Job {job_id} failed: {e}")
        logger.error(traceback.format_exc())
        jobs[job_id] = {"status": "failed", "error": str(e)}

@app.get("/api/groundwater/status/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job["status"] == "completed":
        return {
            "job_id": job_id,
            "status": "completed",
            "result_url": f"/results/{job_id}.html",  # Use job_id directly
            "thumbnail_url": f"/thumbnails/{job_id}.png",
            "statistics": results_cache.get(job_id, {}).get("statistics", {})
        }
    elif job["status"] == "failed":
        return {"job_id": job_id, "status": "failed", "error": job.get("error", "Unknown error")}
    else:
        return {"job_id": job_id, "status": "processing"}

@app.get("/results/{job_id}.html")
async def get_result_html(job_id: str):
    """Get the interactive HTML map for a completed job"""
    try:
        # Check multiple possible locations
        possible_paths = [
            os.path.join(DATA_DIR, "output", f"gwpz_{job_id}.html"),
            os.path.join(DATA_DIR, "output", f"{job_id}.html"),
            os.path.join(DATA_DIR, "thumbnails", f"gwpz_{job_id}.html")
        ]
        
        # Also check if in cache with different filename
        if job_id in results_cache:
            result = results_cache[job_id]
            if "interactive_url" in result:
                filename = result["interactive_url"].split("/")[-1]
                possible_paths.append(os.path.join(DATA_DIR, "output", filename))
        
        for file_path in possible_paths:
            if os.path.exists(file_path):
                logger.info(f"Found HTML file at {file_path}")
                return FileResponse(file_path)
        
        # If still not found, list directory contents
        output_dir = os.path.join(DATA_DIR, "output")
        files = os.listdir(output_dir) if os.path.exists(output_dir) else []
        logger.error(f"HTML not found. Files in output: {files}")
        
        raise HTTPException(status_code=404, detail=f"HTML file not found for job {job_id}")
            
    except Exception as e:
        logger.error(f"Error serving result HTML: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/thumbnails/{job_id}.png")
async def get_thumbnail(job_id: str):
    """Get the thumbnail PNG for a completed job"""
    try:
        possible_paths = [
            os.path.join(DATA_DIR, "thumbnails", f"gwpz_{job_id}.png"),
            os.path.join(DATA_DIR, "output", f"gwpz_{job_id}.png"),
            os.path.join(DATA_DIR, "thumbnails", f"{job_id}.png"),
            os.path.join(DATA_DIR, "output", f"{job_id}.png")
        ]
        
        for file_path in possible_paths:
            if os.path.exists(file_path):
                logger.info(f"Found thumbnail at {file_path}")
                return FileResponse(file_path)
        
        raise HTTPException(status_code=404, detail=f"Thumbnail not found for job {job_id}")
            
    except Exception as e:
        logger.error(f"Error serving thumbnail: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug/clean")
async def clean_jobs():
    """Clean up stuck jobs"""
    global jobs, results_cache
    
    jobs.clear()
    results_cache.clear()
    
    # Clean up files
    cleaned = []
    for subdir in ["output", "cache", "thumbnails"]:
        dir_path = os.path.join(DATA_DIR, subdir)
        if os.path.exists(dir_path):
            for f in os.listdir(dir_path):
                if f.endswith(('.tif', '.png', '.html')):
                    try:
                        os.remove(os.path.join(dir_path, f))
                        cleaned.append(f)
                    except:
                        pass
    
    return {
        "status": "cleaned",
        "jobs_cleared": len(jobs),
        "cache_cleared": len(results_cache),
        "files_removed": len(cleaned)
    }

@app.get("/api/test/minimal")
async def test_minimal():
    """Run a minimal analysis for testing"""
    try:
        if processor is None:
            return {"status": "error", "message": "Processor not initialized"}
        
        test_extent = [36.7, -1.5, 36.9, -1.3]
        test_weights = {"geology": 0.3, "rainfall": 0.3, "slope": 0.2, "landuse": 0.2}
        
        result = processor.full_ahp_analysis(
            extent=test_extent,
            weights=test_weights,
            season="transitional"
        )
        
        return {
            "status": "success",
            "message": "Analysis completed",
            "has_result": bool(result),
            "statistics": result.get("statistics")
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "trace": traceback.format_exc()
        }