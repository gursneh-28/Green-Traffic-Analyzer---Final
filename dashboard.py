import os
import sys
import json
import time
from datetime import datetime
from flask import Flask, render_template, jsonify

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

app = Flask(__name__)

class TrafficDashboard:
    def __init__(self):
        self.current_data = {
            'vehicle_counts': {'camera_1': 0, 'camera_2': 0, 'camera_3': 0, 'camera_4': 0},
            'current_green': None,
            'efficiency': 0,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
    
    def update_data(self, vehicle_counts, current_green, efficiency):
        self.current_data = {
            'vehicle_counts': vehicle_counts,
            'current_green': current_green,
            'efficiency': efficiency,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }

# Global dashboard instance
dashboard = TrafficDashboard()

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🚦 Green Traffic Analyzer</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .dashboard { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
            .camera { border: 1px solid #ccc; padding: 15px; border-radius: 5px; }
            .green { background-color: #90EE90; }
            .red { background-color: #FFB6C1; }
            .stats { grid-column: span 2; background: #f0f0f0; padding: 15px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>🚦 Green Traffic Analyzer - Live Dashboard</h1>
        <div id="dashboard" class="dashboard">
            <!-- Content will be updated by JavaScript -->
        </div>
        <script>
            function updateDashboard() {
                fetch('/data')
                    .then(response => response.json())
                    .then(data => {
                        const dashboard = document.getElementById('dashboard');
                        dashboard.innerHTML = `
                            <div class="stats">
                                <h3>📊 Live Statistics</h3>
                                <p>🕒 Last Update: ${data.timestamp}</p>
                                <p>📈 Efficiency: ${data.efficiency}%</p>
                                <p>🚥 Current Green: ${data.current_green || 'None'}</p>
                            </div>
                            ${Object.entries(data.vehicle_counts).map(([camera, count]) => `
                                <div class="camera ${data.current_green === camera ? 'green' : 'red'}">
                                    <h3>${camera.toUpperCase()}</h3>
                                    <p>🚗 Vehicles: ${count}</p>
                                    <p>${data.current_green === camera ? '🟢 GREEN' : '🔴 RED'}</p>
                                </div>
                            `).join('')}
                        `;
                    });
            }
            
            // Update every 3 seconds
            setInterval(updateDashboard, 3000);
            updateDashboard(); // Initial load
        </script>
    </body>
    </html>
    """

@app.route('/data')
def get_data():
    return jsonify(dashboard.current_data)

def run_dashboard():
    print("🌐 Starting Traffic Dashboard...")
    print("   📍 Open http://localhost:5000 in your browser")
    app.run(debug=True, use_reloader=False)

if __name__ == '__main__':
    run_dashboard()