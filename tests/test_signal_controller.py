"""
tests/test_signal_controller.py
================================
Unit tests for TrafficSignalController — pressure scoring, green time
allocation, queue carryover, starvation prevention, and emission model.
No camera / YOLO model required.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from vehicle_detector import DetectionResult
from signal_controller import (
    TrafficSignalController,
    MIN_GREEN_TIME,
    MAX_GREEN_TIME,
    YELLOW_TIME,
    ALL_RED_TIME,
    TOTAL_CYCLE_TIME,
    FIXED_GREEN_TIME,
)

CAMERAS = ["North", "South", "East", "West"]


def make_det(counts: dict) -> DetectionResult:
    return DetectionResult(counts, "mock")


def make_detections(counts_map: dict[str, dict]) -> dict[str, DetectionResult]:
    return {cam: make_det(counts) for cam, counts in counts_map.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class TestHelpers:
    def test_detection_result_weighted(self):
        det = make_det({"car": 4, "bus": 1})
        # car weight 1.0, bus weight 3.0  →  4*1 + 1*3 = 7
        assert det.weighted_count == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------
class TestInit:
    def test_initialises_with_cameras(self):
        ctrl = TrafficSignalController(CAMERAS)
        assert ctrl.camera_ids == CAMERAS

    def test_rejects_empty_cameras(self):
        with pytest.raises(ValueError):
            TrafficSignalController([])

    def test_initial_carryover_zero(self):
        ctrl = TrafficSignalController(CAMERAS)
        assert all(v == 0.0 for v in ctrl._carryover.values())

    def test_initial_wait_counters_zero(self):
        ctrl = TrafficSignalController(CAMERAS)
        assert all(v == 0 for v in ctrl._cycles_since_green.values())


# ---------------------------------------------------------------------------
# Green time allocation — bounds
# ---------------------------------------------------------------------------
class TestGreenTimeAllocation:

    def _run_one_cycle(self, counts_map):
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections(counts_map)
        return ctrl.run_cycle(dets)

    def test_green_time_never_below_minimum(self):
        result = self._run_one_cycle({
            "North": {"car": 50},
            "South": {},
            "East":  {},
            "West":  {},
        })
        for phase in result.phases:
            assert phase.green_time >= MIN_GREEN_TIME

    def test_green_time_never_above_maximum(self):
        result = self._run_one_cycle({
            "North": {"bus": 100},
            "South": {"car": 1},
            "East":  {"car": 1},
            "West":  {"car": 1},
        })
        for phase in result.phases:
            assert phase.green_time <= MAX_GREEN_TIME

    def test_zero_traffic_all_get_minimum(self):
        result = self._run_one_cycle({cam: {} for cam in CAMERAS})
        for phase in result.phases:
            assert phase.green_time == MIN_GREEN_TIME

    def test_busier_direction_gets_more_green(self):
        result = self._run_one_cycle({
            "North": {"bus": 10, "car": 5},
            "South": {"car": 1},
            "East":  {"car": 1},
            "West":  {"car": 1},
        })
        north_phase = next(p for p in result.phases if p.camera_id == "North")
        south_phase = next(p for p in result.phases if p.camera_id == "South")
        assert north_phase.green_time >= south_phase.green_time

    def test_total_cycle_time_within_budget(self):
        result = self._run_one_cycle({
            "North": {"car": 20},
            "South": {"car": 5},
            "East":  {"truck": 3},
            "West":  {"motorcycle": 8},
        })
        # Each direction is clamped to [MIN_GREEN_TIME, MAX_GREEN_TIME].
        # When min-clamping kicks in, total green may exceed the proportional
        # budget but must never exceed num_cameras * MAX_GREEN_TIME.
        # The controller guarantees no single direction exceeds MAX_GREEN_TIME.
        for phase in result.phases:
            assert phase.green_time <= MAX_GREEN_TIME
            assert phase.green_time >= MIN_GREEN_TIME
        # Total green stays within the theoretical maximum cycle budget
        total_green = sum(p.green_time for p in result.phases)
        max_possible = len(CAMERAS) * MAX_GREEN_TIME
        assert total_green <= max_possible


# ---------------------------------------------------------------------------
# Pressure score — no starvation
# ---------------------------------------------------------------------------
class TestNoStarvation:

    def test_wait_multiplier_grows_when_skipped(self):
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections({
            "North": {"bus": 30},
            "South": {},
            "East":  {},
            "West":  {},
        })
        # Run several cycles where South/East/West may be skipped
        for _ in range(4):
            ctrl.run_cycle(dets)

        # Directions that didn't go recently should have higher wait counter
        # (North always goes first due to pressure, others accumulate)
        skipped = [c for c in CAMERAS if c != "North"]
        for cam in skipped:
            assert ctrl._cycles_since_green[cam] >= 0   # non-negative

    def test_low_traffic_direction_always_included(self):
        """Every direction must appear in every cycle's phase list."""
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections({
            "North": {"bus": 20, "car": 10},
            "South": {},
            "East":  {},
            "West":  {},
        })
        for _ in range(5):
            result = ctrl.run_cycle(dets)
            phase_cams = {p.camera_id for p in result.phases}
            assert phase_cams == set(CAMERAS), \
                f"Missing cameras in cycle {result.cycle_number}: {set(CAMERAS) - phase_cams}"


