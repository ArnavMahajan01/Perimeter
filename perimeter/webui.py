"""Native window UI (pywebview) — shadcn-styled HTML front end.

The Controller owns all app flow (calibration sequencing, evaluation
sessions, listening state) and translates engine events into a UI state
snapshot. The JS side polls `Api.poll()` ~8x/s and just renders.
"""

import queue
import time
from collections import deque
from pathlib import Path

from . import config as config_mod
from . import model as model_mod
from .dispatch import NEEDS_TARGET, Dispatcher
from .engine import AudioEngine
from .evaluation import TAPS_PER_ZONE, EvaluationSession, latest_report

UI_HTML = Path(__file__).resolve().parent.parent / "ui" / "index.html"

CALIB_TAPS = 10
NEG_TAPS = 20
ZONE_ORDER = ["lr", "rr", "lf", "rf"]
ARM_DELAY_S = 0.9


class Controller:
    def __init__(self):
        self.cfg = config_mod.load()
        self.events = queue.Queue()
        self.engine = AudioEngine(self.cfg, self.events)
        self.dispatcher = Dispatcher(self.cfg)  # Test buttons

        self.listening = False
        self.calibrating = False
        self.calib_queue = []
        self.eval_session = None
        self.eval_queue = []

        self.status = ("Calibrate, then start listening.", "muted")
        self.calib_live = {}       # zid -> {"text","tone"} while calibrating
        self.eval_live = {}        # zid -> {"text","tone"} while evaluating
        self.neg_live = None
        self.train_msg = None      # {"text","tone"}
        self.meter = 0.0
        self.logs = deque(maxlen=80)
        self.flashes = []          # [{"zone","tone"}] since last poll

        self._arm_at = None
        self._arm_zone = None
        self._arm_kind = None      # "calib" | "eval"

        self.engine.start()

    # ---------------------------------------------------------------- pump --

    def pump(self):
        now = time.time()
        if self._arm_at and now >= self._arm_at:
            zone, kind = self._arm_zone, self._arm_kind
            self._arm_at = self._arm_zone = self._arm_kind = None
            if kind == "calib" and self.calibrating:
                self.engine.arm_calibration(zone, NEG_TAPS if zone == "_negative" else CALIB_TAPS)
            elif kind == "eval" and self.eval_session:
                if not self.engine.arm_evaluation(zone):
                    self._eval_cancel()

        try:
            while True:
                ev = self.events.get_nowait()
                self._handle(ev)
        except queue.Empty:
            pass

    def _handle(self, ev):
        kind = ev[0]
        if kind == "meter":
            self.meter = ev[1]
        elif kind == "calib":
            _, zone, count, ok, guidance = ev
            target = NEG_TAPS if zone == "_negative" else CALIB_TAPS
            if zone == "_negative":
                self.neg_live = f"capturing — {count}/{target}"
            else:
                self.calib_live[zone] = (
                    {"text": f"armed — {count}/{target}", "tone": "ok"} if ok
                    else {"text": guidance, "tone": "warn"})
                if ok:
                    self.flashes.append({"zone": zone, "tone": "ok"})
        elif kind == "calib_done":
            _, zone, count = ev
            if zone == "_negative":
                self.calibrating = False
                self.neg_live = None
                self.status = ("Noise samples added — updating model…", "muted")
                self.engine.train_async()
            else:
                self.calib_live[zone] = {"text": f"{count} samples ✓", "tone": "muted"}
                self._calib_next()
        elif kind == "trained":
            result = ev[1]
            tone = "ok" if result["ok"] else "warn"
            self.train_msg = {"text": result["message"], "tone": tone}
            self.status = (result["message"], tone)
            if not result["ok"] and result.get("weakest"):
                self.calib_live[result["weakest"]] = {
                    "text": "weakest — redo this zone", "tone": "err"}
        elif kind == "tap":
            _, label, conf, fired, why = ev
            if fired and label:
                zone = config_mod.get_zone(self.cfg, label)
                self.flashes.append({"zone": label, "tone": "ok"})
                self._log(f"{zone['name']} → {zone['action']['type']} ({conf:.0%})")
            else:
                self._log(f"ignored — {why}")
        elif kind == "eval":
            self._on_eval(*ev[1:])
        elif kind == "error":
            self.status = (ev[1], "err")
            self._log("ERROR " + ev[1])

    def _log(self, text):
        self.logs.appendleft(f"{time.strftime('%H:%M:%S')}  {text}")

    # ------------------------------------------------------------- actions --

    def toggle_listen(self):
        if self.calibrating or self.eval_session:
            return
        if self.listening:
            self.listening = False
            self.engine.set_idle()
            self.status = ("Paused.", "muted")
        else:
            if self.engine.start_listening():
                self.listening = True
                self.status = ("Listening — tap a calibrated zone.", "ok")

    def calib_toggle(self):
        if self.eval_session or self.listening:
            return
        if self.calibrating:
            self.calibrating = False
            self.calib_queue = []
            self._arm_at = None
            self.engine.set_idle()
            self.calib_live = {}
            self.status = ("Calibration cancelled.", "muted")
            return
        for zid in ZONE_ORDER:
            model_mod.delete_zone_samples(self.engine.profile, zid)
        self.calibrating = True
        self.train_msg = None
        self.calib_live = {}
        self.calib_queue = list(ZONE_ORDER)
        self._calib_next()

    def _calib_next(self):
        if not self.calib_queue:
            self.calibrating = False
            self.status = ("Calibration captured — checking agreement…", "muted")
            self.engine.train_async()
            return
        zid = self.calib_queue.pop(0)
        zone = config_mod.get_zone(self.cfg, zid)
        self.status = (f"Armed: {zone['name']} — tap {CALIB_TAPS} times, spread "
                       "around the area.", "ok")
        self.calib_live[zid] = {"text": f"armed — 0/{CALIB_TAPS}", "tone": "ok"}
        self._arm_at, self._arm_zone, self._arm_kind = time.time() + ARM_DELAY_S, zid, "calib"

    def calib_negative(self):
        if self.calibrating or self.eval_session or self.listening:
            return
        self.calibrating = True
        self.calib_queue = []
        self.neg_live = "capturing — 0/%d" % NEG_TAPS
        self.status = ("Armed: noise rejection — talk, type, touch the laptop.", "ok")
        self._arm_at, self._arm_zone, self._arm_kind = \
            time.time() + ARM_DELAY_S, "_negative", "calib"

    def eval_toggle(self):
        if self.listening or self.calibrating:
            return
        if self.eval_session:
            self._eval_cancel()
            return
        self.eval_session = EvaluationSession(self.engine.profile, list(ZONE_ORDER))
        self.eval_queue = list(ZONE_ORDER)
        self.eval_live = {}
        self._eval_next()

    def _eval_cancel(self):
        self.eval_session = None
        self.eval_queue = []
        self._arm_at = None
        self.eval_live = {}
        self.engine.set_idle()
        self.status = ("Evaluation cancelled.", "muted")

    def _eval_next(self):
        if not self.eval_queue:
            session = self.eval_session
            self.eval_session = None
            self.engine.set_idle()
            path = session.save()
            report = session.report()
            verdict = "passed" if report["passed"] else "missed targets"
            self.status = (f"Evaluation {verdict} — saved {path.name}",
                           "ok" if report["passed"] else "warn")
            self.eval_live = {}
            return
        zid = self.eval_queue.pop(0)
        zone = config_mod.get_zone(self.cfg, zid)
        self.status = (f"Armed: {zone['name']} — {TAPS_PER_ZONE} fresh taps.", "ok")
        self.eval_live[zid] = {"text": f"armed — 0/{TAPS_PER_ZONE}", "tone": "ok"}
        self._arm_at, self._arm_zone, self._arm_kind = time.time() + ARM_DELAY_S, zid, "eval"

    def _on_eval(self, expected, predicted, correct, conf, latency_ms):
        if not self.eval_session:
            return
        self.eval_session.add(expected, predicted, correct, conf, latency_ms)
        n = self.eval_session.count_for(expected)
        mark = "✓" if correct else f"✗ {predicted}"
        self.eval_live[expected] = {"text": f"armed — {n}/{TAPS_PER_ZONE}  {mark}",
                                    "tone": "ok" if correct else "warn"}
        self.flashes.append({"zone": expected, "tone": "ok" if correct else "err"})
        if n >= TAPS_PER_ZONE:
            self.engine.set_idle()
            self.eval_live[expected] = {"text": f"{n} taps done", "tone": "muted"}
            self._eval_next()

    # --------------------------------------------------------------- state --

    def state(self):
        counts = model_mod.sample_counts(self.engine.profile)
        calibrated = model_mod.model_path(self.engine.profile).exists()
        zones = []
        for zid in ZONE_ORDER:
            z = config_mod.get_zone(self.cfg, zid)
            a = z.get("action")
            desk_sub, desk_tone = "no action", "muted"
            if not z["enabled"]:
                desk_sub = "off"
            elif a:
                if a["type"] in NEEDS_TARGET and not a.get("target", "").strip():
                    desk_sub, desk_tone = f"{a['type']} · set a target", "warn"
                else:
                    desk_sub = a["type"] + (f" · {a['target']}" if a.get("target") else "")
            n = counts.get(zid, 0)
            calib_sub = self.calib_live.get(
                zid, {"text": f"{n} samples" if n else "not calibrated",
                      "tone": "muted" if n else "dim"})
            zones.append({
                "id": zid, "name": z["name"], "enabled": z["enabled"],
                "type": a["type"] if a else "visual",
                "target": a.get("target", "") if a else "",
                "sensitivity": z["sensitivity"],
                "desk": {"text": desk_sub, "tone": desk_tone},
                "calib": calib_sub,
                "eval": self.eval_live.get(zid, {"text": "", "tone": "muted"}),
            })
        flashes, self.flashes = self.flashes, []
        return {
            "zones": zones,
            "listening": self.listening,
            "calibrating": self.calibrating,
            "evaluating": self.eval_session is not None,
            "locked": self.calibrating or self.eval_session is not None,
            "calibrated": calibrated,
            "negativeCount": counts.get("_negative", 0),
            "negLive": self.neg_live,
            "trainMsg": self.train_msg,
            "status": {"text": self.status[0], "tone": self.status[1]},
            "meter": min(1.0, self.meter * 40),
            "logs": list(self.logs),
            "flashes": flashes,
            "report": latest_report(self.engine.profile),
            "device": self.cfg.get("device") or "system default input",
            "profile": self.engine.profile,
        }


