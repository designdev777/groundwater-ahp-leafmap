"""
Groundwater AHP Processor using leafmap (simplified, no maplibre dependency)
All processing happens locally on the server
"""

import leafmap
import geopandas as gpd
import rasterio
import numpy as np
from rasterio.transform import from_origin
import tempfile
import os
from typing import List, Dict, Any, Tuple
import xarray as xr
import rioxarray
import json
import hashlib
import time
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap


class LeafmapGroundwaterProcessor:
    """
    Groundwater AHP analysis using leafmap
    All processing happens locally on the server
    """
    
    def __init__(self, data_dir: str = None):
        """
        Initialize processor with automatic directory selection
        
        Args:
            data_dir: Optional path to data directory. If None, uses env var or defaults.
        """
        # Priority: 1. Passed argument, 2. Environment variable, 3. Default
        if data_dir is not None:
            self.data_dir = data_dir
        else:
            self.data_dir = os.getenv("DATA_DIR", "/tmp/groundwater-data")
        
        print(f"🔧 Initializing processor...")
        print(f"📁 Requested data directory: {self.data_dir}")
        
        # Try to set up directories
        if not self._setup_directories():
            # If failed, try fallback locations
            self._try_fallback_directories()
    
    def _setup_directories(self) -> bool:
        """Try to create directories in current path, return True if successful"""
        try:
            # Create all required subdirectories
            os.makedirs(f"{self.data_dir}/preprocessed", exist_ok=True)
            os.makedirs(f"{self.data_dir}/cache", exist_ok=True)
            os.makedirs(f"{self.data_dir}/output", exist_ok=True)
            os.makedirs(f"{self.data_dir}/thumbnails", exist_ok=True)
            
            # Test write permission
            test_file = f"{self.data_dir}/test_write.txt"
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            
            print(f"✅ Successfully using: {self.data_dir}")
            return True
            
        except (PermissionError, OSError) as e:
            print(f"⚠️ Cannot use {self.data_dir}: {e}")
            return False
    
    def _try_fallback_directories(self):
        """Try alternative directories if primary fails"""
        fallback_dirs = [
            "/tmp/groundwater-data",
            os.path.join(os.getcwd(), "data"),
            tempfile.mkdtemp(prefix="groundwater-"),
            "./data"
        ]
        
        for fallback in fallback_dirs:
            if fallback == self.data_dir:
                continue  # Skip if same as primary
                
            try:
                os.makedirs(f"{fallback}/preprocessed", exist_ok=True)
                os.makedirs(f"{fallback}/cache", exist_ok=True)
                os.makedirs(f"{fallback}/output", exist_ok=True)
                os.makedirs(f"{fallback}/thumbnails", exist_ok=True)
                
                # Test write
                test_file = f"{fallback}/test.txt"
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                
                self.data_dir = fallback
                print(f"✅ Using fallback directory: {self.data_dir}")
                return
                
            except (PermissionError, OSError) as e:
                print(f"⚠️ Cannot use fallback {fallback}: {e}")
                continue
        
        # If all fallbacks fail, raise error
        raise PermissionError("Cannot find any writable directory for data storage")
    
    def _ensure_data_directories(self):
        """Create necessary data directories"""
        os.makedirs(f"{self.data_dir}/preprocessed", exist_ok=True)
        os.makedirs(f"{self.data_dir}/cache", exist_ok=True)
        os.makedirs(f"{self.data_dir}/output", exist_ok=True)
        os.makedirs(f"{self.data_dir}/thumbnails", exist_ok=True)
    
    def get_srtm_dem(self, extent: List[float], resolution: int = 100) -> str:
        """
        Get SRTM DEM for extent using local files or create synthetic
        Returns path to GeoTIFF
        """
        output_path = f"{self.data_dir}/cache/dem_{'_'.join(map(str, extent))}.tif"
        
        # For production, you'd download actual SRTM data
        # For now, create synthetic DEM for testing
        if not os.path.exists(output_path):
            self._create_synthetic_dem(extent, output_path, resolution)
            
        return output_path
    
    def _create_synthetic_dem(self, extent: List[float], output_path: str, resolution: int):
        """Create synthetic DEM using rasterio only (no osgeo)"""
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
        
        minx, miny, maxx, maxy = extent
        width = height = resolution
        
        # Create synthetic elevation with hills
        x = np.linspace(0, 2*np.pi, width)
        y = np.linspace(0, 2*np.pi, height)
        X, Y = np.meshgrid(x, y)
        elevation = 1000 + 200 * np.sin(X) * np.cos(Y) + 100 * np.sin(2*X)
        
        # Calculate pixel size
        pixel_width = (maxx - minx) / width
        pixel_height = (maxy - miny) / height
        
        # Create transform
        transform = from_origin(minx, maxy, pixel_width, pixel_height)
        
        # Write with rasterio (no osgeo needed)
        with rasterio.open(
            output_path,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=1,
            dtype=elevation.dtype,
            crs='EPSG:4326',
            transform=transform
        ) as dst:
            dst.write(elevation, 1)
        
        print(f"✅ Created synthetic DEM: {output_path}")
    
    def calculate_slope(self, dem_path: str) -> str:
        """
        Calculate slope from DEM using rioxarray
        """
        output_path = dem_path.replace('.tif', '_slope.tif')
        
        # Check if already calculated
        if os.path.exists(output_path):
            return output_path
        
        # Open DEM with rioxarray
        dem = rioxarray.open_rasterio(dem_path)
        
        # Calculate slope using numpy gradient
        # This is a simplified approach - for production use proper terrain algorithms
        data = dem.values[0]
        
        # Get pixel resolution in degrees
        transform = dem.rio.transform()
        res_x = abs(transform[0])
        res_y = abs(transform[4])
        
        # Calculate gradients
        dx = np.gradient(data, res_x, axis=1)
        dy = np.gradient(data, res_y, axis=0)
        
        # Calculate slope in degrees
        slope = np.arctan(np.sqrt(dx**2 + dy**2)) * (180 / np.pi)
        
        # Convert back to xarray
        slope_da = xr.DataArray(
            slope[np.newaxis, :, :],
            dims=dem.dims,
            coords=dem.coords,
            attrs=dem.attrs
        )
        
        # Save to file
        slope_da.rio.to_raster(output_path)
        print(f"✅ Calculated slope: {output_path}")
        
        return output_path
    
    def get_rainfall_data(self, extent: List[float], season: str = 'transitional') -> str:
        """
        Get CHIRPS rainfall data (synthetic for now)
        """
        output_path = f"{self.data_dir}/cache/rainfall_{'_'.join(map(str, extent))}_{season}.tif"
        
        if not os.path.exists(output_path):
            self._create_synthetic_rainfall(extent, output_path, season)
            
        return output_path
    
    def _create_synthetic_rainfall(self, extent: List[float], output_path: str, season: str):
        """Create synthetic rainfall for testing"""
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
        
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
        
        # Calculate pixel size
        pixel_width = (maxx - minx) / width
        pixel_height = (maxy - miny) / height
        
        # Create transform
        transform = from_origin(minx, maxy, pixel_width, pixel_height)
        
        # Write to GeoTIFF
        with rasterio.open(
            output_path,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=1,
            dtype=rainfall.dtype,
            crs='EPSG:4326',
            transform=transform
        ) as dst:
            dst.write(rainfall, 1)
        
        print(f"✅ Created synthetic rainfall: {output_path}")
    
    def _create_synthetic_geology(self, extent: List[float]) -> str:
        """Create synthetic geology layer"""
        output_path = f"{self.data_dir}/cache/geology_{'_'.join(map(str, extent))}.tif"
        
        if not os.path.exists(output_path):
            import numpy as np
            import rasterio
            from rasterio.transform import from_origin
            
            minx, miny, maxx, maxy = extent
            width = height = 100
            
            # Create synthetic geology classes (1-5)
            x = np.linspace(0, 2*np.pi, width)
            y = np.linspace(0, 2*np.pi, height)
            X, Y = np.meshgrid(x, y)
            
            # Random geology patterns
            geology = 3 + 2 * np.sin(X * 3) * np.cos(Y * 3)
            geology = np.clip(geology, 1, 5).astype(np.int16)
            
            # Calculate pixel size
            pixel_width = (maxx - minx) / width
            pixel_height = (maxy - miny) / height
            
            # Create transform
            transform = from_origin(minx, maxy, pixel_width, pixel_height)
            
            # Write to GeoTIFF
            with rasterio.open(
                output_path,
                'w',
                driver='GTiff',
                height=height,
                width=width,
                count=1,
                dtype=geology.dtype,
                crs='EPSG:4326',
                transform=transform
            ) as dst:
                dst.write(geology, 1)
            
            print(f"✅ Created synthetic geology: {output_path}")
        
        return output_path
    
    def _create_synthetic_landuse(self, extent: List[float]) -> str:
        """Create synthetic landuse layer"""
        output_path = f"{self.data_dir}/cache/landuse_{'_'.join(map(str, extent))}.tif"
        
        if not os.path.exists(output_path):
            import numpy as np
            import rasterio
            from rasterio.transform import from_origin
            
            minx, miny, maxx, maxy = extent
            width = height = 100
            
            # Create synthetic landuse classes (1-5)
            x = np.linspace(0, 2*np.pi, width)
            y = np.linspace(0, 2*np.pi, height)
            X, Y = np.meshgrid(x, y)
            
            # Landuse patterns
            landuse = 3 + 2 * np.sin(X * 5) * np.cos(Y * 5)
            landuse = np.clip(landuse, 1, 5).astype(np.int16)
            
            # Calculate pixel size
            pixel_width = (maxx - minx) / width
            pixel_height = (maxy - miny) / height
            
            # Create transform
            transform = from_origin(minx, maxy, pixel_width, pixel_height)
            
            # Write to GeoTIFF
            with rasterio.open(
                output_path,
                'w',
                driver='GTiff',
                height=height,
                width=width,
                count=1,
                dtype=landuse.dtype,
                crs='EPSG:4326',
                transform=transform
            ) as dst:
                dst.write(landuse, 1)
            
            print(f"✅ Created synthetic landuse: {output_path}")
        
        return output_path
    
    def reclassify_raster(self, raster_path: str, thresholds: List[Tuple[float, float, int]]) -> str:
        """
        Reclassify raster based on thresholds
        thresholds: [(min, max, new_value), ...]
        """
        output_path = raster_path.replace('.tif', '_reclass.tif')
        
        if os.path.exists(output_path):
            return output_path
        
        # Read raster
        with rasterio.open(raster_path) as src:
            data = src.read(1)
            profile = src.profile
            
            # Handle nodata
            if src.nodata is not None:
                mask = data == src.nodata
            else:
                mask = np.zeros_like(data, dtype=bool)
            
            # Reclassify
            reclassed = np.zeros_like(data, dtype=np.int16)
            for min_val, max_val, new_val in thresholds:
                value_mask = (data >= min_val) & (data <= max_val)
                reclassed[value_mask] = new_val
            
            # Preserve nodata
            reclassed[mask] = src.nodata if src.nodata is not None else -9999
            
            # Write output
            profile.update(dtype=rasterio.int16)
            with rasterio.open(output_path, 'w', **profile) as dst:
                dst.write(reclassed.astype(np.int16), 1)
        
        print(f"✅ Reclassified raster: {output_path}")
        return output_path
    
    def weighted_overlay(self, raster_paths: List[str], weights: List[float]) -> str:
        """
        Perform weighted overlay of multiple rasters
        """
        # Create unique hash for this combination
        import hashlib
        combo = "".join([f"{p}{w}" for p, w in zip(raster_paths, weights)])
        hash_id = hashlib.md5(combo.encode()).hexdigest()
        
        output_path = f"{self.data_dir}/output/gwpz_{hash_id}.tif"
        
        if os.path.exists(output_path):
            return output_path
        
        # Read first raster to get profile and shape
        with rasterio.open(raster_paths[0]) as src:
            profile = src.profile
            shape = src.shape
            nodata = src.nodata
        
        # Initialize weighted sum
        weighted_sum = np.zeros(shape, dtype=np.float32)
        weight_sum = 0
        
        # Add each weighted raster
        for path, weight in zip(raster_paths, weights):
            with rasterio.open(path) as src:
                data = src.read(1)
                
                # Handle nodata
                if src.nodata is not None:
                    data = np.where(data == src.nodata, 0, data)
                
                weighted_sum += data * weight
                weight_sum += weight
        
        # Normalize by total weight
        if weight_sum > 0:
            weighted_sum = weighted_sum / weight_sum
        
        # Write result
        profile.update(dtype=rasterio.float32, nodata=-9999)
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(weighted_sum, 1)
        
        print(f"✅ Created weighted overlay: {output_path}")
        return output_path
    
    def calculate_statistics(self, raster_path: str) -> Dict[str, float]:
        """
        Calculate statistics for the result raster
        """
        with rasterio.open(raster_path) as src:
            data = src.read(1)
            
            # Handle nodata
            if src.nodata is not None:
                data = data[data != src.nodata]
            else:
                data = data.flatten()
            
            if len(data) == 0:
                return {
                    'mean': 0,
                    'std': 0,
                    'min': 0,
                    'max': 0,
                    'zone_areas': {
                        'very_low': 0,
                        'low': 0,
                        'moderate': 0,
                        'high': 0,
                        'very_high': 0
                    }
                }
            
            stats = {
                'mean': float(np.mean(data)),
                'std': float(np.std(data)),
                'min': float(np.min(data)),
                'max': float(np.max(data))
            }
            
            # Calculate zone areas (approximate)
            with rasterio.open(raster_path) as src_count:
                full_data = src_count.read(1)
                
                # Zone classification based on value ranges
                # Define zone thresholds as a dictionary
                zone_thresholds = {
                    'very_low': (full_data >= 1) & (full_data < 2),
                    'low': (full_data >= 2) & (full_data < 3),
                    'moderate': (full_data >= 3) & (full_data < 4),
                    'high': (full_data >= 4) & (full_data < 5),
                    'very_high': full_data >= 5
                }
                
                # Create nodata mask if needed
                if src_count.nodata is not None:
                    nodata_mask = full_data == src_count.nodata
                    # Apply nodata mask to all zone calculations
                    for zone_name in zone_thresholds:
                        zone_thresholds[zone_name] = zone_thresholds[zone_name] & ~nodata_mask
                
                # Calculate pixel counts for each zone
                zones = {}
                for zone_name, zone_mask in zone_thresholds.items():
                    zones[zone_name] = np.sum(zone_mask)
                
                # Calculate pixel area in square kilometers
                # This is approximate for EPSG:4326
                transform = src_count.transform
                pixel_width_deg = abs(transform[0])
                pixel_height_deg = abs(transform[4])
                
                # Convert degrees to km (111km per degree at equator)
                pixel_area_km2 = (pixel_width_deg * 111) * (pixel_height_deg * 111)
                
                zone_areas = {k: float(v * pixel_area_km2) for k, v in zones.items()}
                stats['zone_areas'] = zone_areas
        
        return stats
    
