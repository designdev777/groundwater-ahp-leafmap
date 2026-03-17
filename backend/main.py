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

@app.get("/api/debug/processor")
async def debug_processor():
    """Test if processor is working"""
    try:
        # Test with minimal extent
        test_extent = [36.7, -1.5, 36.9, -1.3]
        test_weights = {"geology": 0.3, "rainfall": 0.3, "slope": 0.2, "landuse": 0.2}
        
        # Just test directory creation
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
        debug_info["files_found"] = os.listdir(output_dir)[:10]  # First 10 files
    
    return debug_info


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
    logger.info(f"🚀 Starting job {job_id}")
    logger.info(f"📊 Extent: {extent}")
    logger.info(f"⚖️ Weights: {weights}")
    logger.info(f"🌦️ Season: {season}")
    
    try:
        # Run leafmap analysis
        logger.info("Calling processor.full_ahp_analysis...")
        result = processor.full_ahp_analysis(
            extent=extent,
            weights=weights,
            season=season
        )
        logger.info(f"✅ Analysis complete for job {job_id}")
        
        # Store result
        results_cache[job_id] = result
        jobs_queue[job_id] = {"status": "completed", "result": job_id}
        logger.info(f"Job {job_id} stored in cache")
        
    except Exception as e:
        logger.error(f"❌ Job {job_id} failed: {e}")
        logger.error(traceback.format_exc())
        jobs_queue[job_id] = {"status": "failed", "error": str(e)}

@app.get("/api/groundwater/status/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs_queue:
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
    """Get the interactive HTML map for a completed job"""
    try:
        # Check if result exists in cache
        if cache_key not in results_cache:
            # Try to find the file directly
            possible_files = [
                os.path.join(DATA_DIR, "output", f"gwpz_{cache_key}.html"),
                os.path.join(DATA_DIR, "output", f"{cache_key}.html"),
                os.path.join(DATA_DIR, "thumbnails", f"gwpz_{cache_key}.html")
            ]
            
            for file_path in possible_files:
                if os.path.exists(file_path):
                    logger.info(f"Found HTML file at {file_path}")
                    return FileResponse(file_path)
            
            raise HTTPException(status_code=404, detail=f"Result not found for key: {cache_key}")
        
        # Get result from cache
        result = results_cache[cache_key]
        logger.info(f"Cache result keys: {result.keys()}")
        
        # Try multiple ways to get the HTML file
        html_path = None
        
        # Method 1: Check interactive_url
        if "interactive_url" in result:
            filename = result["interactive_url"].split("/")[-1]
            html_path = os.path.join(DATA_DIR, "output", filename)
            logger.info(f"Trying path from interactive_url: {html_path}")
        
        # Method 2: Check if interactive_html is stored directly
        if (not html_path or not os.path.exists(html_path)) and "interactive_html" in result:
            # Save the HTML to a file if it's in the cache
            html_path = os.path.join(DATA_DIR, "output", f"{cache_key}.html")
            with open(html_path, 'w') as f:
                f.write(result["interactive_html"])
            logger.info(f"Saved interactive_html to {html_path}")
        
        # Method 3: Look for any HTML file with the cache_key
        if not html_path or not os.path.exists(html_path):
            pattern = os.path.join(DATA_DIR, "output", f"*{cache_key}*.html")
            import glob
            matching_files = glob.glob(pattern)
            if matching_files:
                html_path = matching_files[0]
                logger.info(f"Found matching file: {html_path}")
        
        # Final check
        if html_path and os.path.exists(html_path):
            return FileResponse(html_path)
        else:
            # List all files in output directory for debugging
            output_dir = os.path.join(DATA_DIR, "output")
            files = os.listdir(output_dir) if os.path.exists(output_dir) else []
            logger.error(f"No HTML file found. Files in output: {files[:10]}")
            
            raise HTTPException(
                status_code=404, 
                detail=f"HTML file not found. Cache key: {cache_key}, Tried path: {html_path}"
            )
            
    except Exception as e:
        logger.error(f"Error serving result HTML: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/thumbnails/{cache_key}.png")
async def get_thumbnail(cache_key: str):
    """Get the thumbnail PNG for a completed job"""
    try:
        if cache_key not in results_cache:
            # Try to find the file directly
            possible_files = [
                os.path.join(DATA_DIR, "thumbnails", f"gwpz_{cache_key}.png"),
                os.path.join(DATA_DIR, "output", f"gwpz_{cache_key}.png"),
                os.path.join(DATA_DIR, "thumbnails", f"{cache_key}.png")
            ]
            
            for file_path in possible_files:
                if os.path.exists(file_path):
                    logger.info(f"Found thumbnail at {file_path}")
                    return FileResponse(file_path)
            
            raise HTTPException(status_code=404, detail=f"Thumbnail not found for key: {cache_key}")
        
        result = results_cache[cache_key]
        
        # Try multiple ways to get the thumbnail
        thumb_path = None
        
        # Method 1: Direct thumbnail_path
        if "thumbnail_path" in result and os.path.exists(result["thumbnail_path"]):
            thumb_path = result["thumbnail_path"]
        
        # Method 2: Check result_url for PNG
        if not thumb_path and "result_url" in result:
            filename = result["result_url"].split("/")[-1]
            thumb_path = os.path.join(DATA_DIR, "output", filename)
        
        # Method 3: Look for any PNG with the cache_key
        if not thumb_path or not os.path.exists(thumb_path):
            import glob
            patterns = [
                os.path.join(DATA_DIR, "output", f"*{cache_key}*.png"),
                os.path.join(DATA_DIR, "thumbnails", f"*{cache_key}*.png")
            ]
            for pattern in patterns:
                matching_files = glob.glob(pattern)
                if matching_files:
                    thumb_path = matching_files[0]
                    logger.info(f"Found matching thumbnail: {thumb_path}")
                    break
        
        if thumb_path and os.path.exists(thumb_path):
            return FileResponse(thumb_path)
        else:
            raise HTTPException(status_code=404, detail="Thumbnail file not found")
            
    except Exception as e:
        logger.error(f"Error serving thumbnail: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug/clean")
async def clean_jobs():
    """Clean up stuck jobs"""
    global jobs_queue, results_cache
    
    # Clear everything
    jobs_queue.clear()
    results_cache.clear()
    
    # Also clean up any files in data directory
    import shutil
    data_dirs = [
        f"{DATA_DIR}/output",
        f"{DATA_DIR}/cache",
        f"{DATA_DIR}/thumbnails"
    ]
    
    cleaned = []
    for d in data_dirs:
        if os.path.exists(d):
            for f in os.listdir(d):
                if f.endswith('.tif') or f.endswith('.png') or f.endswith('.html'):
                    try:
                        os.remove(os.path.join(d, f))
                        cleaned.append(f)
                    except:
                        pass
    
    return {
        "status": "cleaned",
        "jobs_queue": "cleared",
        "results_cache": "cleared",
        "files_removed": len(cleaned)
    }

@app.get("/api/test/minimal")
async def test_minimal():
    """Run a minimal analysis for testing"""
    try:
        test_extent = [36.7, -1.5, 36.9, -1.3]
        test_weights = {"geology": 0.3, "rainfall": 0.3, "slope": 0.2, "landuse": 0.2}
        
        # Run directly (not in background)
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
