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
from typing import Any, Dict, List, Optional, Tuple

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


def _snapshot_rows(hwnd: int) -> List[Dict[str, Any]]:
    """Bulk UIA snapshot as plain JSON-safe rows (call INSIDE a BackgroundSession for a parked window).
    Node objects never leave this function: reports stay serializable."""
    from core_organs import fast_uia
    nodes = fast_uia.snapshot(hwnd) or []
    return [{"idx": n.idx, "parent": n.parent, "depth": n.depth, "ctype": n.ctype, "name": n.name,
             "aid": n.aid, "cls": n.cls, "rect": list(n.rect), "enabled": bool(n.enabled),
             "offscreen": bool(n.offscreen), "accel": n.accel, "help": (n.help or "")[:120],
             "pats": list(n.pats)} for n in nodes]


def deep_scan(target: str, model=None, *, budget_s: float = 10.0, vision: bool = True, close_if_launched: bool = True,
              fresh: bool = True, hold_for_vision_capture: bool = True, target_hwnd: int = 0,
              force: bool = False, measure_tree: bool = False) -> Dict[str, Any]:
    """First-contact structure of `target` (an app name) within `budget_s`; see the module doc. Returns the scan report plus
    {'seconds', 'within_budget', 'static', 'tree': {...}, 'menus': {...}, 'vision': {...}}.
    `target_hwnd` > 0: scan THAT exact window (hot callers that already resolved the handle); it is treated as a
    pre-existing window — reused, never re-launched, never closed by us."""
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
    rep = us.scan_desktop(target, model, deepen=False, e1_actions=0, close_if_launched=False, fresh=fresh, fast=True,
                          e0_budget_s=e0_budget, hwnd_hint=target_hwnd or 0, force=force)
    th.join(timeout=max(0.0, budget_s - (time.time() - t0)) + 2.0)
    rep["static"] = st.get("static", {"ok": False, "error": "static harvest did not finish"})
    rep["phases"]["static_s(parallel)"] = st.get("static_s")
    hwnd = int(target_hwnd or 0) or int(rep.get("hwnd") or 0)          # the scan's own window; never re-resolved by name (could hit the user's)
    if not hwnd:
        try:
            from core_organs import desktop_grounding as dg
            found = dg.DesktopGrounding().find_window(target)
            hwnd = found if isinstance(found, int) else 0
        except Exception:  # noqa: BLE001
            hwnd = 0
    # --- knowledge side by side (organ_49): cheap READ-ONLY E0 front-load only (app-version check demotes stale
    # trust; menu tree + accelerators; skip_known de-dup). open_session returns None when organ_48/UIA are
    # unavailable -> the scan runs exactly as before. NO probing here (that stays cumulative in master()).
    rep["knowledge_e0"] = {"available": False}
    if hwnd:
        try:
            from core_organs import organ_49_scan_knowledge as _sk
            _ks = _sk.open_session(target, hwnd)
            if _ks is not None:
                _e0 = _ks.start() or {}
                rep["knowledge_e0"] = {"available": True, **{k: v for k, v in _e0.items() if k != "methods"}}
        except Exception:  # noqa: BLE001
            rep["knowledge_e0"] = {"available": False, "why": "organ_49 open_session/start failed (degraded: scan unaffected)"}
    nodes = rep.get("tree_nodes_when_ready") or 0
    lay = rep.get("layout") or {}
    rep["tree"] = {"nodes": nodes, "controls_mapped": lay.get("controls"), "regions": lay.get("regions"), "sections": len(rep.get("sections") or [])}
    cmds = model.commands(key, limit=5000)
    menu_cmds = [c for c in cmds if (c.get("menu_path") or "").count(">") >= 0 and (c.get("origin") or "").startswith(("e0:", "static:"))]
    rep["menus"] = {"commands": len(menu_cmds), "with_path": sum(1 for c in menu_cmds if ">" in (c.get("menu_path") or "")),
                    "methods": [m.get("method") for m in (rep.get("e0", {}).get("methods") or [])]}
    # ---- final pass, ONE background session: tree measurement (when asked) + async vision enrichment.
    # A parked window virtualizes its content tree away outside its session, so both must share it.
    rep["vision"] = {"state": "skipped"}
    rep["_measure_rows"] = None
    want_capture = False
    if not vision:
        rep["vision"] = {"state": "disabled by the caller"}
    elif nodes >= SPARSE_NODES:
        rep["vision"] = {"state": "not needed", "why": f"the UIA tree is rich ({nodes} nodes): vision would only repeat it"}
    elif not hwnd:
        rep["vision"] = {"state": "skipped", "why": "no window to capture"}
    else:
        want_capture = True
    if (measure_tree or want_capture) and hwnd:
        try:
            from core_organs import headless_input as hin
            from core_organs import background_window as bw
            img, note = None, ""
            with bw.BackgroundSession(hwnd):
                if measure_tree:
                    tm = time.time()
                    rep["_measure_rows"] = _snapshot_rows(hwnd)
                    rep.setdefault("phases", {})["measure_ms"] = int((time.time() - tm) * 1000)
                if want_capture:
                    time.sleep(0.5)
                    img, note = hin.capture_window(hwnd)
            if not want_capture:
                pass                                   # measurement only; vision state already reported above
            elif img is None:
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
        from core_organs import background_window as bw2
        rep["closed"] = bool(bw2.is_ours(hwnd)) and us.close_window(hwnd)   # only a window THIS process launched can be closed by us
    rep["seconds"] = round(time.time() - t0, 2)
    rep["within_budget"] = rep["seconds"] <= budget_s
    return rep


