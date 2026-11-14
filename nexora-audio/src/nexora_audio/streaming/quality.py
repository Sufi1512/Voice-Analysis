"""Per-call input quality numbers, cheap enough to run on every live call.

Fed with the decoded input (before cleaning), it keeps the 20 ms block energies of the
last 60 s and summarises them:

* ``speech_level_dbfs``: 90th percentile of block levels (where the voice sits)
* ``noise_floor_dbfs``: 10th percentile (the background between words)
* ``snr_db``: their difference
* ``active_pct``: share of blocks more than 10 dB above the noise floor
* ``clipped_pct``: samples at or near full scale (the input was overdriven)
"""

from __future__ import annotations

from typing import Any

import numpy as np

from nexora_audio.utils.audio_utils import Float32Array

_WINDOW_BLOCKS = 3000  # 60 s of 20 ms blocks
_CLIP = 0.999


class QualityMonitor:
    def __init__(self, rate: int) -> None:
        self.rate = rate
        self._block = max(1, rate // 50)
        self.reset()

    def reset(self) -> None:
        self._energies = np.zeros(_WINDOW_BLOCKS, np.float64)
        self._count = 0
        self._partial = np.zeros(0, np.float32)
        self.samples = 0
        self.clipped = 0

    def update(self, x: Float32Array) -> None:
        if len(x) == 0:
            return
        self.samples += len(x)
        self.clipped += int(np.count_nonzero(np.abs(x) >= _CLIP))
        buf = np.concatenate([self._partial, x]) if len(self._partial) else x
        m = len(buf) // self._block
        if m:
            e = np.mean(buf[: m * self._block].astype(np.float64).reshape(m, -1) ** 2, axis=1)
            for v in e[-_WINDOW_BLOCKS:]:
                self._energies[self._count % _WINDOW_BLOCKS] = v
                self._count += 1
        self._partial = buf[m * self._block :].copy()

    def summary(self) -> dict[str, Any]:
        n = min(self._count, _WINDOW_BLOCKS)
        out: dict[str, Any] = {
            "seconds": round(self.samples / self.rate, 2),
            "clipped_pct": round(100 * self.clipped / self.samples, 3) if self.samples else 0.0,
        }
        if n < 5:
            return out
        lv = 10 * np.log10(self._energies[:n] + 1e-12)
        floor, speech = float(np.percentile(lv, 10)), float(np.percentile(lv, 90))
        out.update(
            speech_level_dbfs=round(speech, 1),
            noise_floor_dbfs=round(floor, 1),
            snr_db=round(speech - floor, 1),
            active_pct=round(float(100 * np.mean(lv > floor + 10)), 1),
        )
        return out
