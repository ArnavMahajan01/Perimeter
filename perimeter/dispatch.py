"""Zone label -> OS action, cross-platform (macOS / Linux / Windows).

Action types (Holo-style):
  visual      no side effect — the UI highlight is the action
  sound       play a short system sound
  copy        copy configured text to the clipboard
  speak       speak configured text with the local synthesizer
  url         open an http(s) address
  app         open or focus an application
  file        open a file or folder
  hotkey      press a key ('playpause', key code, or platform expression)
  shell       run a shell command
  screenshot  full-screen capture to clipboard

Never let a bad action kill the engine.
"""

import shutil
import subprocess
import sys
import time

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
IS_LINUX = not IS_MAC and not IS_WIN

ACTION_TYPES = ["visual", "sound", "copy", "speak", "url", "app",
                "file", "hotkey", "shell", "screenshot"]

# Which action types need a target string
NEEDS_TARGET = {"copy", "speak", "url", "app", "file", "hotkey", "shell"}


class Dispatcher:
    COOLDOWN_S = 1.0

    def __init__(self, cfg: dict, enabled: bool = True):
        self.cfg = cfg
        self.enabled = enabled
        self.last_fired: dict[str, float] = {}
        self.last_error = None  # reason the most recent fire() returned False

    def fire(self, zone: dict) -> bool:
        """Returns True if the action executed (visual counts as executed).
        On failure, self.last_error explains why."""
        self.last_error = None
        action = zone.get("action")
        if not action:
            self.last_error = "no action assigned"
            return False
        zone_id = zone["id"]
        now = time.time()
        if now - self.last_fired.get(zone_id, 0.0) < self.COOLDOWN_S:
            self.last_error = "cooldown"
            return False
        self.last_fired[zone_id] = now
        if not self.enabled:
            self.last_error = "dispatch disabled"
            return False
        try:
            self.execute(action)
            return True
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)
            print(f"[dispatch error] zone {zone_id}: {e}", file=sys.stderr)
            return False

    def execute(self, action: dict) -> None:
        """Run an action spec immediately (also used by the UI Test button)."""
        kind = action["type"]
        target = (action.get("target") or "").strip()
        if kind in NEEDS_TARGET and not target:
            raise ValueError(f"action '{kind}' has no target configured")

        if kind == "visual":
            return
        if kind == "sound":
            self._sound()
        elif kind == "copy":
            self._copy(target)
        elif kind == "speak":
            self._speak(target)
        elif kind in ("url", "file"):
            self._open(target)
        elif kind == "app":
            self._app(target)
        elif kind == "hotkey":
            self._hotkey(target)
        elif kind == "shell":
            subprocess.Popen(target, shell=True)
        elif kind == "screenshot":
            self._screenshot()
        else:
            raise ValueError(f"unknown action type: {kind}")

    # -- platform helpers ------------------------------------------------------

    @staticmethod
    def _sound() -> None:
        if IS_MAC:
            subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        elif IS_LINUX:
            for player, arg in (("paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"),
                                ("aplay", "/usr/share/sounds/alsa/Front_Center.wav")):
                if shutil.which(player):
                    subprocess.Popen([player, arg])
                    return
            print("\a", end="", flush=True)
        else:
            subprocess.Popen(
                ["powershell", "-Command", "[System.Media.SystemSounds]::Asterisk.Play()"])

    @staticmethod
    def _copy(text: str) -> None:
        if IS_MAC:
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        elif IS_LINUX:
            tool = shutil.which("xclip") or shutil.which("xsel") or shutil.which("wl-copy")
            if not tool:
                raise RuntimeError("install xclip, xsel or wl-clipboard for copy actions")
            args = {"xclip": ["xclip", "-selection", "clipboard"],
                    "xsel": ["xsel", "--clipboard", "--input"],
                    "wl-copy": ["wl-copy"]}[tool.rsplit("/", 1)[-1]]
            p = subprocess.Popen(args, stdin=subprocess.PIPE)
        else:
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
        p.communicate(text.encode())

    @staticmethod
    def _speak(text: str) -> None:
        if IS_MAC:
            subprocess.Popen(["say", text])
        elif IS_LINUX:
            for tool in ("spd-say", "espeak", "espeak-ng"):
                if shutil.which(tool):
                    subprocess.Popen([tool, text])
                    return
            raise RuntimeError("install espeak or speech-dispatcher for speak actions")
        else:
            ps = ("Add-Type -AssemblyName System.Speech; "
                  "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                  f".Speak('{text.replace(chr(39), '')}')")
            subprocess.Popen(["powershell", "-Command", ps])

    @staticmethod
    def _open(target: str) -> None:
        if IS_MAC:
            subprocess.Popen(["open", target])
        elif IS_LINUX:
            subprocess.Popen(["xdg-open", target])
        else:
            subprocess.Popen(f'start "" "{target}"', shell=True)

    @staticmethod
    def _app(target: str) -> None:
        if IS_MAC:
            subprocess.Popen(["open", "-a", target])
        elif IS_LINUX:
            if shutil.which("gtk-launch"):
                subprocess.Popen(["gtk-launch", target])
            else:
                subprocess.Popen([target])
        else:
            subprocess.Popen(f'start "" "{target}"', shell=True)

    @staticmethod
    def _hotkey(target: str) -> None:
        if IS_MAC:
            if target == "playpause":
                script = 'tell application "Music" to playpause'
            elif target.isdigit():
                script = f'tell application "System Events" to key code {target}'
            else:
                script = f'tell application "System Events" to {target}'
            subprocess.Popen(["osascript", "-e", script])
        elif IS_LINUX:
            if not shutil.which("xdotool"):
                raise RuntimeError("install xdotool for hotkey actions")
            key = "XF86AudioPlay" if target == "playpause" else target
            subprocess.Popen(["xdotool", "key", key])
        else:
            ps = f'(New-Object -ComObject WScript.Shell).SendKeys("{target}")'
            subprocess.Popen(["powershell", "-Command", ps])

    @staticmethod
    def _screenshot() -> None:
        if IS_MAC:
            subprocess.Popen(["screencapture", "-c"])
        elif IS_LINUX:
            for cmd in (["gnome-screenshot", "-c"],
                        ["spectacle", "-b", "-c"]):
                if shutil.which(cmd[0]):
                    subprocess.Popen(cmd)
                    return
            raise RuntimeError("install gnome-screenshot or spectacle for screenshots")
        else:
            ps = ("Add-Type -AssemblyName System.Windows.Forms; "
                  "[System.Windows.Forms.SendKeys]::SendWait('{PRTSC}')")
            subprocess.Popen(["powershell", "-Command", ps])
