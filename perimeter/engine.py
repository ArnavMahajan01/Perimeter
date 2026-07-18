"""AudioEngine — one mic pipeline, four modes, Holo-style guided capture.

  idle       mic runs, onsets ignored (keeps the noise floor warm)
  calibrate  the UI arms one zone; accepted taps are saved as samples,
             weak/clipped/noisy taps are rejected with retry guidance
  listen     taps are classified and dispatched
  evaluate   the UI arms one zone; every detected tap is scored against it

Events emitted onto the UI queue:
  ("meter", rms, crest)
  ("calib", zone, accepted_count, ok, guidance)   one per detected tap
  ("calib_done", zone, count)
  ("tap", label, conf, fired, why)
  ("eval", expected_zone, predicted, correct, conf, latency_ms)
  ("trained", result_dict)
  ("error", message)
"""

import queue
import threading
import time
import uuid

import numpy as np
from scipy.io import wavfile

from . import SAMPLE_RATE, WINDOW_POST, WINDOW_PRE
from . import config as config_mod
from . import features
from . import model as model_mod
from .capture import Capture
from .daemon import EventLog
from .dispatch import Dispatcher
from .onset import OnsetDetector

PRE = int(WINDOW_PRE * SAMPLE_RATE)
POST = int(WINDOW_POST * SAMPLE_RATE)

CLIP_PEAK = 0.95
WEAK_PEAK = 0.015
NOISY_RATIO = 0.35       # pre-onset RMS vs window RMS → masked by noise


def quality_gate(window: np.ndarray):
    """Returns (ok, guidance). Mirrors Holo's clean-tap gate."""
    peak = float(np.max(np.abs(window)))
    if peak > CLIP_PEAK:
        return False, "Clipped — use a lighter touch."
    if peak < WEAK_PEAK:
        return False, "Too weak — tap more firmly."
    pre = window[:PRE]
    pre_rms = float(np.sqrt(np.mean(pre**2)))
    win_rms = float(np.sqrt(np.mean(window**2)))
    if win_rms > 0 and pre_rms / win_rms > NOISY_RATIO:
        return False, "Masked by noise — wait for quiet."
    return True, ""


