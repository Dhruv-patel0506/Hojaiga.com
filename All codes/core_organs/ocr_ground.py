"""
ocr_ground - addressable pixel targets for tree-blind apps (plan section B).

A tree-blind surface (WhatsApp / Office / a canvas) exposes few or no UIA controls, so its buttons are
found only by pixels (OCR / vision). ``fast_scan`` persists those boxes as organ_50 ``via='ocr'`` rows,
normalized to the window they were captured from. This module turns a persisted box back into a LIVE,
SAFE click:

  * the stored rect is window-RELATIVE, so it is mapped onto the window's CURRENT rect (a move/reflow
    does not aim the click at a stale pixel);
  * before posting, the target is RE-GROUNDED: a fresh OCR pass (when the engine is present) re-locates
    the label by name and wins over the cached rect;
  * the click is delivered as POSTED window messages only (headless_input) and verified by pixel change;
    no pixel change is reported honestly as delivered-but-INEFFECTIVE, never as a pass.

Product law: the physical cursor never moves; a stale rect is never clicked blindly.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.ocr_ground")


def _rows(model, app_key: str, via: str = "") -> List[Dict[str, Any]]:
    try:
        from core_organs import organ_50_layout_map as o50
        return o50.pixel_rows(model, app_key, via)
    except Exception:  # noqa: BLE001
        return []


def find_pixel(model, app_key: str, name: str, via: str = "") -> Optional[Dict[str, Any]]:
    """The stored pixel row whose label best matches `name` (exact first, then substring)."""
    target = (name or "").strip().lower()
    if not target:
        return None
    rows = _rows(model, app_key, via)
    exact = [r for r in rows if (r["name"] or "").strip().lower() == target]
    if exact:
        return exact[0]
    sub = [r for r in rows if target in (r["name"] or "").lower() or (r["name"] or "").lower() in target]
    return sub[0] if sub else None


def reground_center(root: int, name: str, rel: Optional[Tuple[float, float, float, float]] = None,
                    *, prefer_fresh: bool = True) -> Tuple[Optional[Tuple[int, int]], str]:
    """Where is `name` RIGHT NOW? Returns ((cx, cy), method).

    Method 'ocr-fresh' = a live OCR pass located the label (wins: it is current by construction);
    'cached-rel' = the persisted window-relative box mapped onto the CURRENT window rect (a move-safe
    fallback when OCR is unavailable or missed it); (None, reason) = nothing addressable, so NO click
    should be posted (the caller must not fake a pass)."""
    if not root:
        return None, "no-root-window"
    # 1) live re-ground by OCR: the most truthful source, since it reads the pixels as they are now.
    if prefer_fresh and name:
        try:
            from core_organs import desktop_grounding as dg
            g = dg.DesktopGrounding()
            for e in g._walk_ocr(root):
                if e.name and (name.lower() in e.name.lower() or e.name.lower() in name.lower()):
                    return e.center, "ocr-fresh"
        except Exception as exc:  # noqa: BLE001
            logger.debug("[ocr_ground] fresh OCR re-ground unavailable: %s", exc)
    # 2) cached window-relative rect, scaled to the window's CURRENT rect.
    if rel:
        try:
            from core_organs import desktop_grounding as dg
            bbox = dg._abs_from_rel(rel, root)
            if bbox:
                return ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2), "cached-rel"
        except Exception as exc:  # noqa: BLE001
            logger.debug("[ocr_ground] cached-rel mapping failed: %s", exc)
    return None, "stale-ungroundable"


def pixel_click(root: int, name: str, rel: Optional[Tuple[float, float, float, float]] = None,
                *, verify: bool = True) -> Tuple[bool, str]:
    """Click a pixel-found target: re-ground it, post a click to its live center, and confirm pixels changed.
    Honest: a no-change result is reported delivered-but-INEFFECTIVE (ok=False), never a pass."""
    from core_organs import headless_input as hin
    center, method = reground_center(root, name, rel)
    if center is None:
        return False, f"{hin.UNDELIVERABLE}: pixel target '{name}' could not be re-grounded ({method}); refused to click a stale rect"
    cx, cy = int(center[0]), int(center[1])
    before, _w = hin.capture_window(root) if verify else (None, "")
    ok, note = hin.post_click(root, cx, cy)
    if not ok:
        return False, note
    if not verify:
        return True, f"{note} [{method}, unverified]"
    time.sleep(0.35)
    after, _w2 = hin.capture_window(root)
    try:
        n, _bbox = hin.changed_pixels(before, after)
    except Exception:  # noqa: BLE001
        n = -1
    if n == 0:
        return False, f"delivered but INEFFECTIVE: '{name}' posted via {method} changed no pixels"
    tag = f"{n}px changed" if n > 0 else "change unreadable"
    return True, f"{note} [{method}, {tag}]"
