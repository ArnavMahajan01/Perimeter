# PyInstaller spec — build the standalone desktop app.
#
#   cd web && npm run build && cd ..          # build the UI first
#   .venv/bin/pyinstaller Perimeter.spec      # then the app
#
# Output: dist/Perimeter.app (macOS) / dist/Perimeter (Linux, Windows).

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "web" / "dist"), "web/dist"),  # built React UI
    (str(ROOT / "ui"), "ui"),                  # legacy fallback UI
]

a = Analysis(
    ["app_entry.py"],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=[
        "sklearn.pipeline",
        "sklearn.preprocessing",
        "sklearn.linear_model",
        "sklearn.neighbors",
    ],
    excludes=["tkinter", "matplotlib", "PIL", "pandas", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="Perimeter",
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="Perimeter",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Perimeter.app",
        bundle_identifier="com.arnav.perimeter",
        info_plist={
            "NSMicrophoneUsageDescription":
                "Perimeter listens for desk taps through the microphone. "
                "Audio is analyzed locally and never stored or transmitted.",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
