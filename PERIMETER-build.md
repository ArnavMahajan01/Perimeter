# Perimeter — Build Document

Implementation instructions. Every module, parameter, data format, and task
needed to get from empty repo to working app.

> **Implementation notes (v1, as built):**
> - `librosa` was dropped. Its numba dependency is heavy and lags new Python
>   releases (this machine runs 3.14). `features.py` reimplements the exact
>   feature set (MFCC, deltas, centroid/bandwidth/rolloff, ZCR) in
>   numpy/scipy. Feature vector is 88-dim.
> - `pynput` was added for the §12 keyboard-suppression hook. It degrades
>   gracefully if missing or unauthorized (macOS Input Monitoring).
> - The UI is served by `perimeter/ui_server.py` (stdlib HTTP server,
>   `python cli.py ui`) with GET/POST `/config`, so the HTML needs no
>   filesystem access. Daemon picks up changes on restart.
> - `smoke_test.py` covers steps 1–5 of §14 offline with synthetic taps —
>   run it after any change to capture/onset/features/model.
> - Dependency pins are `>=` rather than exact, for Python 3.14 wheels.

---

## 1. What this project is

**Perimeter turns the empty desk space around a laptop into programmable
buttons, using nothing but the laptop's built-in microphone.**

The user defines a handful of zones on the bare desk surface — top-left,
top-right, bottom-left, bottom-right. Tapping a zone with a finger or knuckle
runs an action they've assigned to it: open Gmail, toggle play/pause, launch a
terminal, run a script. No touchscreen, no external sensor, no wire, no
wearable, no mat. Software only, on hardware the user already owns.

### How it works

A tap on a desk sends a faint mechanical transient through the desk into the
laptop chassis and its microphone. Each zone produces a measurably different
sound, because distance, damping, resonance and reflection paths to the mic all
differ by position. The program listens continuously, detects tap-like
transients, and classifies which zone each tap came from by its acoustic
signature — then fires the mapped action.

### What it is not

This does **not** compute tap position geometrically. Locating a tap by
time-difference-of-arrival requires multiple microphones spread across the
surface with known spacing; a laptop's built-in mics sit centimetres apart,
which is useless at desk scale. Perimeter instead treats zone identification
as a **classification** problem: a small per-user, per-desk model learns what
each zone sounds like from recorded samples. This is why calibration is a
mandatory part of the product, not a nice-to-have.

### Consequences of that design

These follow directly from the above and shape everything downstream:

- **The model is personal and disposable.** It is trained on one user, one
  laptop, one desk. Moving to a different desk means retraining. There is no
  shipping a pretrained model.
- **Zone count is limited.** Four to six well-separated zones is the working
  range. Adjacent zones on a uniform surface will not separate.
- **The negative class is load-bearing.** Typing, mugs, mouse clicks and chair
  movement all create transients. Without an explicit "not a tap" class, every
  one of them gets forced into a zone and fires an action.
- **False positives are the product risk, not accuracy.** A missed tap is a
  minor annoyance; an app launching itself mid-call is why someone uninstalls.
  Thresholds, cooldowns and the negative class exist to bias toward silence.
- **Some desks simply won't work.** An acoustically uniform surface will not
  separate zones at any model complexity. The build order tests for this early
  (§14) rather than discovering it after the UI is done.

### Scope of v1

In: 4 fixed corner zones, single-tap detection, per-zone action assignment,
calibration flow, config UI, background daemon.

Out: double-tap and swipe gestures, tap-type discrimination (nail vs knuckle
vs pad), user-drawn arbitrary zones, multi-device sync, pretrained models.

---

## 2. Repository layout

```
perimeter/
├── perimeter/
│   ├── __init__.py
│   ├── capture.py          # mic stream → ring buffer
│   ├── onset.py            # transient detection
│   ├── features.py         # MFCC extraction
│   ├── model.py            # train / load / predict
│   ├── dispatch.py         # zone label → OS action
│   ├── config.py           # load/save config JSON
│   ├── calibrate.py        # sample collection flow
│   └── daemon.py           # main loop
├── ui/
│   └── perimeter-ui.html   # config interface
├── data/
│   ├── samples/            # recorded WAVs per zone
│   └── model.pkl           # trained classifier
├── config.json
├── requirements.txt
└── cli.py                  # entrypoint
```

---

## 3. Dependencies

`requirements.txt`:

