"""Perimeter — native desktop app, Holo-style, cross-platform.

Sidebar navigation: Desk, Calibrate, Actions, Evaluate, Diagnostics.
Four zones around the laptop (Left/Right x Rear/Front), guided armed
calibration with quality feedback, per-zone actions with inline Test,
held-out evaluation with saved reports.
"""

import queue
import time
import tkinter as tk
from tkinter import ttk

from . import config as config_mod
from . import model as model_mod
from .dispatch import ACTION_TYPES, NEEDS_TARGET, Dispatcher
from .engine import AudioEngine
from .evaluation import (ACCURACY_TARGET, LATENCY_TARGET_MS, TAPS_PER_ZONE,
                         EvaluationSession, latest_report)

BLACK = "#000000"
CARD = "#0c0c0c"
CARD_LIT = "#181818"
EDGE = "#1e1e1e"
WHITE = "#ffffff"
GREY = "#8a8a8a"
DIM = "#3c3c3c"
GREEN = "#38d167"
AMBER = "#e3b341"
RED = "#f85149"

FONT = "Helvetica Neue"
MONO = "Menlo"

CALIB_TAPS = 10
NEG_TAPS = 20

ZONE_ORDER = ["lr", "rr", "lf", "rf"]
# Desk map: two vertical rails beside the laptop, rear on top (display side)
ZONE_POS = {"lr": (0, 0), "rr": (0, 2), "lf": (1, 0), "rf": (1, 2)}

TARGET_HINTS = {
    "visual": "no target needed — the highlight is the action",
    "sound": "no target needed",
    "copy": "text to copy",
    "speak": "text to speak",
    "url": "https://…",
    "app": "application name",
    "file": "path to file or folder",
    "hotkey": "playpause, key code, or keystroke expression",
    "shell": "shell command",
    "screenshot": "no target needed",
}

VIEWS = ["Desk", "Calibrate", "Actions", "Evaluate", "Diagnostics"]


