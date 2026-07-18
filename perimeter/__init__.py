"""Perimeter — four tap zones around the laptop, cross-platform.

Shared audio constants. Import these everywhere; never redefine locally,
since features must be computed identically at calibration and use time.
"""

SAMPLE_RATE = 44100
CHANNELS = 1
BLOCK_SIZE = 512          # frames per callback (~11.6 ms)
RING_SECONDS = 2.0
WINDOW_PRE = 0.015        # seconds captured before onset
WINDOW_POST = 0.075       # seconds captured after onset (90 ms window total)
WINDOW_LEN = int((WINDOW_PRE + WINDOW_POST) * SAMPLE_RATE)  # 3969