```
sounddevice==0.4.6
numpy==1.26.4
scipy==1.13.0
librosa==0.10.2
scikit-learn==1.5.0
joblib==1.4.2
```

Platform action dispatch (no pip install, call via subprocess):
- macOS: `open`, `osascript`
- Linux: `xdg-open`, `xdotool`
- Windows: `start`, PowerShell

---

## 4. Audio constants

Define once in `perimeter/__init__.py`, import everywhere:

```python
SAMPLE_RATE   = 44100
CHANNELS      = 1
BLOCK_SIZE    = 512          # frames per callback (~11.6ms)
RING_SECONDS  = 2.0
WINDOW_PRE    = 0.02         # 20ms captured before onset
WINDOW_POST   = 0.28         # 280ms captured after onset
WINDOW_LEN    = int((WINDOW_PRE + WINDOW_POST) * SAMPLE_RATE)  # 13230
```

---

## 5. `capture.py`

**Purpose:** continuous non-blocking mic stream writing into a ring buffer.

Implement:

- `class RingBuffer` — fixed-size `np.zeros(int(RING_SECONDS * SAMPLE_RATE), dtype=np.float32)`, with `write_pos` index, wraps around.
  - `write(block)` — copy block in, advance `write_pos` modulo length.
  - `read_window(center_pos, pre_samples, post_samples)` — return contiguous slice handling wraparound; return `None` if requested range not yet fully written.
- `class Capture`
  - `__init__(device=None)` — open `sounddevice.InputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, channels=CHANNELS, dtype='float32', callback=self._cb)`
  - `_cb(indata, frames, time, status)` — write `indata[:,0]` to ring buffer, increment `self.total_frames`, push `(block_start_frame, block)` to a `queue.Queue` for the onset detector.
  - `start()` / `stop()`

**Do not** do any processing inside the callback beyond buffer writes and queue puts. Callback must return in well under 11ms.

---

## 6. `onset.py`

**Purpose:** decide "a transient just happened" cheaply, and reject non-taps.

Implement `class OnsetDetector`:

State:
```python
self.noise_floor = 0.001      # running estimate, RMS
self.alpha = 0.995            # noise floor smoothing
self.trigger_mult = 6.0       # onset if rms > noise_floor * trigger_mult
self.abs_floor = 0.004        # never trigger below this RMS
self.refractory_s = 0.25      # ignore new onsets this long after one fires
self.last_onset_frame = -1e9
```

Per incoming block:

1. `rms = np.sqrt(np.mean(block**2))`
2. `peak = np.max(np.abs(block))`
3. **Refractory check** — if `current_frame - self.last_onset_frame < refractory_s * SAMPLE_RATE`, update noise floor and return `None`.
4. **Trigger check** — onset if `rms > max(self.noise_floor * self.trigger_mult, self.abs_floor)`.
5. If no trigger: update noise floor `self.noise_floor = alpha * self.noise_floor + (1-alpha) * rms`, return `None`.
   - **Only update the noise floor on non-trigger blocks.** Updating during a tap poisons the estimate.
6. If trigger: record `self.last_onset_frame`, return the onset frame index.

Add `crest_factor = peak / (rms + 1e-9)` as a gate — taps are impulsive, so require `crest_factor > 4.0`. Speech and music have low crest factors and get rejected here before reaching the classifier.

**Keyboard suppression:** expose `suppress_until_frame`. `daemon.py` sets this on keypress (see §12). Detector returns `None` while `current_frame < suppress_until_frame`.

---

## 7. `features.py`

**Purpose:** window → fixed-length feature vector. Must be identical at train and predict time.

Implement `extract(window: np.ndarray) -> np.ndarray`:

1. Assert `len(window) == WINDOW_LEN`. Pad with zeros if short.
2. Peak-normalize: `window = window / (np.max(np.abs(window)) + 1e-9)`
   - This removes tap-force variance. Loudness must not be a feature — otherwise the model learns "hard tap" vs "soft tap" instead of zone.
3. MFCCs:
   ```python
   mfcc = librosa.feature.mfcc(
       y=window, sr=SAMPLE_RATE, n_mfcc=20,
       n_fft=1024, hop_length=256, n_mels=64, fmin=50, fmax=8000
   )
   ```