class AudioEngine:
    def __init__(self, cfg: dict, events: queue.Queue):
        self.cfg = cfg
        self.events = events
        self.mode = "idle"
        self.profile = cfg.get("profile", "default")

        self.armed_zone = None       # calibrate/evaluate target
        self.calib_target = 0
        self.calib_count = 0

        self.bundle = None           # loaded model bundle
        self.dispatcher = Dispatcher(cfg)
        self.log = EventLog()

        o = cfg["onset"]
        self.detector = OnsetDetector(
            trigger_mult=o["trigger_mult"], abs_floor=o["abs_floor"],
            crest_min=o["crest_min"], refractory_s=o["refractory_s"],
        )

        self.cap = None
        self._running = False

    # -- lifecycle -------------------------------------------------------------

    def start(self):
        if self._running:
            return
        try:
            self.cap = Capture(device=self.cfg.get("device"))
            self.cap.start()
        except Exception as e:
            self.events.put(("error", f"Microphone failed: {e}"))
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        self._install_keyboard_hook()

    def stop(self):
        self._running = False
        if self.cap:
            try:
                self.cap.stop()
            except Exception:
                pass
            self.cap = None

    def _install_keyboard_hook(self):
        try:
            from pynput import keyboard
        except ImportError:
            return
        suppress = int(self.cfg["onset"]["keypress_suppress_ms"] / 1000.0 * SAMPLE_RATE)

        def on_press(_key):
            if self.cap:
                self.detector.suppress_until_frame = self.cap.total_frames + suppress

        try:
            listener = keyboard.Listener(on_press=on_press)
            listener.daemon = True
            listener.start()
        except Exception:
            pass

    # -- mode control -------------------------------------------------------------

    def set_idle(self):
        self.mode = "idle"
        self.armed_zone = None

    def arm_calibration(self, zone_id: str, n_samples: int):
        self.armed_zone = zone_id
        self.calib_target = n_samples
        self.calib_count = model_mod.sample_counts(self.profile).get(zone_id, 0)
        self.mode = "calibrate"

    def arm_evaluation(self, zone_id: str):
        if self.bundle is None:
            try:
                self.bundle = model_mod.load_model(self.profile)
            except FileNotFoundError as e:
                self.events.put(("error", str(e)))
                return False
        self.armed_zone = zone_id
        self.mode = "evaluate"
        return True

    def start_listening(self) -> bool:
        try:
            self.bundle = model_mod.load_model(self.profile)
        except FileNotFoundError as e:
            self.events.put(("error", str(e)))
            return False
        self.mode = "listen"
        return True

    def set_profile(self, profile: str):
        self.profile = profile
        self.bundle = None

    def train_async(self):
        def job():
            result = model_mod.train(self.profile, verbose=False)
            if result["ok"]:
                self.bundle = None  # force reload with the new model
            self.events.put(("trained", result))
        threading.Thread(target=job, daemon=True).start()

    # -- processing --------------------------------------------------------------

    def _loop(self):
        meter_last = 0.0
        while self._running:
            try:
                start_frame, block = self.cap.blocks.get(timeout=2.0)
            except queue.Empty:
                if self._running:
                    self._restart_capture()
                continue
            except AttributeError:
                return

            onset = self.detector.process(block, start_frame)

            now = time.time()
            if now - meter_last > 0.1:
                meter_last = now
                self.events.put(("meter", self.detector.last_rms, self.detector.last_crest))

            if onset is None or self.mode == "idle":
                continue

            window = self._window_at(onset)
            if window is None:
                continue

            if self.mode == "calibrate":
                self._on_calibrate(window)
            elif self.mode == "listen":
                self._on_listen(window)
            elif self.mode == "evaluate":
                self._on_evaluate(window)

    def _window_at(self, onset_frame):
        deadline = time.time() + 0.5
        while self._running and self.cap and self.cap.ring.write_frame < onset_frame + POST:
            if time.time() > deadline:
                return None
            time.sleep(0.004)
        if not self.cap:
            return None
        return self.cap.ring.read_window(onset_frame, PRE, POST)

    def _on_calibrate(self, window):
        zone = self.armed_zone
        ok, guidance = quality_gate(window)
        if zone == "_negative":
            ok, guidance = True, ""  # negatives don't need to be clean taps
        if ok:
            out = model_mod.samples_dir(self.profile) / zone
            out.mkdir(parents=True, exist_ok=True)
            wavfile.write(out / f"{uuid.uuid4()}.wav", SAMPLE_RATE,
                          (window * 32767).astype(np.int16))
            self.calib_count += 1
        self.events.put(("calib", zone, self.calib_count, ok, guidance))
        if self.calib_count >= self.calib_target:
            done_zone, count = zone, self.calib_count
            self.set_idle()
            self.events.put(("calib_done", done_zone, count))

    def _classify(self, window):
        t0 = time.monotonic()
        vec = features.extract(window)
        label, conf, is_ood = model_mod.predict(self.bundle, vec)
        latency_ms = (time.monotonic() - t0) * 1000.0
        return label, conf, is_ood, latency_ms

    def _on_listen(self, window):
        label, conf, is_ood, _ = self._classify(window)

        fired = False
        if is_ood:
            label_out, why = None, "unfamiliar sound (rejected)"
        elif label == "_negative":
            label_out, why = None, "background noise"
        else:
            label_out = label
            zone = config_mod.get_zone(self.cfg, label)
            if zone is None or not zone["enabled"]:
                why = "zone off"
            elif conf < config_mod.zone_threshold(self.cfg, zone):
                why = "ambiguous (rejected)"
            else:
                fired = self.dispatcher.fire(zone)
                why = "fired" if fired else (self.dispatcher.last_error or "not fired")

        self.events.put(("tap", label_out, conf, fired, why))
        self.log.write(zone=label_out or "?", confidence=round(conf, 3), fired=fired,
                       rms=round(self.detector.last_rms, 5),
                       crest=round(self.detector.last_crest, 2))

    def _on_evaluate(self, window):
        expected = self.armed_zone
        label, conf, is_ood, latency_ms = self._classify(window)
        # Holo rule: an armed, detected tap counts even if rejected —
        # rejections during evaluation are incorrect answers.
        predicted = "(rejected)" if is_ood or label == "_negative" else label
        correct = predicted == expected
        self.events.put(("eval", expected, predicted, correct, conf, latency_ms))

    def _restart_capture(self):
        try:
            self.cap.stop()
        except Exception:
            pass
        time.sleep(1.0)
        try:
            self.cap = Capture(device=self.cfg.get("device"))
            self.cap.start()
            self.detector.last_onset_frame = -1e9
            self.detector.suppress_until_frame = -1
        except Exception as e:
            self.events.put(("error", f"Microphone unavailable: {e}"))
            time.sleep(2.0)