def generate_thumbnail(self, raster_path: str) -> str:
    """
    Generate PNG thumbnail for web display
    """
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    
    # Create output path
    base_name = os.path.basename(raster_path).replace('.tif', '.png')
    output_path = f"{self.data_dir}/thumbnails/{base_name}"
    
    if os.path.exists(output_path):
        return output_path
    
    # Read raster
    with rasterio.open(raster_path) as src:
        data = src.read(1)
        
        # Handle nodata
        if src.nodata is not None:
            data = np.ma.masked_where(data == src.nodata, data)
    
    # Create custom colormap (red to green)
    colors = ['#ff0000', '#ff9900', '#ffff00', '#99ff00', '#00aa00']
    cmap = LinearSegmentedColormap.from_list('gwpz', colors, N=5)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(data, cmap=cmap, vmin=1, vmax=5)
    ax.set_title('Groundwater Potential Zones')
    ax.axis('off')
    
    # Add colorbar with correct number of ticks and labels
    cbar = plt.colorbar(im, ax=ax, ticks=[1.4, 2.2, 3.0, 3.8, 4.6])
    cbar.ax.set_yticklabels(['Very Low', 'Low', 'Moderate', 'High', 'Very High'])
    
    # Save
    plt.savefig(output_path, bbox_inches='tight', dpi=100)
    plt.close()
    
    print(f"✅ Generated thumbnail: {output_path}")
    return output_path
    
    def create_interactive_map(self, result_path: str, html_path: str = None) -> str:
        """
        Create interactive HTML map using regular leafmap (no maplibre)
        """
        if html_path is None:
            # Generate a unique filename
            unique_id = hashlib.md5(f"{result_path}{time.time()}".encode()).hexdigest()[:8]
            html_path = f"{self.data_dir}/output/gwpz_{unique_id}.html"
        
        # Create map centered on Kenya
        m = leafmap.Map(center=[-1.4, 36.8], zoom=9)
        m.add_basemap("OpenStreetMap")
        
        # Add result raster
        m.add_raster(
            result_path,
            palette=['red', 'orange', 'yellow', 'lightgreen', 'darkgreen'],
            layer_name='Groundwater Potential',
            opacity=0.7
        )
        
        # Add legend as HTML
        legend_html = """
        <div style="
            position: absolute; 
            bottom: 20px; 
            right: 20px; 
            background: white; 
            padding: 10px; 
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
            z-index: 1000;
        ">
            <h4 style="margin: 0 0 10px 0;">Groundwater Potential</h4>
            <div><span style="background: #ff0000; width: 20px; height: 20px; display: inline-block; margin-right: 5px;"></span> Very Low (1)</div>
            <div><span style="background: #ff9900; width: 20px; height: 20px; display: inline-block; margin-right: 5px;"></span> Low (2)</div>
            <div><span style="background: #ffff00; width: 20px; height: 20px; display: inline-block; margin-right: 5px;"></span> Moderate (3)</div>
            <div><span style="background: #99ff00; width: 20px; height: 20px; display: inline-block; margin-right: 5px;"></span> High (4)</div>
            <div><span style="background: #00aa00; width: 20px; height: 20px; display: inline-block; margin-right: 5px;"></span> Very High (5)</div>
        </div>
        """
        
        # Convert to HTML and add legend
        html = m.to_html()
        html = html.replace('</body>', f'{legend_html}</body>')
        
        # Save to file
        with open(html_path, 'w') as f:
            f.write(html)
        
        print(f"✅ Created interactive map: {html_path}")
        return html_path
    
    def _save_as_png(self, raster_path: str, png_path: str):
        """Save raster as PNG for web display"""
        with rasterio.open(raster_path) as src:
            data = src.read(1)
        
        # Create custom colormap
        colors = ['#ff0000', '#ff9900', '#ffff00', '#99ff00', '#00aa00']
        cmap = LinearSegmentedColormap.from_list('gwpz', colors, N=5)
        
        plt.figure(figsize=(10, 8))
        plt.imshow(data, cmap=cmap, vmin=1, vmax=5)
        plt.axis('off')
        plt.savefig(png_path, bbox_inches='tight', dpi=100, transparent=True)
        plt.close()
    
    def full_ahp_analysis(self, extent, weights, season='transitional'):
        """
        Run complete AHP groundwater analysis
        """
        print(f"🚀 Starting AHP analysis for extent: {extent}")
        print(f"📊 Weights: {weights}")
        print(f"🌦️ Season: {season}")
        
        # 1. Get DEM and calculate slope
        print("📡 Getting DEM data...")
        dem_path = self.get_srtm_dem(extent)
        print("⛰️ Calculating slope...")
        slope_path = self.calculate_slope(dem_path)
        
        # 2. Get rainfall data
        print("🌧️ Getting rainfall data...")
        rainfall_path = self.get_rainfall_data(extent, season)
        
        # 3. Create synthetic geology and landuse
        print("🗺️ Creating geology layer...")
        geology_path = self._create_synthetic_geology(extent)
        print("🌲 Creating landuse layer...")
        landuse_path = self._create_synthetic_landuse(extent)
        
        # 4. Reclassify each factor to 1-5 scale
        print("📐 Reclassifying slope...")
        slope_reclass = self.reclassify_raster(
            slope_path,
            [(0, 5, 5), (5, 15, 4), (15, 25, 3), (25, 35, 2), (35, 90, 1)]
        )
        
        print("💧 Reclassifying rainfall...")
        rainfall_reclass = self.reclassify_raster(
            rainfall_path,
            [(0, 50, 1), (50, 100, 2), (100, 150, 3), (150, 200, 4), (200, 1000, 5)]
        )
        
        # Geology and landuse are already in 1-5 scale (synthetic)
        geology_reclass = geology_path
        landuse_reclass = landuse_path
        
        # 5. Weighted overlay
        print("⚖️ Performing weighted overlay...")
        result_path = self.weighted_overlay(
            [slope_reclass, rainfall_reclass, geology_reclass, landuse_reclass],
            [weights['slope'], weights['rainfall'], weights['geology'], weights['landuse']]
        )
        
        # 6. Calculate statistics
        print("📊 Calculating statistics...")
        stats = self.calculate_statistics(result_path)
        
        # Generate a unique filename
        unique_id = hashlib.md5(f"{extent}{weights}{season}{time.time()}".encode()).hexdigest()[:8]
        
        # 7. Generate thumbnail and interactive map
        print("🖼️ Generating thumbnail...")
        thumb_path = self.generate_thumbnail(result_path)
        
        # Save result as PNG for easy viewing
        png_path = f"{self.data_dir}/output/gwpz_{unique_id}.png"
        self._save_as_png(result_path, png_path)
        
        # Also create interactive HTML
        print("🗺️ Creating interactive map...")
        html_path = f"{self.data_dir}/output/gwpz_{unique_id}.html"
        self.create_interactive_map(result_path, html_path)
        
        print("✅ Analysis complete!")
        
        return {
            'result_path': result_path,
            'thumbnail_path': thumb_path,
            'result_url': f"/results/gwpz_{unique_id}.png",  # Public URL
            'interactive_url': f"/results/gwpz_{unique_id}.html",  # Public URL
            'statistics': stats,
            'weights_used': weights,
            'season': season
        }
