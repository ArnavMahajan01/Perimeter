"""Perimeter Pro licensing via the Lemon Squeezy License API.

No server of our own: the app talks directly to Lemon Squeezy's public
license endpoints (they require no API secret). A key is activated once
per install (instance), then re-validated in the background with a
14-day offline grace period so a flaky network never locks anyone out.

Config shape (cfg["license"]):
  {"key": "...", "instance_id": "...", "status": "active",
   "last_ok_ts": 1234567890.0}
"""

import json
import time
import urllib.parse
import urllib.request

API_BASE = "https://api.lemonsqueezy.com/v1/licenses/"
OFFLINE_GRACE_S = 14 * 86400
INSTANCE_NAME = "Perimeter Desktop"

# Replace with your Lemon Squeezy checkout link once the store exists.
PRO_URL = "https://perimeter.lemonsqueezy.com/checkout"


def _post(endpoint: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        API_BASE + endpoint, data=data,
        headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def activate(key: str) -> dict:
    """Activate a key for this install. Returns cfg['license'] value on
    success; raises ValueError with a user-readable message on failure."""
    key = (key or "").strip()
    if not key:
        raise ValueError("Enter a license key.")
    try:
        out = _post("activate", {"license_key": key,
                                 "instance_name": INSTANCE_NAME})
    except Exception as e:  # noqa: BLE001 — network/HTTP errors
        raise ValueError(f"Could not reach the license server: {e}") from e
    if not out.get("activated"):
        raise ValueError(out.get("error") or "Invalid license key.")
    return {
        "key": key,
        "instance_id": (out.get("instance") or {}).get("id", ""),
        "status": (out.get("license_key") or {}).get("status", "active"),
        "last_ok_ts": time.time(),
    }


def validate(lic: dict) -> dict:
    """Re-validate a stored license. Returns the updated dict; on network
    failure the stored state is kept (offline grace applies)."""
    if not lic or not lic.get("key"):
        return lic
    try:
        out = _post("validate", {"license_key": lic["key"],
                                 "instance_id": lic.get("instance_id", "")})
    except Exception:
        return lic  # offline — keep last known state
    lic = dict(lic)
    if out.get("valid"):
        lic["status"] = "active"
        lic["last_ok_ts"] = time.time()
    else:
        lic["status"] = (out.get("license_key") or {}).get("status", "invalid")
    return lic


def deactivate(lic: dict) -> None:
    """Best-effort release of this install's activation slot."""
    if not lic or not lic.get("key"):
        return
    try:
        _post("deactivate", {"license_key": lic["key"],
                             "instance_id": lic.get("instance_id", "")})
    except Exception:
        pass


def is_pro(lic: dict) -> bool:
    """Valid license, or one that was valid recently enough (offline grace)."""
    if not lic or not lic.get("key"):
        return False
    if lic.get("status") != "active":
        return False
    return time.time() - float(lic.get("last_ok_ts", 0)) < OFFLINE_GRACE_S


def masked_key(lic: dict) -> str:
    key = (lic or {}).get("key", "")
    return f"…{key[-8:]}" if len(key) >= 8 else key
