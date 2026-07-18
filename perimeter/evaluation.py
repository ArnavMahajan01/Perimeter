"""Held-out evaluation reports: per-zone accuracy, confusion matrix,
latency — saved as JSON and CSV, newest restored per profile on relaunch."""

import csv
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "data" / "evaluations"

TAPS_PER_ZONE = 15
ACCURACY_TARGET = 0.80
LATENCY_TARGET_MS = 200.0


class EvaluationSession:
    """Collects armed evaluation taps and produces a report."""

    def __init__(self, profile: str, zone_ids: list):
        self.profile = profile
        self.zone_ids = zone_ids
        self.taps = []  # dicts: expected, predicted, correct, conf, latency_ms

    def add(self, expected, predicted, correct, conf, latency_ms):
        self.taps.append({
            "expected": expected, "predicted": predicted, "correct": bool(correct),
            "confidence": round(conf, 3), "latency_ms": round(latency_ms, 1),
        })

    def count_for(self, zone_id) -> int:
        return sum(1 for t in self.taps if t["expected"] == zone_id)

    def report(self) -> dict:
        total = len(self.taps)
        correct = sum(t["correct"] for t in self.taps)
        latencies = sorted(t["latency_ms"] for t in self.taps)
        median_latency = latencies[len(latencies) // 2] if latencies else 0.0

        per_zone = {}
        for z in self.zone_ids:
            zt = [t for t in self.taps if t["expected"] == z]
            per_zone[z] = {
                "taps": len(zt),
                "correct": sum(t["correct"] for t in zt),
                "accuracy": (sum(t["correct"] for t in zt) / len(zt)) if zt else 0.0,
            }

        labels = self.zone_ids + ["(rejected)"]
        confusion = {e: {p: 0 for p in labels} for e in self.zone_ids}
        for t in self.taps:
            p = t["predicted"] if t["predicted"] in labels else "(rejected)"
            confusion[t["expected"]][p] += 1

        accuracy = correct / total if total else 0.0
        return {
            "profile": self.profile,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_taps": total,
            "accuracy": round(accuracy, 3),
            "median_latency_ms": round(median_latency, 1),
            "passed": accuracy >= ACCURACY_TARGET and median_latency < LATENCY_TARGET_MS,
            "per_zone": per_zone,
            "confusion": confusion,
            "taps": self.taps,
        }

    def save(self) -> Path:
        report = self.report()
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        base = EVAL_DIR / f"{self.profile}-{stamp}"

        json_path = base.with_suffix(".json")
        json_path.write_text(json.dumps(report, indent=2))

        with open(base.with_suffix(".csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["expected", "predicted", "correct", "confidence", "latency_ms"])
            for t in self.taps:
                w.writerow([t["expected"], t["predicted"], t["correct"],
                            t["confidence"], t["latency_ms"]])
        return json_path


def latest_report(profile: str):
    """Newest saved evaluation for this profile, or None. Reports from other
    profiles are never returned."""
    if not EVAL_DIR.exists():
        return None
    candidates = sorted(EVAL_DIR.glob(f"{profile}-*.json"), reverse=True)
    for path in candidates:
        try:
            report = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if report.get("profile") == profile:
            return report
    return None
