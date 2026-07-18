"""Main loop: capture -> onset -> classify -> dispatch, plus event logging."""

import json
import queue
import threading
import time
from pathlib import Path

from . import SAMPLE_RATE, WINDOW_POST, WINDOW_PRE
from . import config as config_mod
from . import features
from . import model as model_mod
from .capture import Capture
from .dispatch import Dispatcher
from .onset import OnsetDetector

ROOT = Path(__file__).resolve().parent.parent
EVENTS_LOG = ROOT / "data" / "events.log"
LOG_MAX_BYTES = 10 * 1024 * 1024


class EventLog:
    def __init__(self, path: Path = EVENTS_LOG):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, **fields) -> None:
        fields.setdefault("ts", time.time())
        line = json.dumps(fields) + "\n"
        with self._lock:
            if self.path.exists() and self.path.stat().st_size > LOG_MAX_BYTES:
                self.path.rename(self.path.with_suffix(".log.1"))
            with open(self.path, "a") as f:
                f.write(line)


class _CaptureHolder:
    """Indirection so the keyboard hook and worker always see the current
    Capture instance, even after a stall-recovery restart."""

    def __init__(self, cap: Capture):
        self.cap = cap


def _install_keyboard_hook(detector: OnsetDetector, holder: "_CaptureHolder", suppress_ms: int):
    """Suppress onsets briefly after any keypress. Requires pynput; degrades
    gracefully (macOS also needs Input Monitoring permission)."""
    try:
        from pynput import keyboard
    except ImportError:
        print("pynput not installed — keyboard suppression disabled "
              "(typing may cause false onsets; the _negative class is the backstop)")
        return None

    suppress_frames = int(suppress_ms / 1000.0 * SAMPLE_RATE)

    def on_press(_key):
        detector.suppress_until_frame = holder.cap.total_frames + suppress_frames

    try:
        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
        return listener
    except Exception as e:
        print(f"keyboard hook failed ({e}) — suppression disabled")
        return None


def run(dispatch_enabled: bool = True) -> None:
    cfg = config_mod.load()
    try:
        clf = model_mod.load_model(cfg.get("profile", "default"))
    except FileNotFoundError as e:
        raise SystemExit(f"{e} Set up zones in the app first: python cli.py app")
    dispatcher = Dispatcher(cfg, enabled=dispatch_enabled)
    log = EventLog()

    onset_cfg = cfg["onset"]
    detector = OnsetDetector(
        trigger_mult=onset_cfg["trigger_mult"],
        abs_floor=onset_cfg["abs_floor"],
        crest_min=onset_cfg["crest_min"],
        refractory_s=onset_cfg["refractory_s"],
    )

    holder = _CaptureHolder(Capture(device=cfg.get("device")))
    _install_keyboard_hook(detector, holder, onset_cfg["keypress_suppress_ms"])

    pre = int(WINDOW_PRE * SAMPLE_RATE)
    post = int(WINDOW_POST * SAMPLE_RATE)
    work: queue.Queue = queue.Queue()

    def worker():
        while True:
            item = work.get()
            if item is None:
                return
            onset_frame, rms, crest = item
            # Wait until the ring buffer holds the full post-onset window.
            ring = holder.cap.ring
            deadline = time.time() + 1.0
            while ring.write_frame < onset_frame + post:
                if time.time() > deadline:
                    break
                time.sleep(0.005)
            window = ring.read_window(onset_frame, pre, post)
            if window is None:
                continue

            vec = features.extract(window)
            label, conf, is_ood = model_mod.predict(clf, vec)

            fired = False
            reason = ""
            if is_ood:
                reason = "out-of-distribution"
            elif label == "_negative":
                reason = "negative"
            else:
                zone = config_mod.get_zone(cfg, label)
                if zone is None:
                    reason = "unknown zone"
                elif not zone["enabled"]:
                    reason = "zone disabled"
                elif conf < config_mod.zone_threshold(cfg, zone):
                    reason = f"low confidence (< {config_mod.zone_threshold(cfg, zone):.2f})"
                else:
                    fired = dispatcher.fire(zone)
                    reason = "fired" if fired else "cooldown/no action"

            print(f"[tap] zone={label} conf={conf:.2f} -> {reason}")
            log.write(zone=label, confidence=round(conf, 3), fired=fired,
                      rms=round(rms, 5), crest=round(crest, 2))

    threading.Thread(target=worker, daemon=True).start()

    mode = "run" if dispatch_enabled else "test (dispatch disabled)"
    print(f"Perimeter daemon [{mode}] — listening. Ctrl-C to stop.")
    holder.cap.start()
    try:
        while True:
            try:
                start_frame, block = holder.cap.blocks.get(timeout=2.0)
            except queue.Empty:
                # Stream stalled (mic disconnect?) — restart capture.
                print("audio stream stalled — restarting capture")
                try:
                    holder.cap.stop()
                except Exception:
                    pass
                time.sleep(1.0)
                holder.cap = Capture(device=cfg.get("device"))
                holder.cap.start()
                detector.last_onset_frame = -1e9
                detector.suppress_until_frame = -1
                continue
            onset_frame = detector.process(block, start_frame)
            if onset_frame is not None:
                work.put((onset_frame, detector.last_rms, detector.last_crest))
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        work.put(None)
        holder.cap.stop()