class Api:
    """Methods callable from JS via window.pywebview.api.*"""

    def __init__(self, ctl: Controller):
        self._ctl = ctl

    def poll(self):
        self._ctl.pump()
        return self._ctl.state()

    def toggle_listen(self):
        self._ctl.toggle_listen()

    def calib_toggle(self):
        self._ctl.calib_toggle()

    def calib_negative(self):
        self._ctl.calib_negative()

    def eval_toggle(self):
        self._ctl.eval_toggle()

    def set_action(self, zid, kind, target):
        zone = config_mod.get_zone(self._ctl.cfg, zid)
        zone["action"] = {"type": kind, "target": (target or "").strip()}
        config_mod.save(self._ctl.cfg)

    def set_enabled(self, zid, enabled):
        zone = config_mod.get_zone(self._ctl.cfg, zid)
        zone["enabled"] = bool(enabled)
        config_mod.save(self._ctl.cfg)

    def set_sensitivity(self, zid, value):
        zone = config_mod.get_zone(self._ctl.cfg, zid)
        zone["sensitivity"] = int(value)
        config_mod.save(self._ctl.cfg)

    def test_action(self, zid):
        zone = config_mod.get_zone(self._ctl.cfg, zid)
        try:
            self._ctl.dispatcher.execute(zone["action"])
            return {"ok": True, "message": f"Tested {zone['name']}."}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}


def main():
    import webview

    ctl = Controller()
    api = Api(ctl)
    webview.create_window(
        "Perimeter", html=UI_HTML.read_text(), js_api=api,
        width=1080, height=700, min_size=(940, 620),
        background_color="#09090b",
    )
    try:
        webview.start()
    finally:
        ctl.engine.stop()


if __name__ == "__main__":
    main()
