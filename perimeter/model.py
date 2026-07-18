"""Zone classifier: dataset building, training with quality gates, prediction.

Holo-style robustness on top of the classifier itself:
- leave-one-out agreement per zone (identifies the weakest zone before saving)
- nearest-example novelty gate: events far from every training example are
  rejected as out-of-distribution instead of being forced into a zone
"""

from pathlib import Path

import joblib
import numpy as np
from scipy.io import wavfile

from . import SAMPLE_RATE
from . import features

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "data" / "profiles"

LOO_GATE = 0.75          # minimum overall leave-one-out agreement to save
NOVELTY_FACTOR = 2.5     # x median intra-class NN distance → OOD


def samples_dir(profile: str = "default") -> Path:
    return PROFILES_DIR / profile / "samples"


def model_path(profile: str = "default") -> Path:
    return PROFILES_DIR / profile / "model.pkl"


def list_profiles() -> list:
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.name for p in PROFILES_DIR.iterdir() if p.is_dir())


def sample_counts(profile: str = "default") -> dict:
    d = samples_dir(profile)
    if not d.exists():
        return {}
    return {z.name: len(list(z.glob("*.wav"))) for z in d.iterdir() if z.is_dir()}


def delete_zone_samples(profile: str, zone_id: str) -> None:
    import shutil
    d = samples_dir(profile) / zone_id
    if d.exists():
        shutil.rmtree(d)


def build_dataset(profile: str = "default"):
    X, y = [], []
    for zone_dir in sorted(samples_dir(profile).iterdir()):
        if not zone_dir.is_dir():
            continue
        for wav in sorted(zone_dir.glob("*.wav")):
            sr, data = wavfile.read(wav)
            if sr != SAMPLE_RATE:
                continue
            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32767.0
            X.append(features.extract(data))
            y.append(zone_dir.name)
    if not X:
        raise ValueError("No samples recorded yet.")
    return np.vstack(X), np.array(y)


def _make_classifier():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    # Regularized linear model (Holo's choice): stable on tiny datasets and
    # its probabilities are better calibrated than a small forest's.
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced"),
    )


def loo_agreement(X, y):
    """Leave-one-out agreement, overall and per zone.

    Returns (overall, {zone: fraction}). Small datasets only — O(n) fits."""
    from sklearn.base import clone

    n = len(y)
    correct = np.zeros(n, dtype=bool)
    base = _make_classifier()
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        clf = clone(base)
        clf.fit(X[mask], y[mask])
        correct[i] = clf.predict(X[i : i + 1])[0] == y[i]
    per_zone = {}
    for zone in sorted(set(y)):
        sel = y == zone
        per_zone[zone] = float(correct[sel].mean())
    return float(correct.mean()), per_zone


def train(profile: str = "default", verbose: bool = True) -> dict:
    """Train, quality-gate, and save. Returns a result dict for the UI:
    {ok, agreement, per_zone, weakest, message}"""
    def log(msg):
        if verbose:
            print(msg)

    try:
        X, y = build_dataset(profile)
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "agreement": 0.0, "per_zone": {}, "weakest": None,
                "message": str(e)}

    zone_labels = [l for l in sorted(set(y)) if l != "_negative"]
    if len(zone_labels) < 2:
        return {"ok": False, "agreement": 0.0, "per_zone": {}, "weakest": None,
                "message": "Calibrate at least 2 zones first."}

    overall, per_zone = loo_agreement(X, y)
    zone_scores = {z: a for z, a in per_zone.items() if z != "_negative"}
    weakest = min(zone_scores, key=zone_scores.get) if zone_scores else None
    log(f"LOO agreement: {overall:.3f} overall, per zone: "
        + ", ".join(f"{z}={a:.2f}" for z, a in per_zone.items()))

    if overall < LOO_GATE:
        msg = (f"Calibration agreement too low ({overall:.0%}). "
               f"Weakest zone: '{weakest}' ({zone_scores.get(weakest, 0):.0%}) — "
               f"redo that zone.")
        log(msg + " Model NOT saved.")
        return {"ok": False, "agreement": overall, "per_zone": per_zone,
                "weakest": weakest, "message": msg}

    clf = _make_classifier()
    clf.fit(X, y)

    # Novelty reference: per-example distance to nearest same-class neighbour
    # in standardized feature space.
    Xs = clf.named_steps["standardscaler"].transform(X)
    nn_dists = []
    for i in range(len(Xs)):
        same = np.where(y == y[i])[0]
        same = same[same != i]
        if len(same):
            nn_dists.append(np.min(np.linalg.norm(Xs[same] - Xs[i], axis=1)))
    novelty_ref = float(np.median(nn_dists)) if nn_dists else 1e9

    path = model_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"clf": clf, "Xs": Xs, "y": y, "novelty_ref": novelty_ref}, path)
    log(f"Model saved ({overall:.0%} agreement) to {path}")
    return {"ok": True, "agreement": overall, "per_zone": per_zone,
            "weakest": weakest,
            "message": f"Calibrated — {overall:.0%} agreement."}


def load_model(profile: str = "default"):
    path = model_path(profile)
    if not path.exists():
        raise FileNotFoundError(f"Profile '{profile}' is not calibrated yet.")
    return joblib.load(path)


def predict(bundle, vec):
    """Returns (label, confidence, is_ood)."""
    clf = bundle["clf"]
    proba = clf.predict_proba(vec.reshape(1, -1))[0]
    idx = int(np.argmax(proba))
    label, conf = clf.classes_[idx], float(proba[idx])

    vs = clf.named_steps["standardscaler"].transform(vec.reshape(1, -1))[0]
    nearest = float(np.min(np.linalg.norm(bundle["Xs"] - vs, axis=1)))
    is_ood = nearest > bundle["novelty_ref"] * NOVELTY_FACTOR
    return label, conf, is_ood
