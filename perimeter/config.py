"""Load/save/validate config.json."""

import json
import shutil
import time

from .paths import STATE

CONFIG_PATH = STATE / "config.json"

DEFAULT_CONFIG = {
    "version": 3,
    "device": None,
    "profile": "default",
    "confidence_threshold": 0.70,
    "onboarded": False,
    "launch_at_login": False,
    # Keep listening in the background when the window is closed
    "background_mode": True,
    # Per-app overrides: when the frontmost app matches `app` (case-
    # insensitive substring), that zone runs `action` instead of its default.
    # [{"app": "zoom", "zone": "lr", "action": {"type": ..., "target": ...}}]
    "app_overrides": [],
    "onset": {
        "trigger_mult": 6.0,
        "abs_floor": 0.004,
        "crest_min": 4.0,
        "refractory_s": 0.25,
        "keypress_suppress_ms": 120,
    },
    # Holo topology: rear zones are on the display side, front on the
    # trackpad side, one pair each side of the laptop.
    #
    # "layout" is a purely visual rectangle (fractions of the desk-map
    # canvas, 0..1) the user can drag/resize in the UI. It has no bearing
    # on tap detection, which is entirely audio-classification based —
    # it's just how the zone is drawn on the map.
    "zones": [
        {"id": "lr", "name": "Left Rear", "enabled": True,
         "action": {"type": "visual", "target": ""}, "sensitivity": 60,
         "layout": {"x": 0.0, "y": 0.0, "w": 0.34, "h": 0.46}},
        {"id": "rr", "name": "Right Rear", "enabled": True,
         "action": {"type": "visual", "target": ""}, "sensitivity": 60,
         "layout": {"x": 0.66, "y": 0.0, "w": 0.34, "h": 0.46}},
        {"id": "lf", "name": "Left Front", "enabled": True,
         "action": {"type": "visual", "target": ""}, "sensitivity": 60,
         "layout": {"x": 0.0, "y": 0.54, "w": 0.34, "h": 0.46}},
        {"id": "rf", "name": "Right Front", "enabled": True,
         "action": {"type": "visual", "target": ""}, "sensitivity": 60,
         "layout": {"x": 0.66, "y": 0.54, "w": 0.34, "h": 0.46}},
    ],
}

DEFAULT_LAYOUT = {z["id"]: z["layout"] for z in DEFAULT_CONFIG["zones"]}

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


_DEFAULT_AREA = 0.34 * 0.46  # default zone tile area on the map


def zone_threshold(cfg: dict, zone: dict) -> float:
    """sensitivity 0-100 -> confidence threshold (100 -> 0.60, 0 -> 0.95).

    The drawn zone size also feeds in: growing a zone on the desk map
    lowers its confidence threshold (accepts taps that match the zone
    less exactly — e.g. farther from where you calibrated), shrinking it
    raises the bar. The mic can't sense geometry directly, so this is
    the honest physical knob zone area can drive.
    """
    sens = zone.get("sensitivity", 50)
    lay = get_layout(zone)
    area_ratio = (lay["w"] * lay["h"]) / _DEFAULT_AREA
    sens = max(0.0, min(100.0, sens + (area_ratio - 1.0) * 30.0))
    return 0.95 - (sens / 100.0) * 0.35


def resolve_action(cfg: dict, zone: dict):
    """The action this zone should run right now: a per-app override if the
    frontmost application matches, otherwise the zone's default action."""
    overrides = cfg.get("app_overrides") or []
    if overrides:
        from . import frontapp
        front = frontapp.frontmost().lower()
        if front:
            for rule in overrides:
                pat = (rule.get("app") or "").strip().lower()
                if pat and rule.get("zone") == zone["id"] and pat in front:
                    return rule.get("action") or zone.get("action")
    return zone.get("action")


def get_layout(zone: dict) -> dict:
    """Zone map rectangle (fractions 0..1). Falls back to the default
    position for zones saved before layout existed."""
    return zone.get("layout") or DEFAULT_LAYOUT.get(zone["id"], {"x": 0, "y": 0, "w": 0.34, "h": 0.46})