4. Deltas: `d1 = librosa.feature.delta(mfcc)`
5. Spectral extras (each `(1, T)`):
   - `librosa.feature.spectral_centroid`
   - `librosa.feature.spectral_bandwidth`
   - `librosa.feature.spectral_rolloff`
   - `librosa.feature.zero_crossing_rate`
6. Stack all rows → matrix `(F, T)`. Collapse time axis:
   ```python
   vec = np.concatenate([mat.mean(axis=1), mat.std(axis=1)])
   ```
7. Return `vec` (float32). Length is fixed given constants above — assert it on first call and store as `FEATURE_DIM`.

---

## 8. `calibrate.py`

**Purpose:** collect labeled training samples.

Implement `collect(zone_id: str, n_samples: int = 30)`:

1. Start `Capture` + `OnsetDetector`.
2. Print prompt: `Tap zone '{zone_id}' — 0/30`.
3. On each onset: read window from ring buffer, save to `data/samples/{zone_id}/{uuid4}.wav` via `scipy.io.wavfile.write`, increment counter, print progress.
4. Stop at `n_samples`.

**Also collect a `_negative` class** — this is required, not optional. Without it every noise that passes the onset gate gets forced into a zone and fires an action. Collect ~60 samples of: typing, mug placement, mouse clicks, chair movement, taps in the middle of the desk (not in a zone).

Sampling rules to enforce in the prompt text:
- Vary tap force and finger vs knuckle across samples within a zone.
- Vary position slightly within the zone, don't hit the identical millimeter 30 times.
- Collect all zones in a single session without moving the laptop.

---

## 9. `model.py`

Implement:

- `build_dataset()` — walk `data/samples/*/`, load each WAV, run `features.extract`, return `X (n, FEATURE_DIM)`, `y (n,)` of directory names.
- `train()`:
  ```python
  from sklearn.ensemble import RandomForestClassifier
  from sklearn.pipeline import make_pipeline
  from sklearn.preprocessing import StandardScaler
  from sklearn.model_selection import cross_val_score, StratifiedKFold

  clf = make_pipeline(
      StandardScaler(),
      RandomForestClassifier(n_estimators=400, min_samples_leaf=2,
                             class_weight='balanced', random_state=0)
  )
  scores = cross_val_score(clf, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0))
  ```
  - Print mean CV accuracy and the confusion matrix.
  - **Gate:** if mean CV accuracy < 0.85, print the confusion matrix and abort without saving. Tell the user which zone pair is confusing and to move those zones further apart.
  - Fit on full data, `joblib.dump(clf, 'data/model.pkl')`.
- `predict(vec) -> (label, confidence)`:
  ```python
  proba = clf.predict_proba(vec.reshape(1, -1))[0]
  idx = np.argmax(proba)
  return clf.classes_[idx], proba[idx]
  ```

---

## 10. `dispatch.py`

Implement `class Dispatcher`:

- `__init__(config)` — store zone→action map.
- `fire(zone_id)`:
  1. Look up action spec.
  2. If none, return.
  3. Enforce cooldown: skip if `time.time() - last_fired[zone_id] < 1.0`.
  4. Feedback **before** executing — play a short tone or print. Users need to know the tap registered even when the action is invisible.
  5. Execute per `type`:
     - `app` → macOS `open -a {target}` / Linux `xdg-open {target}` / Windows `start {target}`
     - `url` → same `open`/`xdg-open`/`start` with URL
     - `hotkey` → macOS `osascript -e 'tell app "System Events" to key code ...'` / Linux `xdotool key {target}`
     - `shell` → `subprocess.Popen(target, shell=True)`
  6. Wrap in try/except, log failures, never let a bad action kill the daemon.

---

## 11. `config.py` — config schema

`config.json`:

```json
{
  "version": 1,
  "device": null,
  "confidence_threshold": 0.70,
  "onset": {
    "trigger_mult": 6.0,
    "abs_floor": 0.004,
    "crest_min": 4.0,
    "refractory_s": 0.25,
    "keypress_suppress_ms": 120
  },
  "zones": [
    {
      "id": "tl",
      "name": "Top Left",
      "enabled": true,
      "action": { "type": "url", "target": "https://mail.google.com" },
      "sensitivity": 62
    },
    {
      "id": "tr",
      "name": "Top Right",
      "enabled": false,
      "action": null,
      "sensitivity": 50
    },
    {
      "id": "bl",
      "name": "Bottom Left",
      "enabled": true,
      "action": { "type": "hotkey", "target": "XF86AudioPlay" },
      "sensitivity": 55
    },
    {
      "id": "br",
      "name": "Bottom Right",
      "enabled": false,
      "action": null,
      "sensitivity": 50
    }
  ]
}
```

