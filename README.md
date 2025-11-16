# 🚦 Green Traffic Analyzer

AI-powered traffic management system that optimizes signal timing using computer vision to reduce vehicle waiting time through adaptive control.

## 🎯 What We Built

### Week 1: Vehicle Detection
- Implemented YOLOv8 for real-time vehicle detection
- Processed 18 traffic intersection images
- Counted cars, trucks, buses, and motorcycles

### Week 2: Smart Signal Control  
- Built adaptive traffic signal controller
- 90-second fixed cycles with 15-45s green times
- Prioritizes busiest directions automatically
- **17.8% more efficient** than fixed timing

### Week 3: Live Dashboard
- Real-time console dashboard
- Live traffic monitoring
- Signal status visualization

## 🚀 How to Run

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Simulations

#### Basic Signal Simulation:
```bash
python signal_simulation.py
```

#### Live Dashboard:
```bash
python live_simulation.py
```

## 📊 Results
- Cycle Time: 90-95 seconds
- Green Time: 15-27 seconds (adaptive)
- Efficiency: 17.8% improvement
- Detection: High accuracy vehicle counting

## 🛠️ Tech Stack
- Python, YOLOv8, OpenCV
- Custom signal timing algorithms
- Real-time dashboard