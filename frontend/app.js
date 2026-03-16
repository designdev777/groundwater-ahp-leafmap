// Initialize map
let map;
let studyAreas = {};

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    loadStudyAreas();
});

function initMap() {
    map = L.map('map').setView([-1.4, 36.8], 8);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);
}

async function loadStudyAreas() {
    try {
        const response = await fetch('/api/study-areas');
        const data = await response.json();
        studyAreas = data.study_areas;
        console.log('Study areas loaded:', studyAreas);
    } catch (error) {
        console.error('Failed to load study areas:', error);
    }
}

async function runAnalysis() {
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    
    loading.style.display = 'block';
    results.innerHTML = '<p>Processing on server...</p>';
    
    const request = {
        extent: [36.7, -1.5, 36.9, -1.3],  // Default Kenya extent
        weighting_scheme: document.getElementById('weightingScheme').value,
        season: document.getElementById('season').value,
        resolution: 100
    };
    
    try {
        const response = await fetch('/api/groundwater/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(request)
        });
        
        const data = await response.json();
        
        if (data.status === 'processing') {
            results.innerHTML = `<p>Job submitted: ${data.job_id}</p>`;
            pollJobStatus(data.job_id);
        } else {
            displayResults(data);
        }
    } catch (error) {
        loading.style.display = 'none';
        results.innerHTML = `<p class="error">Error: ${error.message}</p>`;
    }
}

async function pollJobStatus(jobId) {
    const results = document.getElementById('results');
    const loading = document.getElementById('loading');
    
    let attempts = 0;
    const maxAttempts = 30;
    
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`/api/groundwater/status/${jobId}`);
            const data = await response.json();
            
            if (data.status === 'completed') {
                clearInterval(interval);
                loading.style.display = 'none';
                displayResults(data);
            } else if (data.status === 'failed') {
                clearInterval(interval);
                loading.style.display = 'none';
                results.innerHTML = `<p class="error">Processing failed</p>`;
            }
            
            attempts++;
            if (attempts >= maxAttempts) {
                clearInterval(interval);
                loading.style.display = 'none';
                results.innerHTML = '<p class="error">Timeout - please try again</p>';
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000);
}

function displayResults(data) {
    const results = document.getElementById('results');
    
    // Clear any existing layers (except base map)
    map.eachLayer((layer) => {
        if (layer !== map._layers[Object.keys(map._layers)[0]]) { // Keep base map
            map.removeLayer(layer);
        }
    });
    
    let html = '<h4>Analysis Complete ✅</h4>';
    
    // Add the groundwater layer to map
    if (data.result_url) {
        // If result_url is an image (PNG/JPG)
        if (data.result_url.match(/\.(png|jpg|jpeg)$/i)) {
            // Get current map bounds
            const bounds = map.getBounds();
            
            // Add as image overlay
            L.imageOverlay(data.result_url, bounds, {
                opacity: 0.7,
                alt: 'Groundwater Potential'
            }).addTo(map);
            
            html += '<p>✅ Groundwater layer added to map</p>';
        } 
        // If result_url is HTML (interactive map)
        else if (data.result_url.match(/\.html$/i)) {
            html += `<p><a href="${data.result_url}" target="_blank">Open Interactive Map</a></p>`;
        }
    }
    
    // Add thumbnail if available
    if (data.thumbnail_url) {
        html += `<p><img src="${data.thumbnail_url}" style="max-width:100%; border-radius:4px; margin-top:10px;"></p>`;
    }
    
    // Add statistics
    if (data.statistics) {
        html += '<div style="margin-top:15px; padding-top:10px; border-top:1px solid #ddd;">';
        html += '<h4>Statistics</h4>';
        html += `<p>Mean Score: ${data.statistics.mean?.toFixed(2) || 'N/A'}</p>`;
        html += `<p>Std Dev: ${data.statistics.std?.toFixed(2) || 'N/A'}</p>`;
        
        if (data.statistics.zone_areas) {
            html += '<h4>Zone Areas (km²)</h4>';
            html += '<ul style="list-style:none; padding:0;">';
            for (const [zone, area] of Object.entries(data.statistics.zone_areas)) {
                const color = {
                    'very_low': '#ff0000',
                    'low': '#ff9900',
                    'moderate': '#ffff00',
                    'high': '#99ff00',
                    'very_high': '#00aa00'
                }[zone] || '#ccc';
                
                html += `<li><span style="display:inline-block; width:12px; height:12px; background:${color}; margin-right:5px;"></span> ${zone.replace('_', ' ')}: ${area.toFixed(2)} km²</li>`;
            }
            html += '</ul>';
        }
        html += '</div>';
    }
    
    results.innerHTML = html;
}