`sensitivity` (0–100 from the UI slider) maps to per-zone confidence threshold:
```python
threshold = 0.95 - (sensitivity / 100.0) * 0.35   # 100 → 0.60, 0 → 0.95
```

Implement `load()`, `save(cfg)`, `get_zone(id)`. Validate on load; on schema mismatch, back up the old file and write defaults.

---

## 12. `daemon.py` — main loop

```
start Capture
load model, config
build Dispatcher
install keyboard hook → on any keypress, set onset.suppress_until_frame

loop:
    pull (start_frame, block) from queue
    onset_frame = detector.process(block, start_frame)
    if onset_frame is None: continue

    wait until ring buffer has WINDOW_POST seconds past onset_frame
    window = ring.read_window(onset_frame, WINDOW_PRE, WINDOW_POST)
    if window is None: continue

    vec = features.extract(window)
    label, conf = model.predict(vec)

    if label == "_negative": continue
    zone = config.get_zone(label)
    if not zone or not zone["enabled"]: continue
    if conf < threshold_for(zone): log and continue

    dispatcher.fire(label)
```

Run feature extraction and prediction on a **worker thread**, not the audio callback thread.

Log every event to `data/events.log` as JSONL: `{ts, zone, confidence, fired, rms, crest}`. This log is the debugging tool for tuning thresholds — build it from day one, not later.

---

## 13. `cli.py` — commands

```
python cli.py devices                    # list input devices, print indices
python cli.py listen                     # raw RMS/crest meter, no classification
python cli.py calibrate --zone tl -n 30  # collect samples for a zone
python cli.py calibrate --negative -n 60 # collect negative class
python cli.py train                      # build dataset, CV, save model
python cli.py run                        # start daemon
python cli.py test                       # daemon w/ dispatch disabled, prints predictions
```

---

## 14. Build order

Each step has an exit condition. Do not start a step until the previous one passes.

| # | Task | Exit condition |
|---|---|---|
| 1 | `capture.py` + `cli.py listen` | Meter visibly spikes on a desk tap, sits near floor otherwise |
| 2 | `onset.py` | Detector fires on ≥95% of deliberate taps, ~0 fires during 60s of typing |
| 3 | `features.py` | `extract()` returns fixed-length vector; same WAV → identical vector twice |
| 4 | `calibrate.py` | 30 samples/zone × 4 zones + 60 negatives on disk, all valid WAVs |
| 5 | `model.py train` | CV accuracy ≥ 0.85, no zone pair confused >15% in confusion matrix |
| 6 | `cli.py test` | Live predictions correct ≥8/10 taps per zone |
| 7 | `dispatch.py` | Each action type executes on target OS |
| 8 | `daemon.py run` | 30 min normal work session: zero unintended fires |
| 9 | UI ↔ `config.json` wiring | Saving in UI changes daemon behavior on next reload |

If step 5 fails: reduce to 2 zones on opposite corners and retest. If 2 opposite corners fail to separate, the desk surface is too acoustically uniform — the approach will not work on that desk, and no amount of model tuning fixes it.

---

## 15. Tuning reference

| Symptom | Change |
|---|---|
| Taps missed | Lower `trigger_mult` → 4.0, lower `abs_floor` |
| Typing triggers onsets | Raise `crest_min` → 5.0, raise `keypress_suppress_ms` → 200 |
| Onset fires twice per tap | Raise `refractory_s` → 0.35 |
| Correct onsets, wrong zone | Retrain; if CV was already low, move zones apart |
| Correct zone, low confidence | Raise `sensitivity` for that zone; collect 15 more samples |
| Random actions during calls | Raise `confidence_threshold` → 0.85; verify `_negative` class has speech samples |
| Worked yesterday, not today | Laptop moved → recalibrate |

---

## 16. Ship gates

Do not build past v1 until all pass:

- [ ] 4 zones, ≥90% correct on 40 live taps (10/zone)
- [ ] Zero unintended fires across a 2-hour work session
- [ ] Recalibration flow completes in under 3 minutes
- [ ] Daemon survives mic disconnect/reconnect without crashing
- [ ] `events.log` rotates at 10MB
- [ ] Every action type verified on the target OS
