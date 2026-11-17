"""Shared helpers for the Natural Intelligence (NI) dual-brain pipeline.

Everything here is deterministic: given the same base seed and cycle index the
same 70/30 windows and the same torch seeds are produced (Grill rule 1).
"""
import os, sys, json, time, hashlib
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
RUNS = os.path.join(ROOT, "runs")
VRAM_LIMIT_GB = 6.0
BASE_SEED = 20261107

os.makedirs(DATA, exist_ok=True)
os.makedirs(RUNS, exist_ok=True)

_LOGFILE = None


def set_logfile(path):
    global _LOGFILE
    _LOGFILE = path


def log(*a):
    msg = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        print(msg, flush=True)
    except Exception:
        pass
    if _LOGFILE:
        try:
            with open(_LOGFILE, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass


def task_hash(name: str) -> int:
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16)


def seed_for(task: str, cycle: int, salt: int = 0) -> int:
    """Deterministic seed that shifts every cycle (the 'rotation')."""
    return (BASE_SEED * 1000003 + cycle * 7919 + task_hash(task) + salt * 104729) % (2**31 - 1)


def split_train_mask(ids: np.ndarray, seed: int, train_frac: float = 0.70) -> np.ndarray:
    """Vectorised seed-shifting hash window. True = train (70%), False = val (30%)."""
    x = ids.astype(np.uint64)
    with np.errstate(over="ignore"):
        x = x * np.uint64(0x9E3779B97F4A7C15) + np.uint64(seed) * np.uint64(0xBF58476D1CE4E5B9)
        x ^= x >> np.uint64(30)
        x = x * np.uint64(0xBF58476D1CE4E5B9)
        x ^= x >> np.uint64(27)
        x = x * np.uint64(0x94D049BB133111EB)
        x ^= x >> np.uint64(31)
    u = (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)
    return u < train_frac


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
    os.replace(tmp, path)
