"""
fast_scan.py -- first contact with ANY app in seconds (P1-G)

    rep = deep_scan("notepad")        # control tree + menu tree + static knowledge, vision enrichment continues in the background

What lands within the budget (and is persisted to the behavior DB exactly like a full scan, so the cumulative explorer continues from it):
  * the STATIC harvest (menus, accelerators, dialogs, toolkit, file types: read from the program files, nothing launched) - runs in a
    thread while the app starts, so its cost is hidden behind the launch;
  * the control tree (one bulk UIA read), the menu tree (Win32 HMENU read first, then the UIA expand/collapse crawl, both under a
    time budget), the layout map (regions + controls with window-relative positions);
  * NO probing (that is exploration, `master()`, cumulative and resumable).
Vision enrichment is the slow part (OmniParser on CPU: 80-260 s). It runs AFTER the structure is returned, in a daemon thread, and only
when the UIA tree is sparse (a canvas / Chromium app): `rep["vision"]` says 'not needed', 'scheduled' or why not, and
`wait_for_vision(rep, timeout)` collects the result. It never blocks the caller and never claims results it does not have.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

SPARSE_NODES = 25            # a UIA tree smaller than this is "sparse": the visible content is probably not in it
_VISION: Dict[str, Dict[str, Any]] = {}      # job id -> {"state": scheduled|running|done|failed|cancelled, ...}
_GEN = {"n": 0}                               # generation: a newer enrichment cancels the older one's write-back


def _static_job(name: str, model, out: Dict[str, Any]) -> None:
    t = time.time()
    try:
        from core_organs import static_knowledge as sk
        from core_organs import organ_48_app_behavior_model as bm
        d = sk.harvest(name)
        out["static"] = {"ok": d.get("ok"), "commands": len(d.get("commands", [])), "dialogs": len(d.get("dialogs", [])),
                         "toolkit": [f["id"] for f in d.get("frameworks", [])][:3], "file_types": len(d.get("file_types", [])),
                         "elapsed_s": d.get("elapsed_s")}
        if d.get("ok"):
            out["static"]["ingested"] = sk.ingest(model, name, d, version_hash=bm.app_version_hash(d.get("exe", "")))
    except Exception as exc:  # noqa: BLE001
        out["static"] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:100]}"}
    out["static_s"] = round(time.time() - t, 2)


def _vision_job(job: str, gen: int, png: str, model, key: str) -> None:
    st = _VISION[job]
    st["state"] = "running"
    t = time.time()
    try:
        from core_organs import desktop_grounding as dg
        parser = dg.DesktopGrounding._get_vision_parser()
        if parser is None:
            st.update({"state": "failed", "why": "vision parser unavailable (torch / local OmniParser repo missing)"})
            return
        els = parser.parse_screenshot(png) or []
        if gen != _GEN["n"]:
            st.update({"state": "cancelled", "why": "a newer enrichment superseded this one"})
            return
        rows = [{"name": getattr(e, "name", "") or getattr(e, "text", "") or "", "type": getattr(e, "role", "") or "icon"} for e in els]
        rows = [r for r in rows if r["name"]]
        model.record_region(key, "vision:enrichment", rows[:400], via="fast_scan:vision")
        st.update({"state": "done", "elements": len(els), "named": len(rows), "seconds": round(time.time() - t, 1)})
    except Exception as exc:  # noqa: BLE001
        st.update({"state": "failed", "why": f"{type(exc).__name__}: {str(exc)[:120]}"})
    finally:
        try:
            os.remove(png)
        except OSError:
            pass


def wait_for_vision(rep: Dict[str, Any], timeout_s: float = 0.0) -> Dict[str, Any]:
    job = (rep.get("vision") or {}).get("job")
    if not job or job not in _VISION:
        return rep.get("vision") or {}
    end = time.time() + timeout_s
    while time.time() < end and _VISION[job]["state"] in ("scheduled", "running"):
        time.sleep(0.5)
    return dict(_VISION[job])


def deep_scan(target: str, model=None, *, budget_s: float = 10.0, vision: bool = True, close_if_launched: bool = True,
              fresh: bool = True, hold_for_vision_capture: bool = True) -> Dict[str, Any]:
    """First-contact structure of `target` (an app name) within `budget_s`; see the module doc. Returns the scan report plus
    {'seconds', 'within_budget', 'static', 'tree': {...}, 'menus': {...}, 'vision': {...}}."""
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import universal_scan as us
    model = model or bm.get_model()
    key = bm._app_key(target)
    t0 = time.time()
    st: Dict[str, Any] = {}
    th = threading.Thread(target=_static_job, args=(target, model, st), daemon=True, name="fast-scan-static")
    th.start()                                                       # hidden behind the launch + readiness wait
    e0_budget = max(1.5, budget_s * 0.25)
    # the vision capture needs the window while it is still open; do it through the scan's own `on_window` hook is too early (not laid out),
    # so close_if_launched is deferred and the capture happens right after the structure is read
    rep = us.scan_desktop(target, model, deepen=False, e1_actions=0, close_if_launched=False, fresh=fresh, fast=True, e0_budget_s=e0_budget)
    th.join(timeout=max(0.0, budget_s - (time.time() - t0)) + 2.0)
    rep["static"] = st.get("static", {"ok": False, "error": "static harvest did not finish"})
    rep["phases"]["static_s(parallel)"] = st.get("static_s")
    hwnd = 0
    try:
        from core_organs import desktop_grounding as dg
        hwnd = dg.DesktopGrounding().find_window(target) or 0
    except Exception:  # noqa: BLE001
        hwnd = 0
    nodes = rep.get("tree_nodes_when_ready") or 0
    lay = rep.get("layout") or {}
    rep["tree"] = {"nodes": nodes, "controls_mapped": lay.get("controls"), "regions": lay.get("regions"), "sections": len(rep.get("sections") or [])}
    cmds = model.commands(key, limit=5000)
    menu_cmds = [c for c in cmds if (c.get("menu_path") or "").count(">") >= 0 and (c.get("origin") or "").startswith(("e0:", "static:"))]
    rep["menus"] = {"commands": len(menu_cmds), "with_path": sum(1 for c in menu_cmds if ">" in (c.get("menu_path") or "")),
                    "methods": [m.get("method") for m in (rep.get("e0", {}).get("methods") or [])]}
    # ---- vision enrichment: only for a sparse tree, never blocking
    rep["vision"] = {"state": "skipped"}
    if not vision:
        rep["vision"] = {"state": "disabled by the caller"}
    elif nodes >= SPARSE_NODES:
        rep["vision"] = {"state": "not needed", "why": f"the UIA tree is rich ({nodes} nodes): vision would only repeat it"}
    elif not hwnd:
        rep["vision"] = {"state": "skipped", "why": "no window to capture"}
    else:
        try:
            from core_organs import headless_input as hin
            from core_organs import background_window as bw
            with bw.BackgroundSession(hwnd):
                time.sleep(0.5)
                img, note = hin.capture_window(hwnd)
            if img is None:
                rep["vision"] = {"state": "skipped", "why": f"capture failed ({note})"}
            else:
                png = os.path.join(os.environ.get("TEMP", "."), f"hj_fs_{uuid.uuid4().hex[:8]}.png")
                img.save(png, format="PNG")
                _GEN["n"] += 1
                job = f"v{_GEN['n']}"
                _VISION[job] = {"state": "scheduled", "app": key}
                threading.Thread(target=_vision_job, args=(job, _GEN["n"], png, model, key), daemon=True, name="fast-scan-vision").start()
                rep["vision"] = {"state": "scheduled", "job": job, "why": f"sparse UIA tree ({nodes} nodes): OmniParser runs in the background"}
        except Exception as exc:  # noqa: BLE001
            rep["vision"] = {"state": "skipped", "why": f"{type(exc).__name__}: {str(exc)[:100]}"}
    if rep.get("launch", {}).get("launched") and close_if_launched and hwnd:
        rep["closed"] = us.close_window(hwnd)
    rep["seconds"] = round(time.time() - t0, 2)
    rep["within_budget"] = rep["seconds"] <= budget_s
    return rep