# ---------------------------------------------------------------- legacy-shape adapter
#
# organ_01 (CrewAI scan tools) and organ_10 (DEEP_SCAN task) were built against the serial organ_30 result dict
# (tree_stats.{nodes_walked,max_depth_seen,walk_max_depth}, total_elements/total_controls/total_menu_items, ui_elements[]).
# They now run on THIS fast scanner; `deep_scan_legacy_shape` maps the modern report onto those exact keys so no caller
# and no S1 assertion has to change semantics. Nothing is faked: fields the modern pipeline does not produce (a depth
# cap, per-app VLM notes) are reported honestly as absent, and `vision` stays async (`wait_for_vision` collects it).

_ACTIONABLE = {"invoke", "toggle", "expand", "select"}


def _ui_elements_from_snapshot(rows) -> Tuple[List[Dict[str, Any]], int]:
    """Generic (no per-app rules) element list from snapshot rows (see _snapshot_rows), legacy-compatible shape."""
    els, controls = [], 0
    for n in rows:
        pats = set(n["pats"]) & _ACTIONABLE
        if not n["name"] and not pats:
            continue
        role = n["ctype"].replace("Control", "").lower()
        if role in ("titlebar", "tooltip", "scrollbar", "separator"):
            continue
        actionable = bool(pats) and n["enabled"]
        if actionable:
            controls += 1
        x0, y0, x1, y1 = n["rect"]
        el = {"name": n["name"] or n["aid"] or f"{role}:{n['idx']}", "type": role,
              "purpose": n["help"] or (f"{role} '{n['name']}'" if n["name"] else role),
              "interactable": actionable,
              "keyboard_hint": n["accel"] or "",
              "action_hint": "+".join(sorted(pats)),
              "depth": n["depth"]}
        if x1 > x0 and y1 > y0:
            el["coords"] = {"x": (x0 + x1) // 2, "y": (y0 + y1) // 2, "box": [x0, y0, x1, y1]}
        els.append(el)
    return els, controls


def deep_scan_legacy_shape(target: str, target_hwnd: int = 0, *, budget_s: float = 10.0,
                           vision: bool = True, quiet: bool = True, model=None,
                           close_if_launched: bool = False, force: bool = False) -> Dict[str, Any]:
    """Modern first-contact scan returned in the organ_30 deep-scan dict shape (see note above).
    The window is snapshotted BEFORE any auto-close, so stats always describe what was actually walked.
    `close_if_launched` defaults to False (legacy parity: a window the scan had to start stays open for the caller)."""
    import time as _t
    from core_organs import organ_48_app_behavior_model as bm
    rep = deep_scan(target, model=model, budget_s=budget_s, vision=vision, target_hwnd=target_hwnd,
                    fresh=not target_hwnd, close_if_launched=False, force=force, measure_tree=True)
    model = model or bm.get_model()
    key = bm._app_key(target)
    hwnd = int(target_hwnd or 0) or int(rep.get("hwnd") or 0)      # the exact window the scan walked; no name re-resolution
    if not hwnd:
        try:
            from core_organs import desktop_grounding as dg
            found = dg.DesktopGrounding().find_window(target)
            hwnd = found if isinstance(found, int) else 0
        except Exception:  # noqa: BLE001
            hwnd = 0
    # the walk S1 measures: the bulk cached UIA snapshot deep_scan took INSIDE the scan's own background session
    # (a parked/off-screen window virtualizes its content tree away outside a session — Explorer shows 8 nodes there,
    # 460 inside). Fallback: take one here if the scan never got to measure (transient COM errors retried once).
    rows = rep.pop("_measure_rows", None) or []
    walk_ms = int((rep.get("phases") or {}).get("measure_ms") or 0)
    capped = len(rows) >= 20000
    if not rows and hwnd:
        from core_organs import background_window as bw
        t = _t.perf_counter()
        for _attempt in range(2):
            try:
                with bw.BackgroundSession(hwnd):
                    rows = _snapshot_rows(hwnd)
            except Exception:  # noqa: BLE001
                try:
                    rows = _snapshot_rows(hwnd)
                except Exception:  # noqa: BLE001
                    rows = []
            if rows:
                break
            _t.sleep(0.3)
        walk_ms = int((_t.perf_counter() - t) * 1000)
        capped = len(rows) >= 20000
    ui_elements, n_controls = _ui_elements_from_snapshot(rows)
    cmds = model.commands(key, limit=5000)
    menu_cmds = [c for c in cmds if (c.get("origin") or "").startswith(("e0:", "static:")) and (c.get("menu_path") or "")]
    for c in menu_cmds:
        path = c.get("menu_path") or ""
        ui_elements.append({"name": c.get("name", ""), "type": "menuitem",
                            "purpose": f"menu item: {path.replace('>', ' > ')}",
                            "interactable": True, "keyboard_hint": c.get("accelerator", ""),
                            "parent_menu": path.split(">")[0], "action_hint": "menu"})
    has_text = any(e["type"] in ("edit", "document", "text") for e in ui_elements)
    n_buttons = sum(1 for e in ui_elements if e["type"] in ("button", "listitem", "radiobutton"))
    if n_buttons and not has_text:
        app_interaction, guide = "BUTTON_APP", "This is a BUTTON-BASED app. Click buttons by their exact names from the element list; do not type text into it."
    elif has_text:
        app_interaction, guide = "TEXT_APP", "This app has a TEXT INPUT area. Use type/keys and the documented shortcuts."
    else:
        app_interaction, guide = "MIXED_APP", "Mixed controls; choose per element from the scan list."
    stopped_by = rep.get("error") or (rep.get("e0") or {}).get("stopped") or "scan-complete"
    out = dict(rep)                                                            # keep seconds/within_budget/static/tree/menus/vision/phases
    out.update({
        "app_name": rep.get("window_title") or target,
        "app_type": "desktop",
        "app_interaction": app_interaction,
        "interaction_guide": guide,
        "current_state": rep.get("window_title") or "",
        "ui_elements": ui_elements,
        "ribbon_tabs": [], "ribbon_groups": {}, "canvases": [], "menu_headers": sorted({(c.get("menu_path") or "").split(">")[0] for c in menu_cmds if c.get("menu_path")}),
        "blocking_elements": [], "suggested_first_action": "", "automation_notes": "",
        "vlm_description": "",
        "total_controls": n_controls,
        "total_menu_items": len(menu_cmds),
        "total_elements": len(ui_elements),
        "tree_stats": {
            "nodes_walked": len(rows),
            "actionable_controls": n_controls,
            "max_depth_seen": max((r["depth"] for r in rows), default=0),
            # honest: the bulk snapshot has NO depth cap; its only rail is the node ceiling
            "walk_max_depth": 0,
            "walk_style": "bulk cached UIA snapshot (fast_uia); no depth cap, node cap 20000",
            "depth_hit_cap": False,
            "time_budget_ms": int(budget_s * 1000),
            "time_budget_hit": not out.get("within_budget", False),
            "walk_ms": walk_ms,
            "truncated": bool(capped),
            "stopped_by": stopped_by,
            "walk_source": "bulk UIA snapshot inside the window's background session",
        },
        "status": (("partial" if ui_elements else "error") if rep.get("error")
                   else ("success" if ui_elements else "partial")),
        "message": rep.get("error", ""),
        "scan_timestamp": _t.time(),
        "screenshot_b64_length": 0,
        "scanner": "fast_scan.deep_scan_legacy_shape",
    })
    if not rows:
        # HONESTY: the walk FAILED (0 measured nodes) - do not let the pre-walk richness check claim vision was
        # "not needed". A tree we could not read is maximally sparse; report why, never fake a completeness we lack.
        out["vision"] = {"state": "skipped", "why": f"final UIA walk returned 0 nodes ({stopped_by}); richness unverified"}
    if close_if_launched and (rep.get("launch") or {}).get("launched") and hwnd:
        try:
            from core_organs import universal_scan as us
            from core_organs import background_window as bw
            # OWNERSHIP GATE: close only what this process launched - never a window found by name (the user's work).
            out["closed"] = bool(bw.is_ours(hwnd)) and us.close_window(hwnd)
        except Exception:  # noqa: BLE001
            out["closed"] = False
    return out