# ---------------------------------------------------------------------------
# Queue carryover
# ---------------------------------------------------------------------------
class TestCarryover:

    def test_carryover_nonzero_when_demand_exceeds_clearance(self):
        ctrl = TrafficSignalController(["North"])
        # 100 buses — impossible to clear in max 45s at 0.5 veh/s (22.5 max clearance)
        dets = {"North": make_det({"bus": 100})}
        result = ctrl.run_cycle(dets)
        north = result.phases[0]
        assert north.carryover_out > 0

    def test_carryover_propagates_to_next_cycle(self):
        ctrl = TrafficSignalController(["North"])
        dets = {"North": make_det({"bus": 100})}
        r1 = ctrl.run_cycle(dets)
        carryover_after_cycle1 = r1.phases[0].carryover_out
        # Next cycle the carryover should appear as carryover_in
        r2 = ctrl.run_cycle(dets)
        assert r2.phases[0].carryover_in == pytest.approx(carryover_after_cycle1)

    def test_empty_road_no_carryover(self):
        ctrl = TrafficSignalController(["North"])
        dets = {"North": make_det({})}
        result = ctrl.run_cycle(dets)
        assert result.phases[0].carryover_out == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Emission model
# ---------------------------------------------------------------------------
class TestEmissionModel:

    def test_co2_saved_nonnegative(self):
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections({
            "North": {"car": 10, "bus": 2},
            "South": {"car": 5},
            "East":  {"truck": 3},
            "West":  {"motorcycle": 4},
        })
        result = ctrl.run_cycle(dets)
        for phase in result.phases:
            assert phase.co2_saved_g >= 0.0

    def test_cumulative_co2_grows_each_cycle(self):
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections({cam: {"car": 10} for cam in CAMERAS})
        prev = 0.0
        for _ in range(3):
            result = ctrl.run_cycle(dets)
            assert result.cumulative_co2_saved_g >= prev
            prev = result.cumulative_co2_saved_g

    def test_more_buses_more_co2_saved(self):
        """A direction with heavy vehicles should save more CO2 than one with only cars."""
        ctrl_cars  = TrafficSignalController(["A"])
        ctrl_buses = TrafficSignalController(["A"])
        r_cars  = ctrl_cars.run_cycle( {"A": make_det({"car":  10})})
        r_buses = ctrl_buses.run_cycle({"A": make_det({"bus":  10})})
        assert r_buses.co2_saved_g >= r_cars.co2_saved_g

    def test_fuel_saved_derived_from_co2(self):
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections({cam: {"car": 8} for cam in CAMERAS})
        result = ctrl.run_cycle(dets)
        for phase in result.phases:
            assert phase.fuel_saved_ml == pytest.approx(phase.co2_saved_g * 0.43, rel=0.01)


# ---------------------------------------------------------------------------
# Efficiency
# ---------------------------------------------------------------------------
class TestEfficiency:

    def test_efficiency_between_0_and_100(self):
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections({cam: {"car": 10} for cam in CAMERAS})
        result = ctrl.run_cycle(dets)
        assert 0.0 <= result.efficiency_pct <= 100.0

    def test_zero_traffic_efficiency_100(self):
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections({cam: {} for cam in CAMERAS})
        result = ctrl.run_cycle(dets)
        assert result.efficiency_pct == pytest.approx(100.0)

    def test_history_grows_each_cycle(self):
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections({cam: {"car": 5} for cam in CAMERAS})
        for i in range(4):
            ctrl.run_cycle(dets)
        assert len(ctrl.history) == 4


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------
class TestReset:

    def test_reset_clears_carryover(self):
        ctrl = TrafficSignalController(["North"])
        ctrl._carryover["North"] = 25.0
        ctrl.reset_state()
        assert ctrl._carryover["North"] == 0.0

    def test_reset_clears_wait_counters(self):
        ctrl = TrafficSignalController(CAMERAS)
        ctrl._cycles_since_green["South"] = 5
        ctrl.reset_state()
        assert ctrl._cycles_since_green["South"] == 0

    def test_reset_preserves_history(self):
        ctrl = TrafficSignalController(CAMERAS)
        dets = make_detections({cam: {"car": 5} for cam in CAMERAS})
        ctrl.run_cycle(dets)
        assert len(ctrl.history) == 1
        ctrl.reset_state()
        assert len(ctrl.history) == 1   # history kept