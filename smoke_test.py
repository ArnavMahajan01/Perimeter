"""Offline smoke tests: no microphone needed.

1. features.extract determinism and fixed length (90 ms windows)
2. OnsetDetector behavior (impulse, sustained sound, suppression)
3. RingBuffer wraparound
4. Calibration quality gate (weak / clipped / noisy taps)
5. Synthetic dataset -> LOO-gated train -> predict, incl. OOD rejection
6. Evaluation session report + persistence round trip
7. Config schema (4 Holo-style zones)
"""

import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from perimeter import BLOCK_SIZE, SAMPLE_RATE, WINDOW_LEN, WINDOW_PRE
from perimeter import config as config_mod
from perimeter import features
from perimeter.capture import RingBuffer
from perimeter.onset import OnsetDetector

rng = np.random.default_rng(0)
FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + f"  {name}")
    if not cond:
        FAILURES.append(name)


def synth_tap(f0: float, decay: float, amp: float = 0.5) -> np.ndarray:
    """Damped-oscillator 'tap' with noise; distinct per (f0, decay)."""
    t = np.arange(WINDOW_LEN) / SAMPLE_RATE
    sig = np.exp(-t * decay) * (
        np.sin(2 * np.pi * f0 * t)
        + 0.5 * np.sin(2 * np.pi * f0 * 2.7 * t)
        + 0.2 * rng.standard_normal(WINDOW_LEN)
    )
    sig[: int(WINDOW_PRE * SAMPLE_RATE)] *= 0.01  # quiet pre-onset region
    sig = sig / np.max(np.abs(sig)) * amp
    return sig.astype(np.float32)


