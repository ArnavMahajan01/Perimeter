"""Collect labeled training samples per zone (and the required negative class)."""

import time
import uuid

import numpy as np
from scipy.io import wavfile

from . import SAMPLE_RATE, WINDOW_POST, WINDOW_PRE
from .capture import Capture
from .model import samples_dir
from .onset import OnsetDetector

NEGATIVE_ZONE = "_negative"

NEGATIVE_PROMPT = """\
Collecting the NEGATIVE class — sounds that must NOT fire an action.
Produce a mix of, roughly equally:
  - typing bursts on the keyboard
  - placing a mug / glass on the desk
  - mouse clicks
  - shifting in / bumping your chair
  - taps in the MIDDLE of the desk (outside every zone)
  - a few seconds of speaking near the laptop
"""

ZONE_PROMPT = """\
Collecting zone '{zone}'. Tips for good samples:
  - vary tap force (light and firm) and alternate finger pad vs knuckle
  - vary the exact spot a few centimetres within the zone
  - collect ALL zones in one session without moving the laptop
"""


def collect(zone_id: str, n_samples: int = 30, device=None, profile: str = "default") -> None:
    out_dir = samples_dir(profile) / zone_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(NEGATIVE_PROMPT if zone_id == NEGATIVE_ZONE else ZONE_PROMPT.format(zone=zone_id))

    cap = Capture(device=device)
    det = OnsetDetector()
    cap.start()
    pre = int(WINDOW_PRE * SAMPLE_RATE)
    post = int(WINDOW_POST * SAMPLE_RATE)
    count = 0
    print(f"Tap zone '{zone_id}' — {count}/{n_samples}")
    try:
        while count < n_samples:
            start_frame, block = cap.blocks.get()
            onset = det.process(block, start_frame)
            if onset is None:
                continue
            # Wait until the ring buffer holds the full post-onset window.
            target = onset + post
            while cap.ring.write_frame < target:
                time.sleep(0.005)
            window = cap.ring.read_window(onset, pre, post)
            if window is None:
                continue
            path = out_dir / f"{uuid.uuid4()}.wav"
            wavfile.write(path, SAMPLE_RATE, (window * 32767).astype(np.int16))
            count += 1
            print(f"Tap zone '{zone_id}' — {count}/{n_samples}")
    except KeyboardInterrupt:
        print(f"\nStopped early with {count} samples.")
    finally:
        cap.stop()
    print(f"Saved {count} samples to {out_dir}")
