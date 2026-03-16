"""
Groundwater AHP API - Main application
"""
import sys
import os
from pathlib import Path

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

@app.get("/")
async def root():
    """Serve the main HTML interface with fallback"""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    else:
        # Serve a simple built-in HTML page
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Groundwater AHP Platform</title>
            <style>
                body { font-family: Arial; margin: 40px; }
                .error { color: red; }
            </style>
        </head>
        <body>
            <h1>🌊 Groundwater AHP Platform</h1>
            <p>API is running but frontend files are missing.</p>
            <p class="error">Frontend directory not found at: {}</p>
            <h2>Available API Endpoints:</h2>
            <ul>
                <li><a href="/docs">/docs</a> - API Documentation</li>
                <li><a href="/api/health">/api/health</a> - Health Check</li>
                <li><a href="/api/study-areas">/api/study-areas</a> - Study Areas</li>
                <li><a href="/api/weighting-schemes">/api/weighting-schemes</a> - Weighting Schemes</li>
            </ul>
        </body>
        </html>
        """.format(FRONTEND_DIR)
        return HTMLResponse(content=html_content)

# ... rest of your endpoints

"""
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize processor
processor = LeafmapGroundwaterProcessor(data_dir="/app/data")

# Job tracking
jobs = {}
results_cache = {}

# Serve frontend
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

@app.get("/")
async def root():
    return FileResponse("../frontend/index.html")
"""
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
    job_id = str(uuid.uuid4())
    
    # Get weights
    if request.weighting_scheme == "custom" and request.custom_weights:
        weights = request.custom_weights
    else:
        weights = WEIGHTING_SCHEMES.get(request.weighting_scheme, WEIGHTING_SCHEMES["balanced"])
    
    # Check cache
    cache_key = hashlib.md5(
        json.dumps({
            "extent": request.extent,
            "weights": weights,
            "season": request.season
        }).encode()
    ).hexdigest()
    
    if cache_key in results_cache:
        return GroundwaterResponse(
            job_id=job_id,
            status="completed",
            result_url=f"/results/{cache_key}.html",
            thumbnail_url=f"/thumbnails/{cache_key}.png",
            statistics=results_cache[cache_key]["statistics"],
            weights_used=weights
        )
    
    # Queue for processing
    jobs[job_id] = {"status": "processing"}
    
    # Process in background
    background_tasks.add_task(
        process_groundwater_job,
        job_id, request.extent, weights, request.season, cache_key
    )
    
    return GroundwaterResponse(
        job_id=job_id,
        status="processing",
        weights_used=weights
    )

async def process_groundwater_job(job_id, extent, weights, season, cache_key):
    try:
        # Run leafmap analysis
        result = processor.full_ahp_analysis(extent, weights, season)
        
        # Store in cache
        results_cache[cache_key] = result
        
        # Update job status
        jobs[job_id] = {"status": "completed", "result": result}
        
    except Exception as e:
        jobs[job_id] = {"status": "failed", "error": str(e)}

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
