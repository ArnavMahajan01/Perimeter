"""Cheap transient detection with noise-floor tracking and non-tap rejection."""

import numpy as np

from . import SAMPLE_RATE


class OnsetDetector:
    def __init__(
        self,
        trigger_mult: float = 6.0,
        abs_floor: float = 0.004,
        crest_min: float = 4.0,
        refractory_s: float = 0.25,
    ):
        self.noise_floor = 0.001
        self.alpha = 0.995
        self.trigger_mult = trigger_mult
        self.abs_floor = abs_floor
        self.crest_min = crest_min
        self.refractory_s = refractory_s
        self.last_onset_frame = -1e9
        # daemon.py pushes this forward on keypresses to mask keyboard clicks
        self.suppress_until_frame = -1

        # Exposed for the `listen` meter and event logging.
        self.last_rms = 0.0
        self.last_crest = 0.0

    def process(self, block: np.ndarray, block_start_frame: int):
        """Return onset frame index, or None."""
        rms = float(np.sqrt(np.mean(block**2)))
        peak = float(np.max(np.abs(block)))
        crest = peak / (rms + 1e-9)
        self.last_rms = rms
        self.last_crest = crest

        current_frame = block_start_frame

        if current_frame < self.suppress_until_frame:
            self._update_floor(rms)
            return None

        if current_frame - self.last_onset_frame < self.refractory_s * SAMPLE_RATE:
            self._update_floor(rms)
            return None

        triggered = rms > max(self.noise_floor * self.trigger_mult, self.abs_floor)

        if not triggered:
            # Only update the floor on quiet blocks — updating during a tap
            # would poison the estimate.
            self._update_floor(rms)
            return None

        if crest < self.crest_min:
            # Loud but not impulsive (speech, music): not a tap. Don't update
            # the floor either, this block isn't background noise.
            return None

        self.last_onset_frame = current_frame
        return current_frame

    def _update_floor(self, rms: float) -> None:
        self.noise_floor = self.alpha * self.noise_floor + (1 - self.alpha) * rms
