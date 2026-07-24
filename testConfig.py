"""
tests/test_config.py
====================
Smoke tests — verify config.yaml loads and has all required keys.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from config_loader import load_config

@pytest.fixture(autouse=True)
def clear_cache():
    load_config.cache_clear()
    yield
    load_config.cache_clear()

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")

def test_config_loads():
    cfg = load_config(CONFIG_PATH)
    assert isinstance(cfg, dict)

def test_required_top_level_keys():
    cfg = load_config(CONFIG_PATH)
    for key in ["signal", "scheduler", "vehicle_weights", "emission",
                 "flow", "detection", "paths", "dashboard", "logging"]:
        assert key in cfg, f"Missing top-level key: {key}"

def test_signal_values_sane():
    cfg = load_config(CONFIG_PATH)
    s = cfg["signal"]
    assert s["min_green_time"] < s["max_green_time"]
    assert s["total_cycle_time"] > 0
    assert s["yellow_time"] > 0

def test_vehicle_weights_positive():
    cfg = load_config(CONFIG_PATH)
    for cls, w in cfg["vehicle_weights"].items():
        assert w > 0, f"Weight for {cls} must be positive"

def test_emission_factors_positive():
    cfg = load_config(CONFIG_PATH)
    for cls, v in cfg["emission"]["idle_co2_g_per_min"].items():
        assert v > 0, f"Emission factor for {cls} must be positive"

def test_bus_heavier_than_car():
    cfg = load_config(CONFIG_PATH)
    assert cfg["vehicle_weights"]["bus"] > cfg["vehicle_weights"]["car"]

def test_missing_config_raises():
    load_config.cache_clear()
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.yaml")