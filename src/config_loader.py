"""
config_loader.py
================
Loads config.yaml once at startup and exposes typed constants
to every module.  All other modules should import from here
instead of hardcoding values.

Usage
-----
    from config_loader import CFG, SIGNAL, WEIGHTS, EMISSION

    green_floor = SIGNAL["min_green_time"]   # 15
    bus_weight  = WEIGHTS["bus"]             # 3.0
"""

import logging
import os
from functools import lru_cache
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config.yaml"
)


@lru_cache(maxsize=1)
def load_config(path: str = _DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load and cache config.yaml.  Raises FileNotFoundError if missing."""
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"config.yaml not found at {abs_path}")
    with open(abs_path, "r") as f:
        cfg = yaml.safe_load(f)
    logger.info("Config loaded from %s", abs_path)
    return cfg


# ---------------------------------------------------------------------------
# Convenience accessors — import these directly in other modules
# ---------------------------------------------------------------------------
def _cfg() -> dict:
    return load_config()

@property
def CFG()      -> dict: return _cfg()                         # full config
def SIGNAL()   -> dict: return _cfg()["signal"]
def SCHEDULER()-> dict: return _cfg()["scheduler"]
def WEIGHTS()  -> dict: return _cfg()["vehicle_weights"]
def EMISSION() -> dict: return _cfg()["emission"]
def FLOW()     -> dict: return _cfg()["flow"]
def DETECTION()-> dict: return _cfg()["detection"]
def PATHS()    -> dict: return _cfg()["paths"]
def DASHBOARD()-> dict: return _cfg()["dashboard"]


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(load_config(), indent=2))