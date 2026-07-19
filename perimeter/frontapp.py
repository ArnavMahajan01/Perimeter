"""Best-effort frontmost-application name, cached.

Used to pick per-app action overrides at dispatch time. Failure means an
empty string, never an exception — overrides simply don't match then.
"""

import subprocess
import sys
import time

_TTL = 0.8  # seconds; polled ~8x/s from the UI, so cache hard
_cache = (0.0, "")


def frontmost() -> str:
    global _cache
    now = time.time()
    if now - _cache[0] < _TTL:
        return _cache[1]

    name = ""
    try:
        if sys.platform == "darwin":
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app:
                name = str(app.localizedName() or "")
        elif sys.platform.startswith("win"):
            import ctypes
            import ctypes.wintypes as wt
            u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
            hwnd = u32.GetForegroundWindow()
            pid = wt.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h = k32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
            if h:
                buf = ctypes.create_unicode_buffer(260)
                size = wt.DWORD(260)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = buf.value.rsplit("\\", 1)[-1]
                    if name.lower().endswith(".exe"):
                        name = name[:-4]
                k32.CloseHandle(h)
        else:
            out = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=0.5)
            name = out.stdout.strip()
    except Exception:
        name = ""

    _cache = (now, name)
    return name
