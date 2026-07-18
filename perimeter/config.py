"""Load/save/validate config.json."""

import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

DEFAULT_CONFIG = {
    "version": 3,
    "device": None,
    "profile": "default",
    "confidence_threshold": 0.70,
    "onset": {
        "trigger_mult": 6.0,
        "abs_floor": 0.004,
        "crest_min": 4.0,
        "refractory_s": 0.25,
        "keypress_suppress_ms": 120,
    },
    # Holo topology: rear zones are on the display side, front on the
    # trackpad side, one pair each side of the laptop.
    "zones": [
        {"id": "lr", "name": "Left Rear", "enabled": True,
         "action": {"type": "visual", "target": ""}, "sensitivity": 60},
        {"id": "rr", "name": "Right Rear", "enabled": True,
         "action": {"type": "visual", "target": ""}, "sensitivity": 60},
        {"id": "lf", "name": "Left Front", "enabled": True,
         "action": {"type": "visual", "target": ""}, "sensitivity": 60},
        {"id": "rf", "name": "Right Front", "enabled": True,
         "action": {"type": "visual", "target": ""}, "sensitivity": 60},
    ],
}

_REQUIRED_KEYS = {"version", "confidence_threshold", "onset", "zones"}
_ZONE_KEYS = {"id", "name", "enabled", "action", "sensitivity"}


def _valid(cfg) -> bool:
    if not isinstance(cfg, dict) or not _REQUIRED_KEYS.issubset(cfg):
        return False
    if cfg.get("version") != DEFAULT_CONFIG["version"]:
        return False
    if not isinstance(cfg["zones"], list):
        return False
    return all(isinstance(z, dict) and _ZONE_KEYS.issubset(z) for z in cfg["zones"])


def load() -> dict:
    if not CONFIG_PATH.exists():
        save(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError:
        cfg = None
    if cfg is None or not _valid(cfg):
        backup = CONFIG_PATH.with_suffix(f".bad-{int(time.time())}.json")
        shutil.copy(CONFIG_PATH, backup)
        save(DEFAULT_CONFIG)
        print(f"config.json invalid — backed up to {backup.name}, wrote defaults")
        return json.loads(json.dumps(DEFAULT_CONFIG))
    return cfg


def save(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")


def get_zone(cfg: dict, zone_id: str):
    for z in cfg["zones"]:
        if z["id"] == zone_id:
            return z
    return None


def zone_threshold(cfg: dict, zone: dict) -> float:
    """sensitivity 0-100 -> confidence threshold (100 -> 0.60, 0 -> 0.95)."""
    sens = zone.get("sensitivity", 50)
    return 0.95 - (sens / 100.0) * 0.35
