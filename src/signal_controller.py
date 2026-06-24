"""
signal_controller.py
====================
Pressure-score based adaptive traffic signal controller.

Scheduling model
----------------
Each direction (camera) carries a pressure score that grows every cycle it
waits and shrinks when it receives green.  The score combines:

    pressure = (weighted_count + carryover_penalty) × wait_multiplier

where
    weighted_count   = Σ raw_count[class] × VEHICLE_WEIGHT[class]
    carryover_penalty = leftover vehicles × CARRYOVER_WEIGHT  (default 1.5)
    wait_multiplier   = 1 + cycles_since_last_green × WAIT_GROWTH  (default 0.3)

This guarantees:
  • No starvation — wait_multiplier rises every cycle a direction is skipped
  • Minimum safe green time — hard floor of MIN_GREEN_TIME seconds
  • Maximum cap — hard ceiling of MAX_GREEN_TIME seconds
  • Proportional allocation — higher pressure ⟹ more green time AND earlier slot

Emission model
--------------
At the end of every phase we calculate:

    idle_time_saved = fixed_green_time - adaptive_green_time   (capped ≥ 0)

    CO2_saved_g = Σ raw_count[class] × IDLE_CO2_G_PER_MIN[class]
                    × (idle_time_saved / 60)

Cumulative figures are kept in self.emission_totals.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from vehicle_detector import DetectionResult, IDLE_CO2_G_PER_MIN

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable constants  (will later live in config.yaml)
# ---------------------------------------------------------------------------
TOTAL_CYCLE_TIME   = 90    # seconds — fixed cycle budget
MIN_GREEN_TIME     = 15    # seconds — hard safety floor
MAX_GREEN_TIME     = 45    # seconds — hard cap per phase
YELLOW_TIME        = 4     # seconds
ALL_RED_TIME       = 1     # seconds

CARRYOVER_WEIGHT   = 1.5   # leftover vehicles count this much more next cycle
WAIT_GROWTH        = 0.3   # pressure multiplier increment per missed cycle

# Fixed-timing baseline used for efficiency & emission comparison
FIXED_GREEN_TIME   = TOTAL_CYCLE_TIME / 4   # 22.5 s (4 cameras, equal split)

# Approximate vehicles that clear per second of green (saturation flow proxy)
# Tuned per direction later if needed; default 0.5 veh/s ≈ 1 vehicle per 2 s
SATURATION_FLOW    = 0.5   # vehicles / second


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PhaseResult:
    """Outcome of a single green phase for one direction."""
    camera_id:        str
    direction:        str
    green_time:       float
    vehicle_count:    int          # raw total at start of phase
    weighted_count:   float
    carryover_in:     float        # vehicles carried IN from previous cycle
    vehicles_cleared: float        # vehicles that actually left
    carryover_out:    float        # vehicles remaining → next cycle
    pressure_score:   float
    co2_saved_g:      float        # grams CO2 saved vs fixed baseline
    fuel_saved_ml:    float        # mL of fuel saved (proxy: 1 g CO2 ≈ 0.43 mL petrol)
    raw_counts:       dict         = field(default_factory=dict)


@dataclass
class CycleResult:
    """Summary of one complete signal cycle (all directions)."""
    cycle_number:     int
    timestamp:        str
    phases:           list[PhaseResult]
    total_cycle_time: float
    efficiency_pct:   float        # vs fixed baseline
    co2_saved_g:      float        # this cycle
    fuel_saved_ml:    float
    cumulative_co2_saved_g:   float
    cumulative_fuel_saved_ml: float


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
class TrafficSignalController:
    """
    Adaptive traffic signal controller using pressure-score scheduling.

    Parameters
    ----------
    camera_ids  : list of camera/direction identifiers e.g. ["N","S","E","W"]
    """

    def __init__(self, camera_ids: list[str]) -> None:
        if not camera_ids:
            raise ValueError("camera_ids must not be empty")

        self.camera_ids       = camera_ids
        self.num_cameras      = len(camera_ids)
        self.cycle_number     = 0

        # Per-direction state
        self._carryover:           dict[str, float] = {c: 0.0 for c in camera_ids}
        self._cycles_since_green:  dict[str, int]   = {c: 0   for c in camera_ids}

        # Cumulative emission totals
        self.emission_totals = {"co2_g": 0.0, "fuel_ml": 0.0}

        # History for dashboard / logging
        self.history: list[CycleResult] = []

        logger.info(
            "TrafficSignalController ready | cameras=%s | cycle=%ds | green=[%d-%d]s",
            camera_ids, TOTAL_CYCLE_TIME, MIN_GREEN_TIME, MAX_GREEN_TIME,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_cycle(
        self, detections: dict[str, DetectionResult]
    ) -> CycleResult:
        """
        Execute one full signal cycle given fresh detections for every camera.

        Parameters
        ----------
        detections : {camera_id: DetectionResult}  — one entry per camera

        Returns
        -------
        CycleResult with per-phase breakdown and emission savings
        """
        self.cycle_number += 1
        logger.info("=== Cycle %d ===", self.cycle_number)

        # 1. Compute pressure scores
        scores   = self._compute_pressure_scores(detections)

        # 2. Sequence: sort by pressure descending
        sequence = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)

        # 3. Allocate green times proportional to pressure
        green_times = self._allocate_green_times(scores)

        # 4. Run each phase; collect results
        phases: list[PhaseResult] = []
        for cam in sequence:
            phase = self._run_phase(cam, detections[cam], green_times[cam], scores[cam])
            phases.append(phase)
            # Reset wait counter for this camera; increment all others
            self._cycles_since_green[cam] = 0
            for other in self.camera_ids:
                if other != cam:
                    self._cycles_since_green[other] += 1

        # 5. Aggregate cycle-level metrics
        total_time     = sum(
            p.green_time + YELLOW_TIME + ALL_RED_TIME for p in phases
        )
        cycle_co2      = sum(p.co2_saved_g  for p in phases)
        cycle_fuel     = sum(p.fuel_saved_ml for p in phases)
        self.emission_totals["co2_g"]   += cycle_co2
        self.emission_totals["fuel_ml"] += cycle_fuel

        efficiency = self._compute_efficiency(detections, phases)

        result = CycleResult(
            cycle_number=self.cycle_number,
            timestamp=datetime.now().isoformat(),
            phases=phases,
            total_cycle_time=round(total_time, 1),
            efficiency_pct=round(efficiency, 1),
            co2_saved_g=round(cycle_co2, 1),
            fuel_saved_ml=round(cycle_fuel, 1),
            cumulative_co2_saved_g=round(self.emission_totals["co2_g"], 1),
            cumulative_fuel_saved_ml=round(self.emission_totals["fuel_ml"], 1),
        )

        self.history.append(result)
        self._log_cycle(result)
        return result

    def reset_state(self) -> None:
        """Reset per-direction state (carryover, wait counters). Keep history."""
        self._carryover          = {c: 0.0 for c in self.camera_ids}
        self._cycles_since_green = {c: 0   for c in self.camera_ids}
        logger.info("Controller state reset.")

    # ------------------------------------------------------------------
    # Internal — pressure scoring
    # ------------------------------------------------------------------
    def _compute_pressure_scores(
        self, detections: dict[str, DetectionResult]
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for cam in self.camera_ids:
            det = detections.get(cam)
            wc  = det.weighted_count if det else 0.0
            co  = self._carryover[cam]
            wt  = self._cycles_since_green[cam]
            pressure = (wc + co * CARRYOVER_WEIGHT) * (1 + wt * WAIT_GROWTH)
            scores[cam] = round(pressure, 3)
            logger.debug(
                "  %s | weighted=%.1f carryover=%.1f wait=%d → pressure=%.2f",
                cam, wc, co, wt, pressure,
            )
        return scores

    # ------------------------------------------------------------------
    # Internal — green time allocation
    # ------------------------------------------------------------------
    def _allocate_green_times(
        self, scores: dict[str, float]
    ) -> dict[str, float]:
        overhead         = self.num_cameras * (YELLOW_TIME + ALL_RED_TIME)
        available_green  = TOTAL_CYCLE_TIME - overhead
        total_pressure   = sum(scores.values())

        green_times: dict[str, float] = {}

        if total_pressure == 0:
            # No vehicles anywhere — give everyone the minimum
            for cam in self.camera_ids:
                green_times[cam] = float(MIN_GREEN_TIME)
            return green_times

        # Proportional allocation
        for cam, pressure in scores.items():
            raw  = available_green * (pressure / total_pressure)
            clamped = max(MIN_GREEN_TIME, min(MAX_GREEN_TIME, raw))
            green_times[cam] = clamped

        # Normalise so total doesn't exceed budget
        total_allocated = sum(green_times.values())
        if total_allocated > available_green:
            scale = available_green / total_allocated
            for cam in green_times:
                green_times[cam] = max(MIN_GREEN_TIME,
                                       round(green_times[cam] * scale, 1))

        return green_times

    # ------------------------------------------------------------------
    # Internal — run one phase
    # ------------------------------------------------------------------
    def _run_phase(
        self,
        cam: str,
        det: Optional[DetectionResult],
        green_time: float,
        pressure: float,
    ) -> PhaseResult:
        raw_counts     = det.raw_counts     if det else {}
        weighted_count = det.weighted_count if det else 0.0
        total_vehicles = det.total_vehicles if det else 0

        carryover_in   = self._carryover[cam]

        # Vehicles that can clear during this green phase
        clearable      = green_time * SATURATION_FLOW
        demand         = weighted_count + carryover_in
        vehicles_cleared = min(demand, clearable)
        carryover_out  = max(0.0, demand - vehicles_cleared)
        self._carryover[cam] = carryover_out

        # Emission calculation
        # Fixed baseline: FIXED_GREEN_TIME for this direction
        # Adaptive:       green_time (may be more OR less than fixed)
        # Idle time saved = how much less the vehicles idle vs fixed schedule
        idle_time_saved_s = max(0.0, FIXED_GREEN_TIME - green_time)
        # If adaptive gives MORE green → vehicles clear faster → less idling
        # for OTHER directions.  We conservatively count only the reduction
        # in this direction's wait time (vehicles behind the red light).
        co2_idle_per_min  = det.idle_co2_per_minute() if det else 0.0
        co2_saved_g       = co2_idle_per_min * (idle_time_saved_s / 60.0)
        fuel_saved_ml     = co2_saved_g * 0.43   # rough petrol proxy

        logger.info(
            "  Phase %s | green=%.1fs | vehicles=%d | cleared=%.0f | "
            "carryover=%.0f | CO2 saved=%.1fg",
            cam, green_time, total_vehicles, vehicles_cleared,
            carryover_out, co2_saved_g,
        )

        return PhaseResult(
            camera_id=cam,
            direction=cam,
            green_time=round(green_time, 1),
            vehicle_count=total_vehicles,
            weighted_count=round(weighted_count, 1),
            carryover_in=round(carryover_in, 1),
            vehicles_cleared=round(vehicles_cleared, 1),
            carryover_out=round(carryover_out, 1),
            pressure_score=pressure,
            co2_saved_g=round(co2_saved_g, 2),
            fuel_saved_ml=round(fuel_saved_ml, 2),
            raw_counts=raw_counts,
        )

    # ------------------------------------------------------------------
    # Internal — efficiency vs fixed baseline
    # ------------------------------------------------------------------
    def _compute_efficiency(
        self,
        detections: dict[str, DetectionResult],
        phases: list[PhaseResult],
    ) -> float:
        """
        Throughput-based efficiency:
            efficiency = vehicles_cleared_adaptive / vehicles_cleared_fixed
        where fixed assumes every camera gets FIXED_GREEN_TIME seconds.
        """
        fixed_cleared    = sum(
            min((det.total_vehicles if det else 0),
                FIXED_GREEN_TIME * SATURATION_FLOW)
            for det in detections.values()
        )
        adaptive_cleared = sum(p.vehicles_cleared for p in phases)

        if fixed_cleared == 0:
            return 100.0

        return min(100.0, (adaptive_cleared / fixed_cleared) * 100.0)

    # ------------------------------------------------------------------
    # Internal — logging
    # ------------------------------------------------------------------
    def _log_cycle(self, result: CycleResult) -> None:
        logger.info(
            "Cycle %d complete | time=%.1fs | efficiency=%.1f%% | "
            "CO2 saved=%.1fg (total=%.1fg)",
            result.cycle_number,
            result.total_cycle_time,
            result.efficiency_pct,
            result.co2_saved_g,
            result.cumulative_co2_saved_g,
        )


# ---------------------------------------------------------------------------
# Smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    from vehicle_detector import DetectionResult

    controller = TrafficSignalController(["North", "South", "East", "West"])

    mock = {
        "North": DetectionResult({"car": 10, "bus": 2},  "mock"),
        "South": DetectionResult({"car": 3},              "mock"),
        "East":  DetectionResult({"truck": 1, "car": 5}, "mock"),
        "West":  DetectionResult({},                      "mock"),
    }

    for cycle in range(3):
        result = controller.run_cycle(mock)
        print(f"\nCycle {result.cycle_number} | Efficiency {result.efficiency_pct}% | "
              f"CO2 saved {result.co2_saved_g}g")