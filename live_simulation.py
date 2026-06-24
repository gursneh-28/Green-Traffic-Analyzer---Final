"""
live_simulation.py
==================
Live simulation: reads from video files or webcam streams, extracts one frame
per camera at the start of every cycle, runs YOLO detection, feeds results
into the adaptive controller, and pushes live state to the dashboard via
Flask-SocketIO.

Two modes
---------
  --mode video   : reads MP4/AVI files from data/videos/<camera_id>.mp4
  --mode webcam  : opens system webcams (index 0,1,2,3)
  --mode demo    : no camera needed — uses synthetic counts that vary each
                   cycle so you can demo the dashboard without hardware

Usage
-----
    python live_simulation.py --mode demo
    python live_simulation.py --mode video --cameras North South East West
    python live_simulation.py --mode webcam
"""

import argparse
import logging
import os
import sys
import threading
import time
from datetime import datetime

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from vehicle_detector import VehicleDetector, DetectionResult
from signal_controller import TrafficSignalController, YELLOW_TIME, ALL_RED_TIME

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

VIDEO_DIR = os.path.join(os.path.dirname(__file__), "data", "videos")


# ---------------------------------------------------------------------------
# Frame sources
# ---------------------------------------------------------------------------
class VideoFrameSource:
    """Reads one frame per cycle from an MP4/AVI file (loops at end)."""

    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        path = os.path.join(VIDEO_DIR, f"{camera_id}.mp4")
        if not os.path.exists(path):
            path = os.path.join(VIDEO_DIR, f"{camera_id}.avi")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"No video found for {camera_id} in {VIDEO_DIR}. "
                "Expected <camera_id>.mp4 or <camera_id>.avi"
            )
        self._cap = cv2.VideoCapture(path)
        logger.info("VideoFrameSource: %s → %s", camera_id, path)

    def grab_frame(self):
        """Return one BGR frame; loops video when exhausted."""
        ret, frame = self._cap.read()
        if not ret:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
        return frame if ret else None

    def release(self) -> None:
        self._cap.release()


class WebcamFrameSource:
    """Reads from a system webcam by index."""

    def __init__(self, camera_id: str, index: int) -> None:
        self.camera_id = camera_id
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open webcam index {index} for {camera_id}")
        logger.info("WebcamFrameSource: %s → index %d", camera_id, index)

    def grab_frame(self):
        ret, frame = self._cap.read()
        return frame if ret else None

    def release(self) -> None:
        self._cap.release()


class DemoFrameSource:
    """
    No hardware needed — returns None (detector will use synthetic counts).
    Used for dashboard demos without a camera or video file.
    """

    def __init__(self, camera_id: str, cycle_ref: list) -> None:
        self.camera_id = camera_id
        self._cycle    = cycle_ref    # shared mutable [cycle_number]

    def grab_frame(self):
        return None   # signal to use synthetic counts


# ---------------------------------------------------------------------------
# Synthetic count generator for demo mode
# ---------------------------------------------------------------------------
import math

def synthetic_detection(camera_id: str, cycle_num: int) -> DetectionResult:
    """
    Returns a DetectionResult with plausible varying counts so the dashboard
    demo looks realistic without any camera hardware.
    """
    # Each camera follows a slightly different sine wave
    offsets = {"camera_1": 0, "camera_2": 1.0, "camera_3": 2.1, "camera_4": 3.3}
    offset  = offsets.get(camera_id, 0)
    base    = 8 + 10 * abs(math.sin(cycle_num * 0.5 + offset))
    cars    = max(0, int(base))
    buses   = max(0, int(base * 0.1))
    trucks  = max(0, int(base * 0.05))
    motos   = max(0, int(base * 0.15))
    counts  = {}
    if cars:   counts["car"]        = cars
    if buses:  counts["bus"]        = buses
    if trucks: counts["truck"]      = trucks
    if motos:  counts["motorcycle"] = motos
    return DetectionResult(counts, f"demo:{camera_id}")


