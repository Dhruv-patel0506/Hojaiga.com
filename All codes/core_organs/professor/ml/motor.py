"""
professor.ml.motor -- the MOTOR-TIMING model of the virtual mouse: how long a pointer movement takes, as a function of distance D and target width W (Fitts's law: T = a + b * log2(D/W + 1)).

The shipped parameters are the textbook prior (a = 0.10 s, b = 0.12 s/bit) - they are NOT learned from people and the Professor says so. The model is a ridge regression anchored on that prior:
with zero data it returns the prior; every observed movement (distance, width, seconds) moves (a, b) toward the data, and `r2` / `rmse` tell how well the law fits what was seen. Data can come
from anywhere that measures real movements: demonstrations a person chooses to record, or the actual durations of the virtual pointer's glides (a consistency check only - those are synthetic).
There is no hidden collection of anybody's mouse use: nothing here reads the physical mouse.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

A0, B0 = 0.10, 0.12


class MotorModel:
    def __init__(self, path: Optional[str] = None, prior_weight: float = 6.0):
        self.path = path
        self.lam = float(prior_weight)                         # the prior counts as this many pseudo-observations
        self.n = 0
        self.n_person = 0                                      # observations from a PERSON's own recorded movements; the rest are the virtual pointer's measured glides (synthetic)
        self.Sx = self.Sy = self.Sxx = self.Sxy = self.Syy = 0.0
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                self.n, self.Sx, self.Sy, self.Sxx, self.Sxy, self.Syy = (d.get(k, 0) for k in ("n", "Sx", "Sy", "Sxx", "Sxy", "Syy"))
                self.n_person = d.get("n_person", 0)
            except Exception:
                pass

    @staticmethod
    def index_of_difficulty(distance: float, width: float) -> float:
        return math.log2(max(0.0, distance) / max(4.0, width) + 1.0)

    def observe(self, distance: float, width: float, seconds: float, source: str = "") -> None:
        x, y = self.index_of_difficulty(distance, width), float(seconds)
        self.n += 1
        if source == "person":
            self.n_person += 1
        self.Sx += x
        self.Sy += y
        self.Sxx += x * x
        self.Sxy += x * y
        self.Syy += y * y

    def params(self) -> Tuple[float, float]:
        """(a, b): ridge solution of  min sum (y - a - b x)^2 + lam ((a - A0)^2 + (b - B0)^2)."""
        lam = self.lam
        # normal equations  [[n + lam, Sx], [Sx, Sxx + lam]] [a, b] = [Sy + lam A0, Sxy + lam B0]
        m11, m12, m22 = self.n + lam, self.Sx, self.Sxx + lam
        r1, r2 = self.Sy + lam * A0, self.Sxy + lam * B0
        det = m11 * m22 - m12 * m12
        if abs(det) < 1e-12:
            return A0, B0
        return (r1 * m22 - r2 * m12) / det, (m11 * r2 - m12 * r1) / det

    def predict(self, distance: float, width: float) -> float:
        a, b = self.params()
        return max(0.16, min(1.6, a + b * self.index_of_difficulty(distance, width)))

    def fit_quality(self) -> Dict[str, Any]:
        if self.n < 3:
            return {"n": self.n, "r2": None, "rmse": None}
        a, b = self.params()
        sse = self.Syy - 2 * a * self.Sy - 2 * b * self.Sxy + self.n * a * a + 2 * a * b * self.Sx + b * b * self.Sxx
        sst = self.Syy - self.Sy * self.Sy / self.n
        var_x = self.Sxx / self.n - (self.Sx / self.n) ** 2
        # r2 only MEANS something when the observations actually differ: with a near-constant index (every drag the same distance) or near-constant time, sst collapses toward 0 and a plain
        # 1 - sse/sst explodes to absurd negatives (measured: -25000 from a batch of identical full-screen drags). Report rmse, and say the fit is unjudged instead of printing a fake number.
        unjudged = sst < 1e-6 or var_x < 1e-4
        return {"n": self.n, "r2": None if unjudged else round(1 - sse / sst, 4), "rmse": round(math.sqrt(max(0.0, sse) / self.n), 4),
                **({"r2_note": "not judged: the observed movements barely differ (index variance %.5f, time variance %.6f) - varied drags are needed to grade the fit" % (var_x, sst / self.n)} if unjudged else {})}

    def summary(self) -> Dict[str, Any]:
        a, b = self.params()
        return {"a": round(a, 4), "b": round(b, 4), "prior": {"a": A0, "b": B0}, "learned_from_people": self.n_person > 0,
                "observations": {"measured_movements": self.n, "from_a_person": self.n_person, "from_the_virtual_pointer": self.n - self.n_person}, **self.fit_quality()}

    def save(self, path: Optional[str] = None) -> None:
        path = path or self.path
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"n": self.n, "n_person": self.n_person, "Sx": self.Sx, "Sy": self.Sy, "Sxx": self.Sxx, "Sxy": self.Sxy, "Syy": self.Syy}, fh)
