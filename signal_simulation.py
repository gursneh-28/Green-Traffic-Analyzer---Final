"""
signal_simulation.py
====================
Offline simulation: reads real images from data/cameras/<cam>/ for each
direction, runs YOLO detection, feeds results into the adaptive controller,
and writes structured CSV + JSON output to results/.

Usage
-----
    python signal_simulation.py                   # default: 3 cycles
    python signal_simulation.py --cycles 10
    python signal_simulation.py --cameras North South East West
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from glob import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from vehicle_detector import VehicleDetector, DetectionResult
from signal_controller import TrafficSignalController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_ROOT    = os.path.join(os.path.dirname(__file__), "data", "cameras")
RESULTS_DIR  = os.path.join(os.path.dirname(__file__), "results")
CSV_PATH     = os.path.join(RESULTS_DIR, "signal_cycles.csv")
JSON_PATH    = os.path.join(RESULTS_DIR, "signal_cycles.json")

SUPPORTED_EXT = {".jpg", ".jpeg", ".png"}


# ---------------------------------------------------------------------------
# Image loader — returns the next image path for a camera (round-robin)
# ---------------------------------------------------------------------------
class CameraImageLoader:
    """
    Round-robins through all images in data/cameras/<camera_id>/.
    Every call to next_image() returns the next available file path.
    This simulates 'fresh capture every cycle' even with static images.
    """

    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        folder = os.path.join(DATA_ROOT, camera_id)
        self.images = sorted([
            p for p in glob(os.path.join(folder, "*"))
            if os.path.splitext(p)[1].lower() in SUPPORTED_EXT
        ])
        if not self.images:
            logger.warning("No images found for camera %s in %s", camera_id, folder)
        self._index = 0

    def next_image(self) -> str | None:
        if not self.images:
            return None
        path = self.images[self._index % len(self.images)]
        self._index += 1
        return path


# ---------------------------------------------------------------------------
# CSV writer — appends one row per phase per cycle
# ---------------------------------------------------------------------------
CSV_FIELDS = [
    "timestamp", "cycle", "camera", "direction",
    "raw_car", "raw_motorcycle", "raw_truck", "raw_bus",
    "total_vehicles", "weighted_count",
    "carryover_in", "vehicles_cleared", "carryover_out",
    "pressure_score", "green_time",
    "co2_saved_g", "fuel_saved_ml",
    "cycle_efficiency_pct",
    "cumulative_co2_saved_g", "cumulative_fuel_saved_ml",
    "annotated_image",
]


def init_csv() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(CSV_PATH, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()
    logger.info("CSV initialised: %s", CSV_PATH)


def append_csv(cycle_result, phases_with_images: dict) -> None:
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        for phase in cycle_result.phases:
            writer.writerow({
                "timestamp":               cycle_result.timestamp,
                "cycle":                   cycle_result.cycle_number,
                "camera":                  phase.camera_id,
                "direction":               phase.direction,
                "raw_car":                 phase.raw_counts.get("car", 0),
                "raw_motorcycle":          phase.raw_counts.get("motorcycle", 0),
                "raw_truck":               phase.raw_counts.get("truck", 0),
                "raw_bus":                 phase.raw_counts.get("bus", 0),
                "total_vehicles":          phase.vehicle_count,
                "weighted_count":          phase.weighted_count,
                "carryover_in":            phase.carryover_in,
                "vehicles_cleared":        phase.vehicles_cleared,
                "carryover_out":           phase.carryover_out,
                "pressure_score":          phase.pressure_score,
                "green_time":              phase.green_time,
                "co2_saved_g":             phase.co2_saved_g,
                "fuel_saved_ml":           phase.fuel_saved_ml,
                "cycle_efficiency_pct":    cycle_result.efficiency_pct,
                "cumulative_co2_saved_g":  cycle_result.cumulative_co2_saved_g,
                "cumulative_fuel_saved_ml":cycle_result.cumulative_fuel_saved_ml,
                "annotated_image":         phases_with_images.get(phase.camera_id, ""),
            })


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------
def run_simulation(camera_ids: list[str], num_cycles: int) -> None:
    logger.info(
        "Starting offline simulation | cameras=%s | cycles=%d",
        camera_ids, num_cycles,
    )

    detector   = VehicleDetector(save_annotated=True, output_dir="data/annotated")
    controller = TrafficSignalController(camera_ids)
    loaders    = {cam: CameraImageLoader(cam) for cam in camera_ids}

    init_csv()
    all_results = []

    for cycle_num in range(1, num_cycles + 1):
        logger.info("--- Cycle %d / %d ---", cycle_num, num_cycles)

        # Fresh detection for every camera this cycle
        detections:          dict[str, DetectionResult] = {}
        phases_with_images:  dict[str, str]             = {}

        for cam in camera_ids:
            image_path = loaders[cam].next_image()
            if image_path:
                det = detector.detect(image_path)
                phases_with_images[cam] = det.annotated_path or image_path
            else:
                # No image available → treat as empty road
                det = DetectionResult({}, cam)
                logger.warning("No image for %s — using zero counts", cam)
            detections[cam] = det

        # Run adaptive cycle
        cycle_result = controller.run_cycle(detections)

        # Persist
        append_csv(cycle_result, phases_with_images)
        all_results.append(_cycle_to_dict(cycle_result))

        # Console summary
        print(
            f"\n{'='*55}\n"
            f"  Cycle {cycle_result.cycle_number:>3} | "
            f"Efficiency {cycle_result.efficiency_pct:>5.1f}% | "
            f"CO₂ saved {cycle_result.co2_saved_g:>6.1f} g | "
            f"Fuel saved {cycle_result.fuel_saved_ml:>6.1f} mL\n"
            f"  Cumulative → CO₂ {cycle_result.cumulative_co2_saved_g:.1f} g | "
            f"Fuel {cycle_result.cumulative_fuel_saved_ml:.1f} mL\n"
            f"{'='*55}"
        )
        for phase in cycle_result.phases:
            print(
                f"    {phase.direction:<8} | green {phase.green_time:>4.1f}s | "
                f"vehicles {phase.vehicle_count:>3} (weighted {phase.weighted_count:>5.1f}) | "
                f"cleared {phase.vehicles_cleared:>4.1f} | "
                f"carryover → {phase.carryover_out:>4.1f} | "
                f"pressure {phase.pressure_score:>6.2f}"
            )

    # Final JSON dump
    with open(JSON_PATH, "w") as f:
        json.dump(all_results, f, indent=2)

    logger.info("Simulation complete.")
    logger.info("CSV  → %s", CSV_PATH)
    logger.info("JSON → %s", JSON_PATH)

    _print_final_summary(controller)


def _cycle_to_dict(cr) -> dict:
    return {
        "cycle":                   cr.cycle_number,
        "timestamp":               cr.timestamp,
        "total_cycle_time_s":      cr.total_cycle_time,
        "efficiency_pct":          cr.efficiency_pct,
        "co2_saved_g":             cr.co2_saved_g,
        "fuel_saved_ml":           cr.fuel_saved_ml,
        "cumulative_co2_saved_g":  cr.cumulative_co2_saved_g,
        "cumulative_fuel_saved_ml":cr.cumulative_fuel_saved_ml,
        "phases": [
            {
                "camera":           p.camera_id,
                "green_time":       p.green_time,
                "total_vehicles":   p.vehicle_count,
                "weighted_count":   p.weighted_count,
                "carryover_in":     p.carryover_in,
                "vehicles_cleared": p.vehicles_cleared,
                "carryover_out":    p.carryover_out,
                "pressure_score":   p.pressure_score,
                "raw_counts":       p.raw_counts,
                "co2_saved_g":      p.co2_saved_g,
                "fuel_saved_ml":    p.fuel_saved_ml,
            }
            for p in cr.phases
        ],
    }


def _print_final_summary(controller: TrafficSignalController) -> None:
    total = controller.emission_totals
    cycles = len(controller.history)
    print(
        f"\n{'#'*55}\n"
        f"  SIMULATION COMPLETE — {cycles} cycles\n"
        f"  Total CO₂ saved  : {total['co2_g']:>8.1f} g  "
        f"({total['co2_g']/1000:.3f} kg)\n"
        f"  Total fuel saved : {total['fuel_ml']:>8.1f} mL "
        f"({total['fuel_ml']/1000:.3f} L)\n"
        f"  Avg efficiency   : "
        f"{sum(c.efficiency_pct for c in controller.history)/cycles:.1f}%\n"
        f"{'#'*55}\n"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Green Traffic Analyzer — offline simulation")
    parser.add_argument("--cycles",  type=int, default=3,
                        help="Number of signal cycles to simulate (default: 3)")
    parser.add_argument("--cameras", nargs="+",
                        default=["camera_1", "camera_2", "camera_3", "camera_4"],
                        help="Camera / direction IDs (must match data/cameras/ subfolders)")
    args = parser.parse_args()

    run_simulation(args.cameras, args.cycles)