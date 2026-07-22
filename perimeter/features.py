"""Window -> fixed-length feature vector. Must be identical at train and predict.

Implemented with numpy/scipy only (no librosa/numba): MFCCs + deltas +
spectral centroid/bandwidth/rolloff + zero-crossing rate, mean/std pooled
over time.
"""

import numpy as np
from scipy.fftpack import dct

from . import SAMPLE_RATE, WINDOW_LEN, WINDOW_PRE

# Bumped whenever extraction changes incompatibly; models trained with a
# different version must be retrained (from the saved wavs — no retapping).
VERSION = 2  # v2: peak alignment

N_FFT = 1024
HOP = 256
N_MELS = 64
N_MFCC = 20
FMIN = 50.0
FMAX = 8000.0

# Where the tap's absolute peak is anchored inside the window (samples).
PEAK_POS = int(WINDOW_PRE * SAMPLE_RATE)

FEATURE_DIM = None  # set on first extract() call, asserted thereafter

_mel_fb = None
_hann = None


def _hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)


def _mel_to_hz(mel):
    return 700.0 * (10.0 ** (np.asarray(mel) / 2595.0) - 1.0)


def _mel_filterbank():
    """Triangular mel filterbank, (N_MELS, N_FFT//2 + 1)."""
    n_bins = N_FFT // 2 + 1
    fft_freqs = np.linspace(0, SAMPLE_RATE / 2, n_bins)
    mel_pts = np.linspace(_hz_to_mel(FMIN), _hz_to_mel(FMAX), N_MELS + 2)
    hz_pts = _mel_to_hz(mel_pts)
    fb = np.zeros((N_MELS, n_bins), dtype=np.float32)
    for m in range(N_MELS):
        lo, ctr, hi = hz_pts[m], hz_pts[m + 1], hz_pts[m + 2]
        up = (fft_freqs - lo) / (ctr - lo + 1e-9)
        down = (hi - fft_freqs) / (hi - ctr + 1e-9)
        fb[m] = np.maximum(0.0, np.minimum(up, down))
    return fb


def _stft_mag(window: np.ndarray) -> np.ndarray:
    """Magnitude spectrogram, (N_FFT//2 + 1, T). Center-padded like librosa."""
    global _hann
    if _hann is None:
        _hann = np.hanning(N_FFT).astype(np.float32)
    padded = np.pad(window, N_FFT // 2, mode="reflect")
    n_frames = 1 + (len(padded) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = padded[idx] * _hann
    return np.abs(np.fft.rfft(frames, axis=1)).T.astype(np.float32)


def _delta(mat: np.ndarray, width: int = 9) -> np.ndarray:
    """Savitzky-Golay style delta over the time axis (librosa-compatible)."""
    half = width // 2
    kernel = np.arange(-half, half + 1, dtype=np.float32)
    norm = np.sum(kernel**2)
    padded = np.pad(mat, ((0, 0), (half, half)), mode="edge")
    out = np.empty_like(mat)
    for t in range(mat.shape[1]):
        out[:, t] = padded[:, t : t + width] @ kernel / norm
    return out


def _align_to_peak(window: np.ndarray) -> np.ndarray:
    """Shift the window so its absolute peak sits at PEAK_POS.

    The onset detector triggers on ~12 ms audio blocks, so where the tap
    lands inside the window jitters by up to a block — the same tap can
    produce visibly different features. Anchoring on the energy peak makes
    windows comparable across taps (and across calibration vs. live use).
    """
    peak = int(np.argmax(np.abs(window)))
    shift = PEAK_POS - peak
    if shift == 0:
        return window
    out = np.zeros_like(window)
    if shift > 0:
        out[shift:] = window[:-shift]
    else:
        out[:shift] = window[-shift:]
    return out


def extract(window: np.ndarray) -> np.ndarray:
    global FEATURE_DIM, _mel_fb

    window = np.asarray(window, dtype=np.float32)
    if len(window) < WINDOW_LEN:
        window = np.pad(window, (0, WINDOW_LEN - len(window)))
    elif len(window) > WINDOW_LEN:
        window = window[:WINDOW_LEN]

    window = _align_to_peak(window)

    # Remove tap-force variance; loudness must not be a feature.
    window = window / (np.max(np.abs(window)) + 1e-9)

    S = _stft_mag(window)                      # (freq_bins, T)
    power = S**2

    if _mel_fb is None:
        _mel_fb = _mel_filterbank()
    mel = _mel_fb @ power                      # (N_MELS, T)
    log_mel = np.log(mel + 1e-10)
    mfcc = dct(log_mel, type=2, axis=0, norm="ortho")[:N_MFCC]
    d1 = _delta(mfcc)

    freqs = np.linspace(0, SAMPLE_RATE / 2, S.shape[0])[:, None]
    total = S.sum(axis=0) + 1e-9
    centroid = (freqs * S).sum(axis=0) / total                    # (T,)
    bandwidth = np.sqrt(((freqs - centroid) ** 2 * S).sum(axis=0) / total)

    # Rolloff: frequency below which 85% of spectral energy lies.
    cumsum = np.cumsum(S, axis=0)
    rolloff_idx = np.argmax(cumsum >= 0.85 * cumsum[-1], axis=0)
    rolloff = freqs[rolloff_idx, 0]

    # Zero-crossing rate per frame (same framing as the STFT, without window).
    padded = np.pad(window, N_FFT // 2, mode="reflect")
    n_frames = S.shape[1]
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = padded[idx]
    zcr = np.mean(np.abs(np.diff(np.signbit(frames), axis=1)), axis=1)

    mat = np.vstack([mfcc, d1, centroid[None], bandwidth[None], rolloff[None], zcr[None]])
    vec = np.concatenate([mat.mean(axis=1), mat.std(axis=1)]).astype(np.float32)

    if FEATURE_DIM is None:
        FEATURE_DIM = len(vec)
    else:
        assert len(vec) == FEATURE_DIM, f"feature dim drifted: {len(vec)} != {FEATURE_DIM}"
    return vec
