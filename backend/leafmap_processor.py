"""
Groundwater AHP Processor using leafmap (simplified)
"""

import os
import tempfile
import numpy as np
import rasterio
from rasterio.transform import from_origin
import hashlib
import time
from typing import List, Dict, Any, Tuple
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import leafmap


class LeafmapGroundwaterProcessor:
    """
    Groundwater AHP analysis using leafmap
    """
    
    def __init__(self, data_dir: str = None):
        """Initialize processor"""
        if data_dir is not None:
            self.data_dir = data_dir
        else:
            self.data_dir = os.getenv("DATA_DIR", "/tmp/groundwater-data")
        
        print(f"Initializing processor with data_dir: {self.data_dir}")
        self._setup_directories()
    
    def _setup_directories(self):
        """Create necessary directories"""
        os.makedirs(f"{self.data_dir}/cache", exist_ok=True)
        os.makedirs(f"{self.data_dir}/output", exist_ok=True)
        os.makedirs(f"{self.data_dir}/thumbnails", exist_ok=True)
        print(f"Directories created in {self.data_dir}")
    
    def full_ahp_analysis(self, extent, weights, season='transitional'):
        """
        Run complete AHP groundwater analysis
        This is a simplified version that returns mock data
        """
        print(f"Starting AHP analysis for extent: {extent}")
        print(f"Weights: {weights}")
        print(f"Season: {season}")
        
        # Generate a unique ID
        unique_id = hashlib.md5(f"{extent}{weights}{season}{time.time()}".encode()).hexdigest()[:8]
        
        # Create a simple synthetic result
        result_path = f"{self.data_dir}/output/gwpz_{unique_id}.tif"
        self._create_synthetic_result(extent, result_path)
        
        # Create thumbnail
        thumb_path = f"{self.data_dir}/thumbnails/gwpz_{unique_id}.png"
        self._create_synthetic_thumbnail(result_path, thumb_path)
        
        # Create interactive map
        html_path = f"{self.data_dir}/output/gwpz_{unique_id}.html"
        self._create_synthetic_map(result_path, html_path)
        
        # Create PNG for web display
        png_path = f"{self.data_dir}/output/gwpz_{unique_id}.png"
        self._save_as_png(result_path, png_path)
        
        # Mock statistics
        stats = {
            'mean': 3.2,
            'std': 1.1,
            'min': 1.0,
            'max': 5.0,
            'zone_areas': {
                'very_low': 150.5,
                'low': 275.3,
                'moderate': 420.8,
                'high': 310.2,
                'very_high': 180.6
            }
        }
        
        print("Analysis complete!")
        
        return {
            'result_path': result_path,
            'thumbnail_path': thumb_path,
            'result_url': f"/results/gwpz_{unique_id}.png",
            'interactive_url': f"/results/gwpz_{unique_id}.html",
            'statistics': stats,
            'weights_used': weights,
            'season': season
        }
    
    def _create_synthetic_result(self, extent, output_path):
        """Create a synthetic result raster"""
        minx, miny, maxx, maxy = extent
        width = height = 100
        
        # Create synthetic data (values 1-5)
        x = np.linspace(0, 4*np.pi, width)
        y = np.linspace(0, 4*np.pi, height)
        X, Y = np.meshgrid(x, y)
        
        # Create pattern with values from 1 to 5
        data = 3 + 2 * np.sin(X) * np.cos(Y)
        data = np.clip(data, 1, 5)
        
        pixel_width = (maxx - minx) / width
        pixel_height = (maxy - miny) / height
        transform = from_origin(minx, maxy, pixel_width, pixel_height)
        
        with rasterio.open(
            output_path, 'w',
            driver='GTiff',
            height=height,
            width=width,
            count=1,
            dtype=data.dtype,
            crs='EPSG:4326',
            transform=transform
        ) as dst:
            dst.write(data, 1)
        
        print(f"Created synthetic result: {output_path}")
    
    def _create_synthetic_thumbnail(self, raster_path, output_path):
        """Create a thumbnail image"""
        # Read the raster
        with rasterio.open(raster_path) as src:
            data = src.read(1)
        
        # Create colormap
        colors = ['#ff0000', '#ff9900', '#ffff00', '#99ff00', '#00aa00']
        cmap = LinearSegmentedColormap.from_list('gwpz', colors, N=5)
        
        plt.figure(figsize=(10, 8))
        plt.imshow(data, cmap=cmap, vmin=1, vmax=5)
        plt.axis('off')
        plt.savefig(output_path, bbox_inches='tight', dpi=100)
        plt.close()
        
        print(f"Created thumbnail: {output_path}")
    
    def _create_synthetic_map(self, raster_path, output_path):
        """Create an interactive map"""
        m = leafmap.Map(center=[-1.4, 36.8], zoom=6)
        m.add_basemap("OpenStreetMap")
        
        html = m.to_html()
        
        # Add legend
        legend = """
        <div style="position: absolute; bottom: 20px; right: 20px; background: white; padding: 10px; border-radius: 5px; z-index: 1000;">
            <h4>Groundwater Potential</h4>
            <div><span style="background: #ff0000; width: 20px; height: 20px; display: inline-block;"></span> Very Low</div>
            <div><span style="background: #ff9900; width: 20px; height: 20px; display: inline-block;"></span> Low</div>
            <div><span style="background: #ffff00; width: 20px; height: 20px; display: inline-block;"></span> Moderate</div>
            <div><span style="background: #99ff00; width: 20px; height: 20px; display: inline-block;"></span> High</div>
            <div><span style="background: #00aa00; width: 20px; height: 20px; display: inline-block;"></span> Very High</div>
        </div>
        """
        
        html = html.replace('</body>', f'{legend}</body>')
        
        with open(output_path, 'w') as f:
            f.write(html)
        
        print(f"Created interactive map: {output_path}")
    
    def _save_as_png(self, raster_path, png_path):
        """Save raster as PNG"""
        with rasterio.open(raster_path) as src:
            data = src.read(1)
        
        colors = ['#ff0000', '#ff9900', '#ffff00', '#99ff00', '#00aa00']
        cmap = LinearSegmentedColormap.from_list('gwpz', colors, N=5)
        
        plt.figure(figsize=(10, 8))
        plt.imshow(data, cmap=cmap, vmin=1, vmax=5)
        plt.axis('off')
        plt.savefig(png_path, bbox_inches='tight', dpi=100, transparent=True)
        plt.close()
        
        print(f"Created PNG: {png_path}")