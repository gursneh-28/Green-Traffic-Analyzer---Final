<div align="center">

# 🚦 Green Traffic Analyzer

**Adaptive traffic signal control using computer vision to reduce vehicle emissions**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-FF6B35?style=flat)](https://ultralytics.com)
[![Flask](https://img.shields.io/badge/Flask-SocketIO-000000?style=flat&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Tests](https://img.shields.io/badge/Tests-42%20passing-00C853?style=flat&logo=pytest&logoColor=white)](tests/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)

*A pressure-score based adaptive signal control system that detects vehicles using YOLOv8, dynamically allocates green time per direction, eliminates queue starvation, and quantifies CO₂ and fuel savings in real time.*

</div>

---

## 📋 Table of Contents

- [The Problem](#the-problem)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running Modes](#running-modes)
- [Dashboard](#dashboard)
- [Results & Emission Savings](#results--emission-savings)
- [Tests](#tests)
- [Tech Stack](#tech-stack)

---

## The Problem

Fixed-cycle traffic signals waste green time on empty roads and starve busy directions — vehicles idle unnecessarily, burning fuel and emitting CO₂. A single idle car emits ~28 g CO₂/min; a bus emits ~90 g/min.

**Green Traffic Analyzer** replaces fixed timing with a vision-driven adaptive scheduler that sees actual traffic, weights vehicles by type, and allocates green time proportionally — reducing idle time and the emissions it causes.

---

## How It Works

### Pressure-Score Scheduling

Every direction at the intersection gets a **pressure score** each cycle:

```
pressure = (weighted_vehicle_count + carryover × 1.5) × (1 + cycles_since_last_green × 0.3)
```

| Component | Purpose |
|---|---|
| `weighted_vehicle_count` | Buses/trucks count more than cars toward green time |
| `carryover × 1.5` | Leftover vehicles from the last cycle get a 50% penalty bonus |
| `cycles_since_last_green × 0.3` | Wait-time multiplier — grows every cycle a direction is skipped |

The wait-time multiplier **guarantees no starvation** — every direction's score eventually climbs high enough to win the next slot, even with zero vehicles.

### Vehicle Type Weights

| Class | Weight | Idle CO₂ (g/min) |
|---|---|---|
| Motorcycle | 0.5× | 10 g/min |
| Car | 1.0× | 28 g/min |
| Truck | 2.5× | 75 g/min |
| Bus | 3.0× | 90 g/min |

### Green Time Allocation

Green time is allocated proportional to pressure score, hard-clamped to a safe range:

```
green_time = proportional(pressure) → clamped [15s, 45s]
```

### Queue Carryover

Vehicles that don't clear during a green phase carry forward with 1.5× weight into the next cycle:

```
vehicles_cleared = green_time × 0.5 veh/s
carryover_out    = max(0, weighted_count + carryover_in − vehicles_cleared)
```

### Emission Model

After every phase, idle time saved vs the fixed 22.5s baseline is converted to emission savings:

```
idle_time_saved = max(0, fixed_green − adaptive_green)
CO₂_saved_g     = Σ count[class] × idle_co2[class] × (idle_time_saved / 60)
fuel_saved_mL   = CO₂_saved_g × 0.43
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Entry Points                          │
│   signal_simulation.py        live_simulation.py        │
│   (offline, static images)    (live: video/webcam/demo) │
└────────────────┬────────────────────────┬───────────────┘
                 │                        │
                 ▼                        ▼
┌─────────────────────────────────────────────────────────┐
│                 src/vehicle_detector.py                  │
│  YOLOv8 inference → DetectionResult                     │
│  (raw_counts, weighted_count, idle_co2_per_min)         │
└─────────────────────────┬───────────────────────────────┘
                          │  DetectionResult per camera
                          ▼
┌─────────────────────────────────────────────────────────┐
│                src/signal_controller.py                  │
│  Pressure scores → green time allocation                 │
│  Queue carryover → emission model → CycleResult         │
└──────────┬──────────────────────────────────┬───────────┘
           │                                  │
           ▼                                  ▼
┌─────────────────────┐            ┌──────────────────────┐
│  results/           │            │  dashboard.py        │
│  signal_cycles.csv  │            │  Flask-SocketIO      │
│  signal_cycles.json │            │  Real-time browser   │
└─────────────────────┘            │  UI with charts      │
                                   └──────────────────────┘
```

---

## Project Structure

```
Green-Traffic-Analyzer/
│
├── src/
│   ├── vehicle_detector.py     # YOLOv8 wrapper — DetectionResult, weights, CO₂ factors
│   ├── signal_controller.py    # Pressure-score scheduler, emission model, CycleResult
│   ├── config_loader.py        # Loads config.yaml once (lru_cache), typed accessors
│   └── logger_setup.py         # Coloured stdout + dated file logging
│
├── tests/
│   ├── test_vehicle_detector.py   # 10 unit tests — weights, CO₂ math, edge cases
│   ├── test_signal_controller.py  # 25 unit tests — scheduling, carryover, emissions
│   └── test_config.py             # 7 unit tests — config validation
│
├── data/
│   ├── cameras/                # Static images: data/cameras/<camera_id>/<image>.jpg
│   │   ├── camera_1/
│   │   ├── camera_2/
│   │   ├── camera_3/
│   │   └── camera_4/
│   ├── videos/                 # Video files for live mode: <camera_id>.mp4
│   └── annotated/              # YOLO bounding-box output images (auto-generated)
│
├── results/
│   ├── signal_cycles.csv       # Per-phase log: counts, green time, CO₂, efficiency
│   └── signal_cycles.json      # Full cycle history in JSON
│
├── signal_simulation.py        # Offline simulation — real images, full CSV/JSON output
├── live_simulation.py          # Live simulation — video/webcam/demo + dashboard
├── dashboard.py                # Flask-SocketIO web dashboard
├── config.yaml                 # Central config — all constants in one place
├── requirements.txt
└── pytest.ini
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/Green-Traffic-Analyzer.git
cd Green-Traffic-Analyzer
pip install -r requirements.txt
```

### 2. Add your images

Place traffic images in:
```
data/cameras/camera_1/image_1.jpg
data/cameras/camera_2/image_1.jpg
data/cameras/camera_3/image_1.jpg
data/cameras/camera_4/image_1.jpg
```

### 3. Run

```bash
# Offline simulation (processes real images, writes CSV + JSON)
python signal_simulation.py

# Live dashboard — demo mode (no camera needed)
python live_simulation.py --mode demo

# Live dashboard — from video files
python live_simulation.py --mode video

# Live dashboard — from webcams
python live_simulation.py --mode webcam
```

Open **http://localhost:5000** to see the dashboard.

---

## Configuration

All constants live in `config.yaml` — no source code changes needed to tune the system:

```yaml
signal:
  total_cycle_time: 90    # seconds
  min_green_time:   15    # hard safety floor — no direction gets less
  max_green_time:   45    # hard cap per phase

scheduler:
  carryover_weight: 1.5   # leftover vehicles count this much more next cycle
  wait_growth:      0.3   # starvation prevention multiplier per missed cycle

vehicle_weights:
  car:        1.0
  motorcycle: 0.5
  truck:      2.5
  bus:        3.0

emission:
  idle_co2_g_per_min:
    car:   28.0
    bus:   90.0
    truck: 75.0
```

---

## Running Modes

### Offline simulation

```bash
python signal_simulation.py --cycles 10 --cameras camera_1 camera_2 camera_3 camera_4
```

- Reads real images from `data/cameras/<camera_id>/` — round-robins through them each cycle
- Runs YOLO detection on every image every cycle (no stale counts)
- Writes complete CSV log to `results/signal_cycles.csv`
- Writes full JSON history to `results/signal_cycles.json`
- Prints per-cycle summary with emission savings to console

### Live simulation

```bash
# Demo mode — synthetic traffic data, no hardware required
python live_simulation.py --mode demo

# Video mode — reads MP4/AVI from data/videos/<camera_id>.mp4
python live_simulation.py --mode video --cameras North South East West

# Webcam mode — opens system cameras by index
python live_simulation.py --mode webcam
```

---

## Dashboard

The real-time web dashboard runs at **http://localhost:5000** during live simulation.

### Features

| Panel | What it shows |
|---|---|
| **KPI row** | Efficiency %, CO₂ saved this cycle, fuel saved, active phase |
| **Intersection diagram** | N/S/E/W signal boxes — green/yellow/red in real time with vehicle count |
| **Countdown ring** | Animated SVG countdown for current phase — colour-coded by state |
| **Phase plan table** | All 4 directions with pressure score, green time, carryover, allocation bar |
| **Emission panel** | Cumulative CO₂ and fuel saved, per-cycle breakdown, km-of-driving equivalent |
| **Vehicle breakdown** | Per-camera grid — cars/buses/trucks/motorcycles with colour codes |
| **Efficiency chart** | Chart.js line graph of efficiency % across all cycles (rolling 30) |

Updates via **WebSocket push every second** — no polling, no lag.

**Standalone demo** (no simulation needed):
```bash
python dashboard.py
```

---

## Results & Emission Savings

### Signal timing comparison

| Metric | Fixed timing | Adaptive (this system) |
|---|---|---|
| Green time per direction | 22.5s (equal) | 15–45s (pressure-based) |
| Starvation risk | Not guaranteed | None (wait multiplier) |
| Vehicle type awareness | ❌ | ✅ Bus = 3× car |
| Queue carryover | ❌ | ✅ Persists across cycles |
| Emission tracking | ❌ | ✅ Per phase, cumulative |

### Efficiency — Queue Reduction (Primary Metric)

The primary efficiency metric is **queue reduction** — how much less carryover (leftover vehicles) our adaptive system leaves compared to fixed timing:

```
fixed_carryover    = Σ max(0, vehicles[d] - 22.5s × 0.5 veh/s)
adaptive_carryover = Σ carryover_out per phase

queue_reduction = (1 - adaptive_carryover / fixed_carryover) × 100
```

**Example cycle (uneven traffic):**

| Direction | Vehicles | Fixed clears | Fixed carryover | Adaptive green | Adaptive clears | Adaptive carryover |
|---|---|---|---|---|---|---|
| North | 30 | 11 | **19** | 40s | 20 | **10** |
| South | 5 | 5 | 0 | 15s | 5 | 0 |
| East | 8 | 8 | 0 | 20s | 8 | 0 |
| West | 2 | 2 | 0 | 15s | 2 | 0 |
| **Total** | | | **19** | | | **10** |

```
queue_reduction = (1 - 10/19) × 100 = 47.4%
```

Nearly half the queue that fixed timing would leave behind is cleared by our system. Those 9 extra vehicles don't idle through the next cycle — that is directly where the emission savings come from.

> **Why not report a single fixed percentage like "17.8% efficiency"?**
> Because efficiency varies with traffic mix. With uniform traffic, both systems perform equally. With uneven traffic (one busy direction), queue reduction can reach 40–60%. Reporting a live per-cycle number is more honest and more useful than a hardcoded claim.

### Emission model (per busy intersection, estimated)

| Scenario | Queue reduction | CO₂ saved | Fuel saved |
|---|---|---|---|
| 1 cycle (90s), uneven traffic | 30–50% less carryover | ~15–40 g | ~6–17 mL |
| 1 hour (~40 cycles) | — | ~600g–1.6 kg | ~240–690 mL |
| 1 day (12 active hours) | — | ~7–19 kg CO₂ | ~3–8 L fuel |

*Values depend on traffic volume and mix. Based on EPA idling emission factors.*

---

## Tests

```bash
# Run all 42 tests
python -m pytest -v --tb=short

# With coverage report
python -m pytest --cov=src --cov-report=term-missing
```

### Test coverage

| File | Tests | What's covered |
|---|---|---|
| `test_vehicle_detector.py` | 10 | Weighted counts, CO₂ math, class ordering, edge cases |
| `test_signal_controller.py` | 25 | Pressure scoring, green time bounds, no starvation, carryover propagation, emission model, efficiency, reset |
| `test_config.py` | 7 | Config load, required keys, value sanity, missing file error |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Vehicle detection | [YOLOv8n](https://ultralytics.com) (Ultralytics) |
| Computer vision | OpenCV |
| Scheduling algorithm | Custom pressure-score model (inspired by SCOOT/SCATS adaptive signal control) |
| Web dashboard | Flask + Flask-SocketIO |
| Frontend | Vanilla JS + Chart.js + WebSocket |
| Config | YAML (`config.yaml`) |
| Testing | pytest + pytest-cov |
| Language | Python 3.12 |

---

## Inspiration

Real-world adaptive traffic signal systems like **SCOOT** (Split Cycle Offset Optimisation Technique) and **SCATS** (Sydney Coordinated Adaptive Traffic System) use pressure and saturation flow concepts to allocate green time dynamically. This project implements a simplified but structurally similar pressure-score model as a demonstration of the same principles using open-source computer vision.

---

<div align="center">
Built as part of a computer vision + systems project — contributions welcome.
</div>