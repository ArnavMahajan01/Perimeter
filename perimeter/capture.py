"""Continuous non-blocking mic stream writing into a ring buffer."""

import queue

import numpy as np
import sounddevice as sd

from . import BLOCK_SIZE, CHANNELS, RING_SECONDS, SAMPLE_RATE


class RingBuffer:
    def __init__(self, seconds: float = RING_SECONDS, sample_rate: int = SAMPLE_RATE):
        self.size = int(seconds * sample_rate)
        self.buf = np.zeros(self.size, dtype=np.float32)
        # Absolute frame counter of the next frame to be written.
        self.write_frame = 0

    def write(self, block: np.ndarray) -> None:
        n = len(block)
        pos = self.write_frame % self.size
        end = pos + n
        if end <= self.size:
            self.buf[pos:end] = block
        else:
            first = self.size - pos
            self.buf[pos:] = block[:first]
            self.buf[: end - self.size] = block[first:]
        self.write_frame += n

    def read_window(self, center_frame: int, pre_samples: int, post_samples: int):
        """Contiguous slice [center-pre, center+post). None if not fully available."""
        start = center_frame - pre_samples
        end = center_frame + post_samples
        if start < 0 or end > self.write_frame:
            return None  # not yet written (or before stream start)
        if self.write_frame - start > self.size:
            return None  # already overwritten
        out = np.empty(end - start, dtype=np.float32)
        pos = start % self.size
        n = end - start
        tail = min(n, self.size - pos)
        out[:tail] = self.buf[pos : pos + tail]
        if tail < n:
            out[tail:] = self.buf[: n - tail]
        return out


class Capture:
    """Owns the InputStream. The callback only copies data and enqueues blocks."""

    def __init__(self, device=None):
        self.ring = RingBuffer()
        self.blocks: queue.Queue = queue.Queue()
        self.total_frames = 0
        self._stream = sd.InputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._cb,
        )

    def _cb(self, indata, frames, time_info, status):
        block = indata[:, 0].copy()
        block_start = self.total_frames
        self.ring.write(block)
        self.total_frames += frames
        self.blocks.put((block_start, block))

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()
        self._stream.close()


def list_devices():
    """Return (index, name, max_input_channels, default_samplerate) for input devices."""
    out = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            out.append((i, dev["name"], dev["max_input_channels"], dev["default_samplerate"]))
    return out
