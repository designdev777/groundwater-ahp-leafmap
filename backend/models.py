# backend/models.py
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from enum import Enum

class WeightingScheme(str, Enum):
    BALANCED = "balanced"
    HYDROGEOLOGY_FOCUS = "hydrogeology_focus"
    CLIMATE_FOCUS = "climate_focus"
    CUSTOM = "custom"

class Season(str, Enum):
    DRY = "dry"
    WET = "wet"
    TRANSITIONAL = "transitional"

class GroundwaterRequest(BaseModel):
    extent: List[float] = Field(..., description="[minx, miny, maxx, maxy]")
    weighting_scheme: str = "balanced"
    custom_weights: Optional[Dict[str, float]] = None
    season: str = "transitional"
    resolution: int = 100

class GroundwaterResponse(BaseModel):
    job_id: str
    status: str
    result_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    statistics: Optional[Dict] = None
    weights_used: Dict[str, float]

# AHP Weighting Schemes
WEIGHTING_SCHEMES = {
    "balanced": {
        "geology": 0.30,
        "rainfall": 0.30,
        "slope": 0.20,
        "landuse": 0.20
    },
    "hydrogeology_focus": {
        "geology": 0.40,
        "slope": 0.20,
        "rainfall": 0.25,
        "landuse": 0.15
    },
    "climate_focus": {
        "rainfall": 0.40,
        "landuse": 0.25,
        "slope": 0.20,
        "geology": 0.15
    }
}