import cv2
import os
import logging
from typing import Optional
from ultralytics import YOLO

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vehicle type weights and emission factors
# ---------------------------------------------------------------------------
# Weight drives how much green time a vehicle "deserves" relative to a car.
# Emission factors are grams of CO2 emitted per minute of idling, per class.
# Sources: EPA idling emission estimates (approx. values for scheduling use).
# ---------------------------------------------------------------------------
VEHICLE_WEIGHTS: dict[str, float] = {
    "car":        1.0,
    "motorcycle": 0.5,
    "truck":      2.5,
    "bus":        3.0,
}

IDLE_CO2_G_PER_MIN: dict[str, float] = {
    "car":        28.0,   # ~28 g CO2/min idling
    "motorcycle": 10.0,
    "truck":      75.0,
    "bus":        90.0,
}


class DetectionResult:
    """
    Holds everything the signal controller needs from one camera snapshot.

    Attributes
    ----------
    raw_counts      : vehicles detected per class  {"car": 4, "bus": 1, ...}
    weighted_count  : Σ count[c] * weight[c]  — used for pressure scoring
    total_vehicles  : raw sum across all classes
    image_path      : source image (for traceability)
    annotated_path  : path to YOLO-annotated output image (or None)
    """

    def __init__(
        self,
        raw_counts: dict[str, int],
        image_path: str,
        annotated_path: Optional[str] = None,
    ) -> None:
        self.raw_counts: dict[str, int] = raw_counts
        self.image_path: str = image_path
        self.annotated_path: Optional[str] = annotated_path

        self.total_vehicles: int = sum(raw_counts.values())
        self.weighted_count: float = sum(
            count * VEHICLE_WEIGHTS.get(cls, 1.0)
            for cls, count in raw_counts.items()
        )

    # ------------------------------------------------------------------
    # Emission helpers (used by the emission model layer)
    # ------------------------------------------------------------------
    def idle_co2_per_minute(self) -> float:
        """Total CO2 (grams) emitted per minute if all detected vehicles idle."""
        return sum(
            count * IDLE_CO2_G_PER_MIN.get(cls, 28.0)
            for cls, count in self.raw_counts.items()
        )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"DetectionResult(total={self.total_vehicles}, "
            f"weighted={self.weighted_count:.1f}, counts={self.raw_counts})"
        )


class VehicleDetector:
    """
    Wraps YOLOv8 inference and returns structured DetectionResult objects.

    Parameters
    ----------
    model_path      : path to YOLOv8 weights file
    save_annotated  : if True, saves bounding-box annotated images to
                      output_dir alongside each processed image
    output_dir      : folder for annotated output images
    confidence      : YOLO confidence threshold (0–1)
    """

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        save_annotated: bool = True,
        output_dir: str = "data/annotated",
        confidence: float = 0.4,
    ) -> None:
        logger.info("Initialising VehicleDetector (model=%s)", model_path)
        self.model = YOLO(model_path)
        self.vehicle_classes = list(VEHICLE_WEIGHTS.keys())
        self.save_annotated = save_annotated
        self.output_dir = output_dir
        self.confidence = confidence

        if save_annotated:
            os.makedirs(output_dir, exist_ok=True)

        logger.info("VehicleDetector ready — classes: %s", self.vehicle_classes)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def detect(self, image_path: str) -> DetectionResult:
        """
        Run inference on a single image.

        Returns a DetectionResult with per-class counts, weighted count,
        and (optionally) the path to the annotated output image.

        Parameters
        ----------
        image_path : absolute or relative path to the input image

        Returns
        -------
        DetectionResult  (empty / zero counts on failure)
        """
        if not os.path.exists(image_path):
            logger.error("Image not found: %s", image_path)
            return DetectionResult({}, image_path)

        try:
            results = self.model(image_path, conf=self.confidence, verbose=False)
        except Exception as exc:
            logger.error("YOLO inference failed on %s: %s", image_path, exc)
            return DetectionResult({}, image_path)

        raw_counts: dict[str, int] = {cls: 0 for cls in self.vehicle_classes}

        for result in results:
            for box in result.boxes:
                class_name = self.model.names[int(box.cls[0])]
                if class_name in self.vehicle_classes:
                    raw_counts[class_name] += 1

        # Remove zero-count classes for cleaner output
        raw_counts = {k: v for k, v in raw_counts.items() if v > 0}

        annotated_path = None
        if self.save_annotated and results:
            annotated_path = self._save_annotated(image_path, results[0])

        detection = DetectionResult(raw_counts, image_path, annotated_path)
        logger.debug(
            "Detected %s  weighted=%.1f  path=%s",
            detection.raw_counts,
            detection.weighted_count,
            image_path,
        )
        return detection

    def detect_from_frame(self, frame, camera_id: str = "live") -> DetectionResult:
        """
        Run inference on an in-memory BGR frame (from cv2.VideoCapture).

        Parameters
        ----------
        frame     : numpy array (H, W, 3) in BGR colour order
        camera_id : label used for logging and annotated-file naming

        Returns
        -------
        DetectionResult
        """
        try:
            results = self.model(frame, conf=self.confidence, verbose=False)
        except Exception as exc:
            logger.error("YOLO frame inference failed (%s): %s", camera_id, exc)
            return DetectionResult({}, camera_id)

        raw_counts: dict[str, int] = {cls: 0 for cls in self.vehicle_classes}

        for result in results:
            for box in result.boxes:
                class_name = self.model.names[int(box.cls[0])]
                if class_name in self.vehicle_classes:
                    raw_counts[class_name] += 1

        raw_counts = {k: v for k, v in raw_counts.items() if v > 0}

        annotated_path = None
        if self.save_annotated and results:
            frame_filename = os.path.join(
                self.output_dir, f"{camera_id}_latest.jpg"
            )
            annotated = results[0].plot()
            cv2.imwrite(frame_filename, annotated)
            annotated_path = frame_filename

        return DetectionResult(raw_counts, camera_id, annotated_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _save_annotated(self, image_path: str, result) -> Optional[str]:
        """Save a YOLO-annotated copy of the image; return its path."""
        try:
            basename = os.path.splitext(os.path.basename(image_path))[0]
            out_path = os.path.join(self.output_dir, f"{basename}_annotated.jpg")
            annotated = result.plot()          # numpy BGR array with boxes drawn
            cv2.imwrite(out_path, annotated)
            logger.debug("Annotated image saved: %s", out_path)
            return out_path
        except Exception as exc:
            logger.warning("Could not save annotated image: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    detector = VehicleDetector()
    logger.info("VehicleDetector initialised successfully.")