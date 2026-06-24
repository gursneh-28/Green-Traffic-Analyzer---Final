"""
tests/test_vehicle_detector.py
================================
Unit tests for VehicleDetector and DetectionResult.
No camera / YOLO model required — all tests use mock data.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from vehicle_detector import DetectionResult, VEHICLE_WEIGHTS, IDLE_CO2_G_PER_MIN


# ---------------------------------------------------------------------------
# DetectionResult — weighted_count
# ---------------------------------------------------------------------------
class TestDetectionResult:

    def test_empty_counts(self):
        det = DetectionResult({}, "img.jpg")
        assert det.total_vehicles == 0
        assert det.weighted_count == 0.0

    def test_cars_only(self):
        det = DetectionResult({"car": 5}, "img.jpg")
        assert det.total_vehicles == 5
        assert det.weighted_count == pytest.approx(5 * VEHICLE_WEIGHTS["car"])

    def test_mixed_vehicles_weighted_count(self):
        counts = {"car": 4, "bus": 1, "truck": 2, "motorcycle": 3}
        det = DetectionResult(counts, "img.jpg")
        expected = (
            4 * VEHICLE_WEIGHTS["car"]
            + 1 * VEHICLE_WEIGHTS["bus"]
            + 2 * VEHICLE_WEIGHTS["truck"]
            + 3 * VEHICLE_WEIGHTS["motorcycle"]
        )
        assert det.weighted_count == pytest.approx(expected)
        assert det.total_vehicles == 10

    def test_bus_weighs_more_than_car(self):
        car_det = DetectionResult({"car": 1}, "img.jpg")
        bus_det = DetectionResult({"bus": 1}, "img.jpg")
        assert bus_det.weighted_count > car_det.weighted_count

    def test_truck_weighs_more_than_motorcycle(self):
        truck = DetectionResult({"truck": 1}, "img.jpg")
        moto  = DetectionResult({"motorcycle": 1}, "img.jpg")
        assert truck.weighted_count > moto.weighted_count

    def test_idle_co2_per_minute_empty(self):
        det = DetectionResult({}, "img.jpg")
        assert det.idle_co2_per_minute() == pytest.approx(0.0)

    def test_idle_co2_per_minute_single_class(self):
        det = DetectionResult({"bus": 2}, "img.jpg")
        expected = 2 * IDLE_CO2_G_PER_MIN["bus"]
        assert det.idle_co2_per_minute() == pytest.approx(expected)

    def test_idle_co2_mixed(self):
        det = DetectionResult({"car": 3, "truck": 1}, "img.jpg")
        expected = 3 * IDLE_CO2_G_PER_MIN["car"] + 1 * IDLE_CO2_G_PER_MIN["truck"]
        assert det.idle_co2_per_minute() == pytest.approx(expected)

    def test_annotated_path_stored(self):
        det = DetectionResult({"car": 1}, "img.jpg", annotated_path="out.jpg")
        assert det.annotated_path == "out.jpg"

    def test_repr_does_not_crash(self):
        det = DetectionResult({"car": 2, "bus": 1}, "img.jpg")
        assert "DetectionResult" in repr(det)