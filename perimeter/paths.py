"""Where files live, in dev and in a packaged (PyInstaller) build.

Dev (running from the repo): everything stays in the repo directory, as
before — config.json at the root, samples/models/logs under data/.

Frozen (Perimeter.app / Perimeter.exe): bundled resources (the built UI)
are read from the PyInstaller extraction dir, and all *writable* state
moves to the platform's per-user app-data directory, since an installed
app bundle must never write into itself.
"""

import os
import sys
from pathlib import Path

APP_NAME = "Perimeter"

FROZEN = bool(getattr(sys, "frozen", False))

# Repo root in dev; PyInstaller's bundle dir (_MEIPASS / Contents/Frameworks)
# when frozen. Bundled read-only resources resolve against this.
if FROZEN:
    RESOURCES = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    RESOURCES = Path(__file__).resolve().parent.parent


def _user_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        return Path(base) / APP_NAME if base else Path.home() / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / APP_NAME.lower()


# Writable state: config + data. Repo in dev, per-user dir when packaged.
STATE = _user_data_dir() if FROZEN else RESOURCES
DATA = STATE / "data"

if FROZEN:
    STATE.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