# ---------------------------------------------------------------------------
# Live runner
# ---------------------------------------------------------------------------
class LiveSimulation:

    def __init__(
        self,
        camera_ids: list[str],
        mode: str,
        dashboard_state: dict,
        state_lock: threading.Lock,
    ) -> None:
        self.camera_ids     = camera_ids
        self.mode           = mode
        self.dashboard_state = dashboard_state
        self.state_lock     = state_lock
        self._stop_event    = threading.Event()
        self._cycle_ref     = [0]

        self.detector   = VehicleDetector(
            save_annotated=True,
            output_dir="data/annotated",
        )
        self.controller = TrafficSignalController(camera_ids)

        # Build frame sources
        self.sources: dict = {}
        for i, cam in enumerate(camera_ids):
            if mode == "video":
                self.sources[cam] = VideoFrameSource(cam)
            elif mode == "webcam":
                self.sources[cam] = WebcamFrameSource(cam, index=i)
            else:
                self.sources[cam] = DemoFrameSource(cam, self._cycle_ref)

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("Live simulation starting | mode=%s | cameras=%s",
                    self.mode, self.camera_ids)
        try:
            while not self._stop_event.is_set():
                self._cycle_ref[0] += 1
                cycle_num = self._cycle_ref[0]
                logger.info("=== Live Cycle %d ===", cycle_num)

                # 1. Capture + detect
                detections: dict[str, DetectionResult] = {}
                for cam in self.camera_ids:
                    frame = self.sources[cam].grab_frame()
                    if frame is not None:
                        det = self.detector.detect_from_frame(frame, cam)
                    else:
                        det = synthetic_detection(cam, cycle_num)
                    detections[cam] = det
                    logger.info(
                        "  %s | %s | weighted=%.1f",
                        cam, det.raw_counts, det.weighted_count,
                    )

                # 2. Compute cycle (pressure scores + green times)
                cycle_result = self.controller.run_cycle(detections)

                # 3. Step through each phase with real timing
                for phase in cycle_result.phases:
                    cam        = phase.camera_id
                    green_time = int(phase.green_time)

                    # ── GREEN ──
                    for remaining in range(green_time, 0, -1):
                        self._push_state(
                            current_green=cam,
                            phase_state="GREEN",
                            countdown=remaining,
                            cycle_result=cycle_result,
                            detections=detections,
                        )
                        time.sleep(1)
                        if self._stop_event.is_set():
                            return

                    # ── YELLOW ──
                    for remaining in range(YELLOW_TIME, 0, -1):
                        self._push_state(
                            current_green=cam,
                            phase_state="YELLOW",
                            countdown=remaining,
                            cycle_result=cycle_result,
                            detections=detections,
                        )
                        time.sleep(1)
                        if self._stop_event.is_set():
                            return

                    # ── ALL RED ──
                    self._push_state(
                        current_green="ALL RED",
                        phase_state="ALL_RED",
                        countdown=ALL_RED_TIME,
                        cycle_result=cycle_result,
                        detections=detections,
                    )
                    time.sleep(ALL_RED_TIME)

        except KeyboardInterrupt:
            logger.info("Live simulation stopped by user.")
        finally:
            for src in self.sources.values():
                if hasattr(src, "release"):
                    src.release()

    def _push_state(
        self,
        current_green: str,
        phase_state: str,
        countdown: int,
        cycle_result,
        detections: dict,
    ) -> None:
        """Write the latest state into the shared dashboard dict."""
        with self.state_lock:
            self.dashboard_state.update({
                "timestamp":              datetime.now().isoformat(),
                "cycle_number":           cycle_result.cycle_number,
                "current_green":          current_green,
                "phase_state":            phase_state,   # GREEN / YELLOW / ALL_RED
                "countdown_s":            countdown,
                "efficiency_pct":         cycle_result.efficiency_pct,
                "co2_saved_g":            cycle_result.co2_saved_g,
                "fuel_saved_ml":          cycle_result.fuel_saved_ml,
                "cumulative_co2_saved_g": cycle_result.cumulative_co2_saved_g,
                "cumulative_fuel_saved_ml": cycle_result.cumulative_fuel_saved_ml,
                "vehicle_counts": {
                    cam: {
                        "total":    det.total_vehicles,
                        "weighted": round(det.weighted_count, 1),
                        "breakdown": det.raw_counts,
                    }
                    for cam, det in detections.items()
                },
                "phase_plan": [
                    {
                        "camera":     p.camera_id,
                        "green_time": p.green_time,
                        "pressure":   p.pressure_score,
                        "carryover":  p.carryover_out,
                    }
                    for p in cycle_result.phases
                ],
            })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Green Traffic Analyzer — live simulation"
    )
    parser.add_argument(
        "--mode", choices=["demo", "video", "webcam"], default="demo",
        help="Frame source mode (default: demo)",
    )
    parser.add_argument(
        "--cameras", nargs="+",
        default=["camera_1", "camera_2", "camera_3", "camera_4"],
        help="Camera IDs (match data/videos/ filenames for video mode)",
    )
    args = parser.parse_args()

    # Shared state between simulation thread and dashboard
    dashboard_state: dict       = {}
    state_lock: threading.Lock  = threading.Lock()

    # Import dashboard here to avoid circular import
    from dashboard import create_app
    app, socketio = create_app(dashboard_state, state_lock)

    # Simulation runs in a background thread
    sim = LiveSimulation(args.cameras, args.mode, dashboard_state, state_lock)
    sim_thread = threading.Thread(target=sim.run, daemon=True)
    sim_thread.start()

    logger.info("Dashboard → http://127.0.0.1:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()