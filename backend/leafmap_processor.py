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

class LeafmapGroundwaterProcessor:
    """
    Groundwater AHP analysis using leafmap
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
        """Create synthetic DEM for testing"""
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
        from osgeo import gdal
        
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
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(output_path, width, height, 1, gdal.GDT_Float32)
        ds.SetGeoTransform([minx, (maxx-minx)/width, 0, maxy, 0, -(maxy-miny)/height])
        ds.SetProjection('EPSG:4326')
        ds.GetRasterBand(1).WriteArray(rainfall)
        ds.FlushCache()
        print(f"✅ Created synthetic rainfall: {output_path}")
    
    def _create_synthetic_geology(self, extent: List[float]) -> str:
        """Create synthetic geology layer"""
        output_path = f"{self.data_dir}/cache/geology_{'_'.join(map(str, extent))}.tif"
        
        if not os.path.exists(output_path):
            from osgeo import gdal
            
            minx, miny, maxx, maxy = extent
            width = height = 100
            
            # Create synthetic geology classes (1-5)
            x = np.linspace(0, 2*np.pi, width)
            y = np.linspace(0, 2*np.pi, height)
            X, Y = np.meshgrid(x, y)
            
            # Random geology patterns
            geology = 3 + 2 * np.sin(X * 3) * np.cos(Y * 3)
            geology = np.clip(geology, 1, 5).astype(np.int16)
            
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(output_path, width, height, 1, gdal.GDT_Int16)
            ds.SetGeoTransform([minx, (maxx-minx)/width, 0, maxy, 0, -(maxy-miny)/height])
            ds.SetProjection('EPSG:4326')
            ds.GetRasterBand(1).WriteArray(geology)
            ds.FlushCache()
            print(f"✅ Created synthetic geology: {output_path}")
        
        return output_path
    
    def _create_synthetic_landuse(self, extent: List[float]) -> str:
        """Create synthetic landuse layer"""
        output_path = f"{self.data_dir}/cache/landuse_{'_'.join(map(str, extent))}.tif"
        
        if not os.path.exists(output_path):
            from osgeo import gdal
            
            minx, miny, maxx, maxy = extent
            width = height = 100
            
            # Create synthetic landuse classes (1-5)
            x = np.linspace(0, 2*np.pi, width)
            y = np.linspace(0, 2*np.pi, height)
            X, Y = np.meshgrid(x, y)
            
            # Landuse patterns
            landuse = 3 + 2 * np.sin(X * 5) * np.cos(Y * 5)
            landuse = np.clip(landuse, 1, 5).astype(np.int16)
            
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(output_path, width, height, 1, gdal.GDT_Int16)
            ds.SetGeoTransform([minx, (maxx-minx)/width, 0, maxy, 0, -(maxy-miny)/height])
            ds.SetProjection('EPSG:4326')
            ds.GetRasterBand(1).WriteArray(landuse)
            ds.FlushCache()
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
                zones = {
                    'very_low': np.sum((full_data >= 1) & (full_data < 2)),
                    'low': np.sum((full_data >= 2) & (full_data < 3)),
                    'moderate': np.sum((full_data >= 3) & (full_data < 4)),
                    'high': np.sum((full_data >= 4) & (full_data < 5)),
                    'very_high': np.sum(full_data >= 5)
                }
                
                # Remove nodata from counts
                if src_count.nodata is not None:
                    nodata_mask = full_data == src_count.nodata
                    for zone in zones:
                        zones[zone] = np.sum((full_data >= eval(zone)) & ~nodata_mask)
                
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
        
        # Add colorbar
        cbar = plt.colorbar(im, ax=ax, ticks=[1.5, 2.5, 3.5, 4.5])
        cbar.ax.set_yticklabels(['Very Low', 'Low', 'Moderate', 'High', 'Very High'])
        
        # Save
        plt.savefig(output_path, bbox_inches='tight', dpi=100)
        plt.close()
        
        print(f"✅ Generated thumbnail: {output_path}")
        return output_path
    
    def create_interactive_map(self, result_path: str) -> str:
        """
        Create interactive HTML map using regular leafmap (no maplibre)
        """
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
        
        return html
    
    def full_ahp_analysis(self, 
                          extent: List[float],
                          weights: Dict[str, float],
                          season: str = 'transitional') -> Dict[str, Any]:
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
        
        # 7. Generate thumbnail and interactive map
        print("🖼️ Generating thumbnail...")
        thumb_path = self.generate_thumbnail(result_path)
        print("🗺️ Creating interactive map...")
        interactive_html = self.create_interactive_map(result_path)
        
        print("✅ Analysis complete!")
        
        return {
            'result_path': result_path,
            'thumbnail_path': thumb_path,
            'interactive_html': interactive_html,
            'statistics': stats,
            'weights_used': weights,
            'season': season
        }
