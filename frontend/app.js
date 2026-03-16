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
    
    let html = '<h4>Analysis Complete ✅</h4>';
    
    if (data.statistics) {
        html += '<p><strong>Statistics:</strong></p>';
        html += `<p>Mean: ${data.statistics.mean?.toFixed(2) || 'N/A'}</p>`;
        html += `<p>Std Dev: ${data.statistics.std?.toFixed(2) || 'N/A'}</p>`;
        
        if (data.statistics.zone_areas) {
            html += '<p><strong>Zone Areas (km²):</strong></p>';
            html += '<ul>';
            for (const [zone, area] of Object.entries(data.statistics.zone_areas)) {
                html += `<li>${zone}: ${area.toFixed(2)} km²</li>`;
            }
            html += '</ul>';
        }
    }
    
    if (data.thumbnail_url) {
        html += `<p><img src="${data.thumbnail_url}" style="max-width:100%; border-radius:4px;"></p>`;
    }
    
    if (data.result_url) {
        html += `<p><a href="${data.result_url}" target="_blank">View Interactive Map</a></p>`;
    }
    
    results.innerHTML = html;
}