# 1. Feature determinism
w = synth_tap(400, 60)
v1, v2 = features.extract(w), features.extract(w)
check("features deterministic", np.array_equal(v1, v2))
check(f"feature dim fixed ({len(v1)})", len(v1) == features.FEATURE_DIM and len(v1) > 0)
short = features.extract(w[: WINDOW_LEN // 2])
check("short window padded to same dim", len(short) == len(v1))

# 2. Onset detector
det = OnsetDetector()
fired = []
frame = 0
for i in range(200):
    block = (0.0005 * rng.standard_normal(BLOCK_SIZE)).astype(np.float32)
    if i == 100:
        block[10] = 0.5
        block[11:60] = 0.3 * np.exp(-np.arange(49) / 10)
    if det.process(block, frame) is not None:
        fired.append(i)
    frame += BLOCK_SIZE
check("onset fires once on impulse", fired == [100])

det2 = OnsetDetector()
fired2 = 0
frame = 0
for i in range(200):
    block = (0.05 * np.sin(2 * np.pi * 300 * (frame + np.arange(BLOCK_SIZE)) / SAMPLE_RATE)).astype(np.float32)
    if det2.process(block, frame) is not None:
        fired2 += 1
    frame += BLOCK_SIZE
check("sustained tone rejected", fired2 == 0)

det3 = OnsetDetector()
det3.suppress_until_frame = 10**9
block = np.zeros(BLOCK_SIZE, dtype=np.float32)
block[0] = 0.9
check("keyboard suppression blocks onset", det3.process(block, 0) is None)

# 3. Ring buffer wraparound
ring = RingBuffer(seconds=0.1)
n_total = int(0.35 * SAMPLE_RATE)
data = np.arange(n_total, dtype=np.float32)
for s in range(0, n_total - BLOCK_SIZE, BLOCK_SIZE):
    ring.write(data[s : s + BLOCK_SIZE])
center = ring.write_frame - 500
win = ring.read_window(center, 100, 200)
check("ring window contiguous across wrap",
      win is not None and np.array_equal(win, data[center - 100 : center + 200]))
check("ring rejects overwritten range", ring.read_window(100, 50, 50) is None)

# 4. Calibration quality gate
from perimeter.engine import quality_gate

ok, _ = quality_gate(synth_tap(400, 60, amp=0.5))
check("quality gate accepts a clean tap", ok)
ok, why = quality_gate(synth_tap(400, 60, amp=0.005))
check("quality gate rejects weak tap", not ok and "weak" in why.lower())
ok, why = quality_gate(synth_tap(400, 60, amp=0.99))
check("quality gate rejects clipped tap", not ok and "light" in why.lower())
noisy = synth_tap(400, 60, amp=0.3)
noisy[: int(WINDOW_PRE * SAMPLE_RATE)] = 0.25 * rng.standard_normal(int(WINDOW_PRE * SAMPLE_RATE))
ok, why = quality_gate(noisy)
check("quality gate rejects noisy pre-roll", not ok and "noise" in why.lower())

# 5. Synthetic train/predict round trip with LOO gate and OOD rejection
import perimeter.model as model_mod
from scipy.io import wavfile

PROFILE = "_smoke"
tmp = model_mod.PROFILES_DIR / PROFILE
if tmp.exists():
    shutil.rmtree(tmp)
def synth_negative() -> np.ndarray:
    """Noise burst — typing/speech-like, broadband rather than tonal."""
    t = np.arange(WINDOW_LEN) / SAMPLE_RATE
    sig = np.exp(-t * 25) * rng.standard_normal(WINDOW_LEN)
    sig = sig / np.max(np.abs(sig)) * 0.4
    return sig.astype(np.float32)

ZONES = {"lr": (300, 40), "rr": (700, 70), "lf": (1200, 110), "rf": (2500, 160)}
for zone, (f0, decay) in ZONES.items():
    d = model_mod.samples_dir(PROFILE) / zone
    d.mkdir(parents=True)
    for k in range(10):
        sig = synth_tap(f0 * (1 + 0.05 * rng.standard_normal()), decay)
        wavfile.write(d / f"{k}.wav", SAMPLE_RATE, (sig * 32767 * 0.6).astype(np.int16))
neg_dir = model_mod.samples_dir(PROFILE) / "_negative"
neg_dir.mkdir(parents=True)
for k in range(10):
    wavfile.write(neg_dir / f"{k}.wav", SAMPLE_RATE,
                  (synth_negative() * 32767 * 0.6).astype(np.int16))

result = model_mod.train(PROFILE)
check("training passes LOO gate on separable data", result["ok"])
check("train reports per-zone agreement",
      set(ZONES) | {"_negative"} == set(result["per_zone"]))
if result["ok"]:
    bundle = model_mod.load_model(PROFILE)
    hits = 0
    for zone, (f0, decay) in ZONES.items():
        votes = 0
        for _ in range(3):  # majority of 3 fresh probes per class
            label, conf, is_ood = model_mod.predict(
                bundle, features.extract(synth_tap(f0, decay)))
            good = label == zone and not is_ood
            votes += good
            if not good:
                print(f"      probe miss: {zone} -> {label} conf={conf:.2f} ood={is_ood}")
        hits += votes >= 2
    check(f"predict correct on all 4 zones ({hits}/4)", hits == 4)

    neg_votes = 0
    for _ in range(3):
        label, conf, is_ood = model_mod.predict(bundle, features.extract(synth_negative()))
        neg_votes += label == "_negative" and not is_ood
    check("fresh noise burst classified as negative", neg_votes >= 2)

    # something acoustically alien (sustained chirp: not a tap, not a noise
    # burst) → OOD gate should reject rather than force a zone
    t = np.arange(WINDOW_LEN) / SAMPLE_RATE
    alien = (0.4 * np.sin(2 * np.pi * (500 + 8000 * t) * t)).astype(np.float32)
    _, _, is_ood = model_mod.predict(bundle, features.extract(alien))
    check("out-of-distribution sound rejected", is_ood)

bad = model_mod.train("_does_not_exist", verbose=False)
check("train on missing profile fails gracefully", not bad["ok"] and bad["message"])
shutil.rmtree(tmp)

# 6. Evaluation session round trip
from perimeter import evaluation as eval_mod

eval_mod.EVAL_DIR = Path("data/_smoke_evals")
if eval_mod.EVAL_DIR.exists():
    shutil.rmtree(eval_mod.EVAL_DIR)
sess = eval_mod.EvaluationSession("_smoke", ["lr", "rr", "lf", "rf"])
for z in ["lr", "rr", "lf", "rf"]:
    for i in range(15):
        correct = not (z == "rf" and i < 3)  # rf gets 12/15
        sess.add(z, z if correct else "(rejected)", correct, 0.9, 45.0)
rep = sess.report()
check("evaluation totals correct", rep["total_taps"] == 60 and abs(rep["accuracy"] - 57 / 60) < 1e-9)
check("evaluation passes targets", rep["passed"])
check("confusion counts rejections", rep["confusion"]["rf"]["(rejected)"] == 3)
path = sess.save()
check("evaluation saved as json+csv",
      path.exists() and path.with_suffix(".csv").exists())
restored = eval_mod.latest_report("_smoke")
check("latest report restored for profile", restored and restored["total_taps"] == 60)
check("other profiles see no report", eval_mod.latest_report("elsewhere") is None)
shutil.rmtree(eval_mod.EVAL_DIR)

# 7. Config schema
cfg = config_mod.load()
check("config has 4 Holo-style zones",
      [z["id"] for z in cfg["zones"]] == ["lr", "rr", "lf", "rf"])
z = config_mod.get_zone(cfg, "lr")
check("get_zone finds Left Rear", z is not None and z["name"] == "Left Rear")
thr = config_mod.zone_threshold(cfg, {"sensitivity": 100})
check("sensitivity 100 -> threshold 0.60", abs(thr - 0.60) < 1e-9)
thr = config_mod.zone_threshold(cfg, {"sensitivity": 0})
check("sensitivity 0 -> threshold 0.95", abs(thr - 0.95) < 1e-9)

from perimeter.dispatch import ACTION_TYPES
check("holo action types present",
      {"visual", "sound", "copy", "speak", "url", "app", "file", "hotkey",
       "shell", "screenshot"} == set(ACTION_TYPES))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
    sys.exit(1)
print("All smoke tests passed.")