class PerimeterApp:
    def __init__(self):
        self.cfg = config_mod.load()
        self.events = queue.Queue()
        self.engine = AudioEngine(self.cfg, self.events)
        self.dispatcher = Dispatcher(self.cfg)  # for Test buttons

        self.listening = False
        self.calib_queue = []
        self.calibrating = False
        self.eval_session = None
        self.eval_queue = []

        self.root = tk.Tk()
        self.root.title("Perimeter")
        self.root.configure(bg=BLACK)
        self.root.geometry("1020x640")
        self.root.minsize(920, 580)

        self._nav_buttons = {}
        self._views = {}
        self._zone_tiles = {}      # desk-map tiles per view name
        self._build_shell()
        self._show("Desk")

        self.engine.start()
        self.root.after(80, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # ---------------------------------------------------------------- shell --

    def _build_shell(self):
        side = tk.Frame(self.root, bg=BLACK, width=190)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        tk.Label(side, text="PERIMETER", bg=BLACK, fg=WHITE,
                 font=(FONT, 15, "bold")).pack(anchor="w", padx=22, pady=(26, 18))

        for name in VIEWS:
            b = tk.Label(side, text=name, bg=BLACK, fg=GREY, anchor="w",
                         font=(FONT, 13), cursor="hand2", padx=22, pady=7)
            b.pack(fill="x")
            b.bind("<Button-1>", lambda e, n=name: self._show(n))
            self._nav_buttons[name] = b

        self.mic_dot = tk.Label(side, text="●  mic", bg=BLACK, fg=DIM, anchor="w",
                                font=(FONT, 11), padx=22)
        self.mic_dot.pack(side="bottom", anchor="w", pady=(0, 18))

        rule = tk.Frame(self.root, bg=EDGE, width=1)
        rule.pack(side="left", fill="y")

        self.content = tk.Frame(self.root, bg=BLACK)
        self.content.pack(side="left", fill="both", expand=True)

        self.status = tk.Label(self.root, text="", bg=BLACK, fg=GREY, anchor="w",
                               font=(FONT, 11), padx=16)
        # status packed into each view's bottom instead; simpler: overlay bottom
        self.status.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0, y=-6, x=200)

        self._views["Desk"] = self._build_desk()
        self._views["Calibrate"] = self._build_calibrate()
        self._views["Actions"] = self._build_actions()
        self._views["Evaluate"] = self._build_evaluate()
        self._views["Diagnostics"] = self._build_diagnostics()

    def _show(self, name):
        if self.calibrating and name != "Calibrate":
            self._set_status("Finish or cancel calibration first.", AMBER)
            return
        if self.eval_session and name != "Evaluate":
            self._set_status("Finish or cancel the evaluation first.", AMBER)
            return
        for view in self._views.values():
            view.pack_forget()
        self._views[name].pack(fill="both", expand=True, padx=34, pady=(26, 30))
        for n, b in self._nav_buttons.items():
            b.configure(fg=WHITE if n == name else GREY,
                        font=(FONT, 13, "bold" if n == name else "normal"))
        if name == "Evaluate":
            self._refresh_eval_report()

    def _set_status(self, text, color=GREY):
        self.status.configure(text=text, fg=color)

    # ------------------------------------------------------------- desk map --

    def _desk_map(self, parent, view_name, tile_body=None):
        """Two 2-zone rails flanking the laptop. Returns {zone_id: tile}."""
        grid = tk.Frame(parent, bg=BLACK)
        grid.columnconfigure(0, weight=1, uniform="m")
        grid.columnconfigure(1, weight=0)
        grid.columnconfigure(2, weight=1, uniform="m")
        grid.rowconfigure(0, weight=1)
        grid.rowconfigure(1, weight=1)

        mid = tk.Frame(grid, bg=BLACK)
        mid.grid(row=0, column=1, rowspan=2, padx=26)
        tk.Label(mid, text="⌨", bg=BLACK, fg=DIM, font=(FONT, 26)).pack()
        tk.Label(mid, text="laptop", bg=BLACK, fg=DIM, font=(FONT, 10)).pack()
        tk.Label(mid, text="display side ↑", bg=BLACK, fg=DIM,
                 font=(FONT, 9)).pack(pady=(10, 0))

        tiles = {}
        for zid in ZONE_ORDER:
            zone = config_mod.get_zone(self.cfg, zid)
            r, c = ZONE_POS[zid]
            tile = tk.Frame(grid, bg=CARD, highlightbackground=EDGE,
                            highlightthickness=1)
            tile.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
            inner = tk.Frame(tile, bg=CARD)
            inner.pack(fill="both", expand=True, padx=16, pady=12)
            tk.Label(inner, text=zone["name"].upper(), bg=CARD, fg=WHITE,
                     font=(FONT, 12, "bold")).pack(anchor="w")
            sub = tk.Label(inner, text="", bg=CARD, fg=GREY, font=(FONT, 11),
                           anchor="w", justify="left")
            sub.pack(anchor="w", pady=(4, 0))
            tiles[zid] = {"tile": tile, "inner": inner, "sub": sub}
            if tile_body:
                tile_body(zid, inner)
        self._zone_tiles.setdefault(view_name, {}).update(tiles)
        return grid

    def _flash_zone(self, view_name, zid, color=WHITE):
        tiles = self._zone_tiles.get(view_name, {})
        t = tiles.get(zid)
        if not t:
            return
        t["tile"].configure(highlightbackground=color, highlightthickness=2)
        self.root.after(500, lambda: t["tile"].configure(
            highlightbackground=EDGE, highlightthickness=1))

    def _tile_sub(self, view_name, zid, text, color=GREY):
        t = self._zone_tiles.get(view_name, {}).get(zid)
        if t:
            t["sub"].configure(text=text, fg=color)

    # ----------------------------------------------------------------- desk --

    def _build_desk(self):
        v = tk.Frame(self.content, bg=BLACK)
        head = tk.Frame(v, bg=BLACK)
        head.pack(fill="x", pady=(0, 14))
        tk.Label(head, text="Desk", bg=BLACK, fg=WHITE,
                 font=(FONT, 18, "bold")).pack(side="left")
        self.listen_btn = tk.Label(head, text="  START  ", bg=WHITE, fg=BLACK,
                                   font=(FONT, 12, "bold"), cursor="hand2", pady=7)
        self.listen_btn.pack(side="right")
        self.listen_btn.bind("<Button-1>", lambda e: self._toggle_listen())

        self.desk_hint = tk.Label(
            v, text="Calibrate first, then START and tap a zone.",
            bg=BLACK, fg=GREY, font=(FONT, 12), anchor="w")
        self.desk_hint.pack(fill="x", pady=(0, 12))

        self._desk_map(v, "Desk").pack(fill="both", expand=True)

        self.desk_log = tk.Label(v, text="", bg=BLACK, fg=DIM, anchor="w",
                                 font=(MONO, 11))
        self.desk_log.pack(fill="x", pady=(14, 0))
        self._refresh_desk_tiles()
        return v

    def _refresh_desk_tiles(self):
        for zid in ZONE_ORDER:
            zone = config_mod.get_zone(self.cfg, zid)
            a = zone.get("action")
            color = GREY
            if not zone["enabled"]:
                text = "off"
            elif not a:
                text = "no action"
            elif a["type"] in NEEDS_TARGET and not a.get("target", "").strip():
                text = f"{a['type']} · set a target in Actions"
                color = AMBER
            else:
                text = a["type"] + (f" · {a['target']}" if a.get("target") else "")
            self._tile_sub("Desk", zid, text, color)

    def _toggle_listen(self):
        if self.calibrating or self.eval_session:
            return
        if self.listening:
            self.listening = False
            self.engine.set_idle()
            self.listen_btn.configure(text="  START  ", bg=WHITE, fg=BLACK)
            self._set_status("Paused.")
        else:
            if not self.engine.start_listening():
                return  # error event will explain
            self.listening = True
            self.listen_btn.configure(text="  STOP  ", bg=CARD_LIT, fg=WHITE)
            self._set_status("Listening — tap a calibrated zone.", GREEN)

    # ------------------------------------------------------------ calibrate --

    def _build_calibrate(self):
        v = tk.Frame(self.content, bg=BLACK)
        head = tk.Frame(v, bg=BLACK)
        head.pack(fill="x", pady=(0, 14))
        tk.Label(head, text="Calibrate", bg=BLACK, fg=WHITE,
                 font=(FONT, 18, "bold")).pack(side="left")
        self.calib_btn = tk.Label(head, text="  BEGIN  ", bg=WHITE, fg=BLACK,
                                  font=(FONT, 12, "bold"), cursor="hand2", pady=7)
        self.calib_btn.pack(side="right")
        self.calib_btn.bind("<Button-1>", lambda e: self._calib_toggle())

        self.calib_hint = tk.Label(
            v, text=(f"Each zone is armed in turn — make {CALIB_TAPS} natural taps, "
                     "spread around the highlighted area. Keep the laptop where it "
                     "will stay; moving it invalidates calibration."),
            bg=BLACK, fg=GREY, font=(FONT, 12), anchor="w", wraplength=760,
            justify="left")
        self.calib_hint.pack(fill="x", pady=(0, 12))

        self._desk_map(v, "Calibrate").pack(fill="both", expand=True)

        foot = tk.Frame(v, bg=BLACK)
        foot.pack(fill="x", pady=(14, 0))
        self.neg_btn = tk.Label(foot, text="＋ noise rejection (talk / type while armed)",
                                bg=BLACK, fg=GREY, font=(FONT, 12), cursor="hand2")
        self.neg_btn.pack(side="left")
        self.neg_btn.bind("<Button-1>", lambda e: self._calib_negative())
        self.calib_result = tk.Label(foot, text="", bg=BLACK, fg=GREY,
                                     font=(FONT, 12), anchor="e")
        self.calib_result.pack(side="right")
        self._refresh_calib_tiles()
        return v

    def _refresh_calib_tiles(self):
        counts = model_mod.sample_counts(self.engine.profile)
        for zid in ZONE_ORDER:
            n = counts.get(zid, 0)
            self._tile_sub("Calibrate", zid,
                           f"{n} samples" if n else "not calibrated",
                           GREY if n else DIM)
        neg = counts.get("_negative", 0)
        self.neg_btn.configure(
            text=f"＋ noise rejection — {neg} samples" if neg
            else "＋ noise rejection (talk / type while armed)")

    def _calib_toggle(self):
        if self.calibrating:
            self.calibrating = False
            self.calib_queue = []
            self.engine.set_idle()
            self.calib_btn.configure(text="  BEGIN  ")
            self._set_status("Calibration cancelled.")
            self._refresh_calib_tiles()
            return
        # Redo everything: clear old samples so redoing is deliberate and clean
        for zid in ZONE_ORDER:
            model_mod.delete_zone_samples(self.engine.profile, zid)
        self.calibrating = True
        self.calib_btn.configure(text="  CANCEL  ")
        self.calib_queue = list(ZONE_ORDER)
        self._calib_next()

    def _calib_next(self):
        self._refresh_calib_tiles()
        if not self.calib_queue:
            self.calibrating = False
            self.calib_btn.configure(text="  BEGIN  ")
            self._set_status("Calibration captured — checking agreement…", GREY)
            self.engine.train_async()
            return
        zid = self.calib_queue.pop(0)
        zone = config_mod.get_zone(self.cfg, zid)
        self._set_status(f"Armed: {zone['name']} — tap {CALIB_TAPS} times, "
                         "short pauses between taps.", GREEN)
        self._tile_sub("Calibrate", zid, f"armed — 0/{CALIB_TAPS}", GREEN)
        # Short transition so moving your hand doesn't count as a tap
        self.root.after(900, lambda: self.engine.arm_calibration(zid, CALIB_TAPS))

    def _calib_negative(self):
        if self.calibrating or self.eval_session or self.listening:
            return
        self.calibrating = True
        self.calib_btn.configure(text="  CANCEL  ")
        self.calib_queue = []
        self._set_status("Armed: noise rejection — talk, type, touch the laptop. "
                         f"Capturing {NEG_TAPS} sounds.", GREEN)
        self.root.after(600, lambda: self.engine.arm_calibration("_negative", NEG_TAPS))

    def _on_calib_event(self, zone, count, ok, guidance):
        target = NEG_TAPS if zone == "_negative" else CALIB_TAPS
        if zone == "_negative":
            self._set_status(f"noise rejection — {count}/{target}", GREEN)
        else:
            self._tile_sub("Calibrate", zone,
                           f"armed — {count}/{target}" if ok else guidance,
                           GREEN if ok else AMBER)
            if ok:
                self._flash_zone("Calibrate", zone, GREEN)

    def _on_calib_done(self, zone, count):
        if zone == "_negative":
            self.calibrating = False
            self.calib_btn.configure(text="  BEGIN  ")
            self._set_status("Noise samples added — updating model…")
            self._refresh_calib_tiles()
            self.engine.train_async()
            return
        self._tile_sub("Calibrate", zone, f"{count} samples ✓")
        self._calib_next()

    def _on_trained(self, result):
        color = GREEN if result["ok"] else AMBER
        self.calib_result.configure(text=result["message"], fg=color)
        self._set_status(result["message"], color)
        if not result["ok"] and result.get("weakest"):
            weak = result["weakest"]
            zone = config_mod.get_zone(self.cfg, weak)
            if zone:
                self._tile_sub("Calibrate", weak, "weakest — redo this zone", RED)

    # -------------------------------------------------------------- actions --

    def _build_actions(self):
        v = tk.Frame(self.content, bg=BLACK)
        tk.Label(v, text="Actions", bg=BLACK, fg=WHITE,
                 font=(FONT, 18, "bold")).pack(anchor="w", pady=(0, 14))

        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("Dark.TCombobox", fieldbackground=CARD_LIT, background=CARD_LIT,
                    foreground=WHITE, arrowcolor=WHITE, bordercolor=EDGE,
                    lightcolor=CARD, darkcolor=CARD)

        self._action_rows = {}
        for side_name, zids in (("LEFT", ["lr", "lf"]), ("RIGHT", ["rr", "rf"])):
            tk.Label(v, text=side_name, bg=BLACK, fg=DIM,
                     font=(FONT, 10, "bold")).pack(anchor="w", pady=(10, 4))
            for zid in zids:
                self._action_row(v, zid)
        return v

    def _action_row(self, parent, zid):
        zone = config_mod.get_zone(self.cfg, zid)
        row = tk.Frame(parent, bg=CARD, highlightbackground=EDGE, highlightthickness=1)
        row.pack(fill="x", pady=3)
        pad = tk.Frame(row, bg=CARD)
        pad.pack(fill="x", padx=14, pady=10)

        tk.Label(pad, text=zone["name"], bg=CARD, fg=WHITE, width=11, anchor="w",
                 font=(FONT, 12, "bold")).pack(side="left")

        type_var = tk.StringVar(value=zone["action"]["type"] if zone["action"] else "visual")
        box = ttk.Combobox(pad, textvariable=type_var, values=ACTION_TYPES, width=10,
                           state="readonly", style="Dark.TCombobox")
        box.pack(side="left", padx=(4, 8))

        target_var = tk.StringVar(value=zone["action"].get("target", "") if zone["action"] else "")
        entry = tk.Entry(pad, textvariable=target_var, bg=BLACK, fg=WHITE,
                         insertbackground=WHITE, bd=0, highlightthickness=1,
                         highlightbackground=EDGE, highlightcolor=GREY, font=(FONT, 12))
        entry.pack(side="left", fill="x", expand=True, ipady=5)

        hint = tk.Label(pad, text="", bg=CARD, fg=DIM, font=(FONT, 10), width=26,
                        anchor="w")
        hint.pack(side="left", padx=(8, 8))

        test = tk.Label(pad, text="Test", bg=CARD, fg=GREY, font=(FONT, 12, "underline"),
                        cursor="hand2")
        test.pack(side="right")

        def sync(save=True):
            t = type_var.get()
            hint.configure(text=TARGET_HINTS.get(t, ""))
            entry.configure(state="normal" if t in NEEDS_TARGET else "disabled")
            zone["action"] = {"type": t, "target": target_var.get().strip()}
            if save:
                config_mod.save(self.cfg)
                self._refresh_desk_tiles()

        def run_test(_e=None):
            try:
                self.dispatcher.execute(zone["action"])
                self._set_status(f"Tested {zone['name']}.", GREEN)
            except Exception as ex:
                self._set_status(f"Test failed: {ex}", RED)

        box.bind("<<ComboboxSelected>>", lambda e: sync())
        # Save on every keystroke — waiting for focus-out meant a typed target
        # was silently lost if the user went straight from typing to tapping.
        entry.bind("<KeyRelease>", lambda e: sync())
        test.bind("<Button-1>", run_test)
        sync(save=False)
        self._action_rows[zid] = row

    # ------------------------------------------------------------- evaluate --

    def _build_evaluate(self):
        v = tk.Frame(self.content, bg=BLACK)
        head = tk.Frame(v, bg=BLACK)
        head.pack(fill="x", pady=(0, 14))
        tk.Label(head, text="Evaluate", bg=BLACK, fg=WHITE,
                 font=(FONT, 18, "bold")).pack(side="left")
        self.eval_btn = tk.Label(head, text="  RUN TEST  ", bg=WHITE, fg=BLACK,
                                 font=(FONT, 12, "bold"), cursor="hand2", pady=7)
        self.eval_btn.pack(side="right")
        self.eval_btn.bind("<Button-1>", lambda e: self._eval_toggle())

        tk.Label(v, text=(f"Held-out accuracy test: {TAPS_PER_ZONE} fresh taps per "
                          f"zone. Targets: ≥{ACCURACY_TARGET:.0%} accuracy, "
                          f"median latency <{LATENCY_TARGET_MS:.0f} ms. "
                          "Rejected taps count as incorrect."),
                 bg=BLACK, fg=GREY, font=(FONT, 12), anchor="w",
                 wraplength=760, justify="left").pack(fill="x", pady=(0, 12))

        self._desk_map(v, "Evaluate").pack(fill="both", expand=True)

        self.eval_text = tk.Text(v, height=9, bg=CARD, fg=GREY, bd=0,
                                 highlightthickness=1, highlightbackground=EDGE,
                                 font=(MONO, 11), state="disabled")
        self.eval_text.pack(fill="x", pady=(14, 0))
        return v

    def _refresh_eval_report(self):
        report = latest_report(self.engine.profile)
        if report and not self.eval_session:
            self._render_report(report, saved=True)

    def _eval_toggle(self):
        if self.eval_session:
            self.eval_session = None
            self.eval_queue = []
            self.engine.set_idle()
            self.eval_btn.configure(text="  RUN TEST  ")
            self._set_status("Evaluation cancelled.")
            return
        if self.listening or self.calibrating:
            return
        self.eval_session = EvaluationSession(self.engine.profile, list(ZONE_ORDER))
        self.eval_queue = list(ZONE_ORDER)
        self.eval_btn.configure(text="  CANCEL  ")
        self._eval_next()

    def _eval_next(self):
        if not self.eval_queue:
            session = self.eval_session
            self.eval_session = None
            self.engine.set_idle()
            self.eval_btn.configure(text="  RUN TEST  ")
            path = session.save()
            report = session.report()
            self._render_report(report, saved=True)
            verdict = "PASSED" if report["passed"] else "MISSED TARGETS"
            self._set_status(f"Evaluation {verdict} — report saved to {path.name}",
                             GREEN if report["passed"] else AMBER)
            return
        zid = self.eval_queue.pop(0)
        zone = config_mod.get_zone(self.cfg, zid)
        self._set_status(f"Armed: {zone['name']} — {TAPS_PER_ZONE} fresh taps.", GREEN)
        self._tile_sub("Evaluate", zid, f"armed — 0/{TAPS_PER_ZONE}", GREEN)

        def arm():
            if self.eval_session and not self.engine.arm_evaluation(zid):
                self._eval_toggle()  # cancel on error (no model)
        self.root.after(900, arm)

    def _on_eval_event(self, expected, predicted, correct, conf, latency_ms):
        if not self.eval_session:
            return
        self.eval_session.add(expected, predicted, correct, conf, latency_ms)
        n = self.eval_session.count_for(expected)
        mark = "✓" if correct else f"✗ {predicted}"
        self._tile_sub("Evaluate", expected, f"armed — {n}/{TAPS_PER_ZONE}  {mark}",
                       GREEN if correct else AMBER)
        self._flash_zone("Evaluate", expected, GREEN if correct else RED)
        if n >= TAPS_PER_ZONE:
            self.engine.set_idle()
            self._tile_sub("Evaluate", expected, f"{n} taps done")
            self._eval_next()

    def _render_report(self, report, saved=False):
        lines = [
            f"{report['timestamp']}   profile: {report['profile']}"
            + ("   (saved)" if saved else ""),
            f"accuracy {report['accuracy']:.0%}   median latency "
            f"{report['median_latency_ms']:.0f} ms   "
            + ("PASSED" if report["passed"] else "missed targets"),
            "",
        ]
        for zid, z in report["per_zone"].items():
            zone = config_mod.get_zone(self.cfg, zid)
            name = zone["name"] if zone else zid
            lines.append(f"  {name:<12} {z['correct']:>2}/{z['taps']:<2} "
                         f"({z['accuracy']:.0%})")
        lines.append("")
        labels = list(report["confusion"].keys()) + ["(rejected)"]
        lines.append("  confusion (rows=expected):")
        header = "               " + "".join(f"{l:>10}" for l in labels)
        lines.append(header)
        for e, row in report["confusion"].items():
            lines.append(f"  {e:>12} " + "".join(f"{row.get(p, 0):>10}" for p in labels))

        self.eval_text.configure(state="normal")
        self.eval_text.delete("1.0", "end")
        self.eval_text.insert("1.0", "\n".join(lines))
        self.eval_text.configure(state="disabled")

    # ----------------------------------------------------------- diagnostics --

    def _build_diagnostics(self):
        v = tk.Frame(self.content, bg=BLACK)
        tk.Label(v, text="Diagnostics", bg=BLACK, fg=WHITE,
                 font=(FONT, 18, "bold")).pack(anchor="w", pady=(0, 14))

        meter_row = tk.Frame(v, bg=BLACK)
        meter_row.pack(fill="x", pady=(4, 2))
        tk.Label(meter_row, text="level", bg=BLACK, fg=DIM, width=7, anchor="w",
                 font=(FONT, 11)).pack(side="left")
        self.diag_meter = tk.Canvas(meter_row, height=4, bg=EDGE, bd=0,
                                    highlightthickness=0)
        self.diag_meter.pack(side="left", fill="x", expand=True)
        self.diag_bar = self.diag_meter.create_rectangle(0, 0, 0, 4, fill=WHITE, width=0)

        self.diag_info = tk.Label(v, text="", bg=BLACK, fg=GREY, anchor="w",
                                  font=(MONO, 11), justify="left")
        self.diag_info.pack(fill="x", pady=(10, 8))

        self.diag_log = tk.Text(v, bg=CARD, fg=GREY, bd=0, highlightthickness=1,
                                highlightbackground=EDGE, font=(MONO, 11),
                                state="disabled")
        self.diag_log.pack(fill="both", expand=True)

        dev = self.cfg.get("device") or "system default input"
        self.diag_info.configure(
            text=f"input: {dev}\nprofile: {self.engine.profile}\n"
                 f"window: 90 ms   sample rate: 44100 Hz")
        return v

    def _diag_append(self, text):
        self.diag_log.configure(state="normal")
        self.diag_log.insert("1.0", f"{time.strftime('%H:%M:%S')}  {text}\n")
        self.diag_log.delete("200.0", "end")
        self.diag_log.configure(state="disabled")

    # ------------------------------------------------------------ event pump --

    def _poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "meter":
                    _, rms, crest = ev
                    # Smooth the raw per-block RMS (fast attack / slow release)
                    # so the bar doesn't flicker and spike to full on brief noise.
                    self._meter = getattr(self, "_meter", 0.0)
                    self._meter = (0.6 * self._meter + 0.4 * rms) if rms > self._meter \
                        else (0.85 * self._meter + 0.15 * rms)
                    self.mic_dot.configure(fg=GREEN if self._meter > 0 else DIM)
                    w = self.diag_meter.winfo_width()
                    frac = min(1.0, self._meter * 40)
                    self.diag_meter.coords(self.diag_bar, 0, 0, int(w * frac), 4)
                elif kind == "calib":
                    self._on_calib_event(ev[1], ev[2], ev[3], ev[4])
                elif kind == "calib_done":
                    self._on_calib_done(ev[1], ev[2])
                elif kind == "trained":
                    self._on_trained(ev[1])
                elif kind == "tap":
                    _, label, conf, fired, why = ev
                    if fired and label:
                        self._flash_zone("Desk", label)
                        zone = config_mod.get_zone(self.cfg, label)
                        self.desk_log.configure(
                            text=f"{time.strftime('%H:%M:%S')}  {zone['name']} → "
                                 f"{zone['action']['type']}  ({conf:.0%})")
                    else:
                        self.desk_log.configure(
                            text=f"{time.strftime('%H:%M:%S')}  ignored — {why}")
                    self._diag_append(f"tap label={label} conf={conf:.2f} {why}")
                elif kind == "eval":
                    self._on_eval_event(ev[1], ev[2], ev[3], ev[4], ev[5])
                elif kind == "error":
                    self._set_status(ev[1], RED)
                    self._diag_append("ERROR " + ev[1])
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _close(self):
        self.engine.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    try:
        PerimeterApp().run()
    except tk.TclError as e:
        raise SystemExit(f"Could not open a window: {e}")


if __name__ == "__main__":
    main()
