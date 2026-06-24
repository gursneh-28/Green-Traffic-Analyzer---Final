"""
logger_setup.py
===============
Call setup_logging() once at the top of any entry-point script
(signal_simulation.py, live_simulation.py, dashboard.py).

All modules that do `import logging; logger = logging.getLogger(__name__)`
will automatically inherit the handlers configured here.

Log levels
----------
  DEBUG   — per-frame YOLO output, pressure score details
  INFO    — cycle summaries, phase transitions, startup messages
  WARNING — missing images, config fallbacks
  ERROR   — detection failures, file I/O errors
"""

import logging
import os
import sys
from datetime import datetime


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    """
    Configure root logger with:
      - Coloured stream handler  → stdout
      - Rotating file handler   → logs/traffic_analyzer_<date>.log

    Parameters
    ----------
    level   : log level string ("DEBUG" / "INFO" / "WARNING" / "ERROR")
    log_dir : directory for log files (created if missing)
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(
        log_dir,
        f"traffic_analyzer_{datetime.now().strftime('%Y%m%d')}.log",
    )

    # ── Formatters ──────────────────────────────────────────
    file_fmt   = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_fmt = _ColouredFormatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Handlers ────────────────────────────────────────────
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(stream_fmt)
    stream_handler.setLevel(numeric_level)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(file_fmt)
    file_handler.setLevel(numeric_level)

    # ── Root logger ─────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(stream_handler)
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("engineio").setLevel(logging.WARNING)
    logging.getLogger("socketio").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised | level=%s | file=%s", level, log_file
    )


# ---------------------------------------------------------------------------
# Coloured stream formatter (no extra deps — uses ANSI codes)
# ---------------------------------------------------------------------------
class _ColouredFormatter(logging.Formatter):
    _COLOURS = {
        logging.DEBUG:    "\033[36m",    # cyan
        logging.INFO:     "\033[32m",    # green
        logging.WARNING:  "\033[33m",    # yellow
        logging.ERROR:    "\033[31m",    # red
        logging.CRITICAL: "\033[35m",    # magenta
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self._COLOURS.get(record.levelno, "")
        record.levelname = f"{colour}{record.levelname}{self._RESET}"
        return super().format(record)