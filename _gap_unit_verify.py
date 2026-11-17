"""
_gap_unit_verify -- offline unit checks for the three hardened gaps.

Deterministic: no model calls, no live app. Gap 1 (throttle) is timing-tested
separately by running decompose_guides twice against Ollama (see the session notes).

  python _gap_unit_verify.py
"""
import base64
import io
import random
import sys

from PIL import Image

sys.path.insert(0, ".")
import live_trajectory_executor as LX  # noqa: E402


def _b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def test_crop_and_remap():
    # noisy 1920x1080 "desktop" so PNG payload scales with pixel area (realistic tokens)
    desktop = Image.frombytes("RGB", (1920, 1080),
                              bytes(random.getrandbits(8) for _ in range(1920 * 1080 * 3)))
    full_b64 = _b64(desktop)
    region = [1200, 300, 500, 400]  # a small app window in screen coords

    crop_b64, (cw, ch), offset = LX.prepare_vision_payload(full_b64, region)

    # coordinate remap: crop-local (10,10) -> screen (10+left, 10+top)
    assert LX.remap_vision_coords((10, 10), offset) == (10 + offset[0], 10 + offset[1]), "remap wrong"
    # padded crop must contain the requested box
    assert cw >= 500 and ch >= 400, f"crop too small: {cw}x{ch}"
    drop = 1 - len(crop_b64) / len(full_b64)
    print(f"  Gap3 crop {cw}x{ch} offset={offset} full_px={1920*1080} crop_px={cw*ch} "
          f"b64_drop={drop:.1%}")
    assert drop > 0.70, f"payload size drop only {drop:.1%} (need >70%)"
    print("  PASS Gap3 crop + remap")


def test_crop_no_region():
    desktop = Image.frombytes("RGB", (800, 600), bytes(random.getrandbits(8) for _ in range(800 * 600 * 3)))
    crop_b64, (cw, ch), offset = LX.prepare_vision_payload(_b64(desktop), None)
    assert (cw, ch) == (800, 600) and offset == (0, 0), "no-region must pass whole frame"
    print("  PASS Gap3 no-region passthrough (full-frame fallback)")


def test_vision_region():
    class Rect: rect = (100, 200, 600, 700)
    assert LX._vision_region([Rect()]) == [100, 200, 500, 500]

    class Zero: rect = (0, 0, 0, 0)
    assert LX._vision_region([Zero()]) is None
    assert LX._vision_region([]) is None
    print("  PASS Gap3 region = window root rect, None when unknown")


def test_verify_state_delta():
    base = {"hwnds": [1, 2], "n_nodes": 10, "state_hash": "aaa"}
    # identical state -> no delta (this is what would otherwise be a false negative risk)
    assert LX.verify_state_delta(base, dict(base)) is False
    # PROPERTY-ONLY mutation: same count + same hwnds, only the state hash moves
    # (exactly the Calculator display-value / checkbox-toggle case the shallow diff missed)
    prop = dict(base); prop["state_hash"] = "bbb"
    assert LX.verify_state_delta(base, prop) is True
    # detached modal / context menu on a new root HWND
    modal = dict(base); modal["hwnds"] = [1, 2, 9]
    assert LX.verify_state_delta(base, modal) is True
    # element added/removed (dropdown open)
    grown = dict(base); grown["n_nodes"] = 11
    assert LX.verify_state_delta(base, grown) is True
    print("  PASS Gap2 verify_state_delta catches property-only + HWND + structural changes")


if __name__ == "__main__":
    test_crop_and_remap()
    test_crop_no_region()
    test_vision_region()
    test_verify_state_delta()
    print("\nALL GAP UNIT CHECKS PASSED")
