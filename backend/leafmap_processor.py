import leafmap
import leafmap.maplibregl as leafmap_gl
import geopandas as gpd
import rasterio
import numpy as np
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling, calculate_default_transform
import tempfile
import os
from typing import List, Dict, Any, Tuple
import xarray as xr
import rioxarray

class LeafmapGroundwaterProcessor:
    """
    Groundwater AHP analysis using leafmap instead of Google Earth Engine
    All processing happens locally on the server
    """
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = data_dir
        self._ensure_data_directories()
        
    def _ensure_data_directories(self):
        """Create necessary data directories"""
        os.makedirs(f"{self.data_dir}/preprocessed", exist_ok=True)
        os.makedirs(f"{self.data_dir}/cache", exist_ok=True)
        os.makedirs(f"{self.data_dir}/output", exist_ok=True)
    
    def get_srtm_dem(self, extent: List[float], resolution: int = 100) -> str:
        """
        Get SRTM DEM for extent using OpenTopography or local files
        Returns path to GeoTIFF
        """
        # Option 1: Download from OpenTopography (if internet available)
        # Option 2: Use pre-downloaded SRTM tiles
        # Option 3: Use local COG (Cloud Optimized GeoTIFF)
        
        output_path = f"{self.data_dir}/cache/dem_{'_'.join(map(str, extent))}.tif"
        
        # For this example, we'll use a sample DEM or create synthetic one
        # In production, you'd download actual SRTM data
        if not os.path.exists(output_path):
            self._create_synthetic_dem(extent, output_path, resolution)
            
        return output_path
    
    def _create_synthetic_dem(self, extent: List[float], output_path: str, resolution: int):
        """Create synthetic DEM for testing (replace with real data in production)"""
        import numpy as np
        from osgeo import gdal
        
        minx, miny, maxx, maxy = extent
        width = height = resolution
        
        # Create synthetic elevation with hills
        x = np.linspace(0, 2*np.pi, width)
        y = np.linspace(0, 2*np.pi, height)
        X, Y = np.meshgrid(x, y)
        elevation = 1000 + 200 * np.sin(X) * np.cos(Y) + 100 * np.sin(2*X)
        
        # Write to GeoTIFF
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(output_path, width, height, 1, gdal.GDT_Float32)
        ds.SetGeoTransform([minx, (maxx-minx)/width, 0, maxy, 0, -(maxy-miny)/height])
        ds.SetProjection('EPSG:4326')
        ds.GetRasterBand(1).WriteArray(elevation)
        ds.FlushCache()
    
    def calculate_slope(self, dem_path: str) -> str:
        """
        Calculate slope from DEM using leafmap/rioxarray
        """
        output_path = dem_path.replace('.tif', '_slope.tif')
        
        # Open DEM with rioxarray
        dem = rioxarray.open_rasterio(dem_path)
        
        # Calculate slope using xarray operations
        # This is simplified - in production use proper terrain algorithms
        dx = dem.differentiate('x')
        dy = dem.differentiate('y')
        slope = np.arctan(np.sqrt(dx**2 + dy**2)) * (180 / np.pi)
        
        # Save to file
        slope.rio.to_raster(output_path)
        
        return output_path
    
    def get_rainfall_data(self, extent: List[float], season: str = 'transitional') -> str:
        """
        Get CHIRPS rainfall data
        In production: download from CHIRPS FTP or use pre-processed monthly files
        """
        output_path = f"{self.data_dir}/cache/rainfall_{'_'.join(map(str, extent))}_{season}.tif"
        
        if not os.path.exists(output_path):
            self._create_synthetic_rainfall(extent, output_path, season)
            
        return output_path
    
    def _create_synthetic_rainfall(self, extent: List[float], output_path: str, season: str):
        """Create synthetic rainfall for testing"""
        minx, miny, maxx, maxy = extent
        
        # Seasonal adjustments
        season_mult = {
            'dry': 0.6,
            'wet': 1.4,
            'transitional': 1.0
        }.get(season, 1.0)
        
        # Create synthetic rainfall pattern
        width = height = 100
        x = np.linspace(0, 2*np.pi, width)
        y = np.linspace(0, 2*np.pi, height)
        X, Y = np.meshgrid(x, y)
        
        # Rainfall gradient (more rain in higher elevations/specific patterns)
        base_rainfall = 100 + 50 * np.sin(X) * np.cos(Y)
        rainfall = base_rainfall * season_mult
        
        # Write to GeoTIFF
        from osgeo import gdal
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(output_path, width, height, 1, gdal.GDT_Float32)
        ds.SetGeoTransform([minx, (maxx-minx)/width, 0, maxy, 0, -(maxy-miny)/height])
        ds.SetProjection('EPSG:4326')
        ds.GetRasterBand(1).WriteArray(rainfall)
        ds.FlushCache()
    
    def reclassify_raster(self, raster_path: str, thresholds: List[Tuple[float, float, int]]) -> str:
        """
        Reclassify raster based on thresholds
        thresholds: [(min, max, new_value), ...]
        """
        output_path = raster_path.replace('.tif', '_reclass.tif')
        
        # Read raster
        with rasterio.open(raster_path) as src:
            data = src.read(1)
            profile = src.profile
            
            # Reclassify
            reclassed = np.zeros_like(data)
            for min_val, max_val, new_val in thresholds:
                mask = (data >= min_val) & (data <= max_val)
                reclassed[mask] = new_val
            
            # Write output
            profile.update(dtype=rasterio.int16)
            with rasterio.open(output_path, 'w', **profile) as dst:
                dst.write(reclassed.astype(np.int16), 1)
        
        return output_path
    
    def weighted_overlay(self, raster_paths: List[str], weights: List[float]) -> str:
        """
        Perform weighted overlay of multiple rasters
        """
        output_path = f"{self.data_dir}/output/gwpz_{hash(str(raster_paths))}.tif"
        
        # Read first raster to get profile
        with rasterio.open(raster_paths[0]) as src:
            profile = src.profile
            shape = src.shape
        
        # Initialize weighted sum
        weighted_sum = np.zeros(shape, dtype=np.float32)
        
        # Add each weighted raster
        for path, weight in zip(raster_paths, weights):
            with rasterio.open(path) as src:
                data = src.read(1)
                weighted_sum += data * weight
        
        # Write result
        profile.update(dtype=rasterio.float32)
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(weighted_sum, 1)
        
        return output_path
    
    def calculate_statistics(self, raster_path: str) -> Dict[str, float]:
        """
        Calculate statistics for the result raster
        """
        with rasterio.open(raster_path) as src:
            data = src.read(1)
            data = data[data != src.nodata] if src.nodata else data
            
            stats = {
                'mean': float(np.mean(data)),
                'std': float(np.std(data)),
                'min': float(np.min(data)),
                'max': float(np.max(data))
            }
            
            # Calculate zone areas
            zones = {
                'very_low': np.sum((data >= 1) & (data < 2)),
                'low': np.sum((data >= 2) & (data < 3)),
                'moderate': np.sum((data >= 3) & (data < 4)),
                'high': np.sum((data >= 4) & (data < 5)),
                'very_high': np.sum(data >= 5)
            }
            
            # Convert pixel counts to area (approximate)
            pixel_area = abs(src.transform[0] * src.transform[4]) * 111000 * 111000  # km² approx
            zone_areas = {k: v * pixel_area / 1e6 for k, v in zones.items()}  # Convert to km²
            
            stats['zone_areas'] = zone_areas
        
        return stats
    
    def generate_thumbnail(self, raster_path: str, output_dir: str = None) -> str:
        """
        Generate PNG thumbnail for web display using leafmap
        """
        if output_dir is None:
            output_dir = f"{self.data_dir}/output"
        
        output_path = f"{output_dir}/thumb_{os.path.basename(raster_path).replace('.tif', '.png')}"
        
        # Use leafmap's built-in visualization
        m = leafmap.Map()
        m.add_raster(raster_path, palette=['red', 'yellow', 'green'], layer_name='GWPZ')
        
        # Save as PNG
        m.save_as_png(output_path)
        
        return output_path
    
    def create_interactive_map(self, result_path: str) -> str:
        """
        Create interactive HTML map using leafmap.maplibregl
        Returns HTML string that can be embedded
        """
        import leafmap.maplibregl as leafmap_gl
        
        # Create interactive map
        m = leafmap_gl.Map(center=[36.8, -1.4], zoom=9)
        m.add_basemap("OpenStreetMap")
        
        # Add result layer
        m.add_raster(
            result_path,
            colormap='RdYlGn',
            opacity=0.7,
            layer_name='Groundwater Potential'
        )
        
        # Add legend
        legend_html = """
        <div style="background: white; padding: 10px; border-radius: 5px;">
            <h4>Groundwater Potential</h4>
            <div><span style="background: #ff0000; width: 20px; height: 20px; display: inline-block;"></span> Very Low (1)</div>
            <div><span style="background: #ff9900; width: 20px; height: 20px; display: inline-block;"></span> Low (2)</div>
            <div><span style="background: #ffff00; width: 20px; height: 20px; display: inline-block;"></span> Moderate (3)</div>
            <div><span style="background: #99ff00; width: 20px; height: 20px; display: inline-block;"></span> High (4)</div>
            <div><span style="background: #00aa00; width: 20px; height: 20px; display: inline-block;"></span> Very High (5)</div>
        </div>
        """
        m.add_html(legend_html, position='bottom-right')
        
        return m.to_html()
    
    def full_ahp_analysis(self, 
                          extent: List[float],
                          weights: Dict[str, float],
                          season: str = 'transitional') -> Dict[str, Any]:
        """
        Run complete AHP groundwater analysis
        """
        # 1. Get DEM and calculate slope
        dem_path = self.get_srtm_dem(extent)
        slope_path = self.calculate_slope(dem_path)
        
        # 2. Get rainfall data
        rainfall_path = self.get_rainfall_data(extent, season)
        
        # 3. In production, you'd add geology and landuse here
        # For now, create synthetic geology and landuse
        geology_path = self._create_synthetic_geology(extent)
        landuse_path = self._create_synthetic_landuse(extent)
        
        # 4. Reclassify each factor to 1-5 scale
        slope_reclass = self.reclassify_raster(
            slope_path,
            [(0, 5, 5), (5, 15, 4), (15, 25, 3), (25, 35, 2), (35, 90, 1)]
        )
        
        rainfall_reclass = self.reclassify_raster(
            rainfall_path,
            [(0, 50, 1), (50, 100, 2), (100, 150, 3), (150, 200, 4), (200, 1000, 5)]
        )
        
        # Simplified reclass for geology and landuse
        geology_reclass = geology_path  # Assume already reclassed
        landuse_reclass = landuse_path  # Assume already reclassed
        
        # 5. Weighted overlay
        result_path = self.weighted_overlay(
            [slope_reclass, rainfall_reclass, geology_reclass, landuse_reclass],
            [weights['slope'], weights['rainfall'], weights['geology'], weights['landuse']]
        )
        
        # 6. Calculate statistics
        stats = self.calculate_statistics(result_path)
        
        # 7. Generate thumbnail and interactive map
        thumb_path = self.generate_thumbnail(result_path)
        interactive_html = self.create_interactive_map(result_path)
        
        return {
            'result_path': result_path,
            'thumbnail_path': thumb_path,
            'interactive_html': interactive_html,
            'statistics': stats,
            'weights_used': weights,
            'season': season
        }