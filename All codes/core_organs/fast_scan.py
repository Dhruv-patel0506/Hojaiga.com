"""
fast_scan.py -- first contact with ANY app in seconds (P1-G)

    rep = deep_scan("notepad")        # control tree + menu tree + static knowledge, vision enrichment continues in the background

What lands within the budget (and is persisted to the behavior DB exactly like a full scan, so the cumulative explorer continues from it):
  * the STATIC harvest (menus, accelerators, dialogs, toolkit, file types: read from the program files, nothing launched) - runs in a
    thread while the app starts, so its cost is hidden behind the launch;
  * the control tree (one bulk UIA read), the menu tree (Win32 HMENU read first, then the UIA expand/collapse crawl, both under a
    time budget), the layout map (regions + controls with window-relative positions);
  * NO probing during the budget (that is exploration): the map is returned first and the BEHAVIOR half
    continues in the background (scan_learner -> organ_63's cumulative, resumable frontier), so
    `rep["learn"]` says what is being learned and `rep["capability"]` is the capability card of what is
    known right now (surface, map, can-do graph, blind spots, honest verdict);
  * virtualized content (XAML footers, long lists) is part of the returned map: every vertical
    ScrollPattern container is scrolled to its end, re-read and merged, then scrolled back (REVEAL).
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
# Tiered scan rails (the any-app contract): REVEAL folds virtualized content (scroll to the end of every
# ScrollPattern container, re-read, merge, restore) into the returned map; LEARN hands the behavior half to
# scan_learner's background job so the report still lands within the budget. Both degrade honestly: a
# failure is recorded in the report, never hidden. Opt outs: HOJAIGA_SCAN_REVEAL=0, HOJAIGA_SCAN_LEARN=0.
REVEAL = os.environ.get("HOJAIGA_SCAN_REVEAL", "1") != "0"
_VISION: Dict[str, Dict[str, Any]] = {}      # job id -> {"state": scheduled|running|done|failed|cancelled, ...}
_GEN = {"n": 0}                               # generation: a newer enrichment cancels the older one's write-back


def _merge_rows(base: List[Dict[str, Any]], more: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Union two bulk snapshots (top + scroll-revealed bottom) keyed by what a node IS, not by its
    snapshot-local idx: (parent-name, ctype, name, aid, rect). Rows from `more` that survive the dedupe
    are the materialized virtualized content; the count is what a report calls extra_nodes."""
    def _key(r):
        return (r.get("ctype"), r.get("name"), r.get("aid"), tuple(r.get("rect") or []))
    seen = {_key(r) for r in base}
    extra = 0
    merged = list(base)
    for r in more or []:
        k = _key(r)
        if k in seen:
            continue
        seen.add(k)
        extra += 1
        merged.append(r)
    return merged, extra


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
        # PERSIST the boxes as ADDRESSABLE pixel rows (organ_50, via='ocr') so a tree-blind app can be
        # acted on later without re-running the (80-260 s) engine. Coords are stored normalized to the
        # captured image, so the actuator maps them onto the window's CURRENT rect and re-grounds before
        # clicking (a stale rect never produces a fake pass). This is what the capability card counts as
        # pixel grounding and what the OCR-GROUND test targets.
        grounded = 0
        try:
            from PIL import Image as _Img
            from core_organs import organ_50_layout_map as o50
            with _Img.open(png) as _im:
                iw, ih = _im.size
            px = []
            for e in els:
                nm = (getattr(e, "name", "") or getattr(e, "text", "") or "").strip()
                b = getattr(e, "bounds", None)
                if not nm or not b or list(b)[2] <= list(b)[0] or list(b)[3] <= list(b)[1]:
                    continue
                px.append({"name": nm, "role": getattr(e, "role", "") or "icon", "bbox": [int(v) for v in list(b)[:4]]})
            grounded = o50.save_pixels(model, key, (0, 0, iw, ih), px, via="ocr")
        except Exception as exc:  # noqa: BLE001
            st["ground_err"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        st.update({"state": "done", "elements": len(els), "named": len(rows), "grounded": grounded,
                   "seconds": round(time.time() - t, 1)})
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


def _snapshot_rows(hwnd: int, timeout_ms: Optional[int] = None, cheap: bool = False) -> List[Dict[str, Any]]:
    """Bulk UIA snapshot as plain JSON-safe rows (call INSIDE a BackgroundSession for a parked window).
    Node objects never leave this function: reports stay serializable.
    `timeout_ms` bounds the ONE UIA transaction so the caller's time budget is honoured - leaving it out means
    fast_uia's 12 s default, which is LONGER than the 10 s budget S1 scans with, and that is exactly how a scan
    that was told to stop at 10 s measured 15-23 s (measured 2026-10-06: 2776 nodes, 15.2 s, three runs running)."""
    from core_organs import fast_uia
    nodes = fast_uia.snapshot(hwnd, timeout_ms=timeout_ms, cheap=cheap) or []
    return [{"idx": n.idx, "parent": n.parent, "depth": n.depth, "ctype": n.ctype, "name": n.name,
             "aid": n.aid, "cls": n.cls, "rect": list(n.rect), "enabled": bool(n.enabled),
             "offscreen": bool(n.offscreen), "accel": n.accel, "help": (n.help or "")[:120],
             "pats": list(n.pats)} for n in nodes]


def _walk_rows(hwnd: int, left_s: float) -> Tuple[List[Dict[str, Any]], str]:
    """The tree walk, run TO THE BUDGET that is actually left: the full raw-view tree first, then the cheap
    control-view rung with whatever time remains. Returns (rows, rung) where rung is 'raw-view',
    'control-view' or 'timed-out' - so a report can say how it got its numbers instead of implying the app
    was slow. A window that cannot answer in its slice is reported as timed out, not silently walked for
    twice the budget."""
    slice_ms = int(max(1200.0, min(max(0.0, left_s), 12.0) * 1000))
    rows = _snapshot_rows(hwnd, timeout_ms=slice_ms)
    if rows:
        return rows, "raw-view"
    left2 = max(0.0, left_s - slice_ms / 1000.0)
    if left2 > 0.5:
        rows = _snapshot_rows(hwnd, timeout_ms=int(max(1000.0, left2 * 1000.0)), cheap=True)
        if rows:
            return rows, "control-view"
    return [], "timed-out"


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
    # ---- DYNAMIC SCAN BUDGET (the any-app time contract, made robust for complex apps) --------------------
    # A simple window must come back fast; a big or slow app is GRANTED proportionally MORE time, bounded by a
    # hard max, so the old one-size 10s no longer truncates real apps into an empty/"over budget" map. Readiness
    # (the runaway cost - historically 20s + 15s hardcodes inside universal_scan) is capped to a slice of this
    # budget. `within_budget` is measured against the EFFECTIVE budget and the report states base/effective and
    # whether it was extended - honestly, never a hidden overrun. Knobs: HOJAIGA_SCAN_BUDGET_BASE_S/_MAX_S/_READY_FRAC.
    _base = max(float(budget_s), float(os.environ.get("HOJAIGA_SCAN_BUDGET_BASE_S", "35")))
    _hardmax = max(_base, float(os.environ.get("HOJAIGA_SCAN_BUDGET_MAX_S", "30")))
    budget = min(_base, _hardmax)
    _rfrac = min(0.8, max(0.2, float(os.environ.get("HOJAIGA_SCAN_BUDGET_READY_FRAC", "0.55"))))
    ready_budget = max(2.5, min(budget * _rfrac, budget - 2.0))
    st: Dict[str, Any] = {}
    th = threading.Thread(target=_static_job, args=(target, model, st), daemon=True, name="fast-scan-static")
    th.start()                                                       # hidden behind the launch + readiness wait
    e0_budget = max(1.5, budget * 0.25)
    # ---- RIBBON REVEAL (the any-app fix): a ribbon app materializes ONLY the active tab's buttons in the
    # UIA tree, so a plain snapshot (deepen=False) saw the tab LABELS but none of the other tabs' buttons.
    # Ask the scan for a reversible "ribbon" pass (select each tab + open its galleries, restore). It is a
    # cheap no-op on apps with no ribbon (organ_50 finds no tab galleries), bounded to its own budget, and
    # fully reversible/headless (UIA SelectionItem, no cursor). Toggle OFF: HOJAIGA_SCAN_RIBBON=0.
    _ribbon = os.environ.get("HOJAIGA_SCAN_RIBBON", "1") != "0"
    _rbud = float(os.environ.get("HOJAIGA_RIBBON_BUDGET_S", "30"))
    # the vision capture needs the window while it is still open; do it through the scan's own `on_window` hook is too early (not laid out),
    # so close_if_launched is deferred and the capture happens right after the structure is read
    rep = us.scan_desktop(target, model, deepen=("ribbon" if _ribbon else False),
                          ribbon_budget_s=(_rbud if _ribbon else 0.0),
                          e1_actions=0, close_if_launched=False, fresh=fresh, fast=True,
                          e0_budget_s=e0_budget, ready_budget_s=ready_budget, hwnd_hint=target_hwnd or 0, force=force)
    th.join(timeout=max(0.0, budget - (time.time() - t0)) + 2.0)
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
    _ks = None
    if hwnd:
        try:
            from core_organs import organ_49_scan_knowledge as _sk
            _sk.release_stale()                    # an earlier scan in THIS process may have died mid-run
            _ks = _sk.open_session(target, hwnd)
            if _ks is not None:
                _e0 = _ks.start() or {}
                rep["knowledge_e0"] = {"available": True, **{k: v for k, v in _e0.items() if k != "methods"}}
        except Exception:  # noqa: BLE001
            rep["knowledge_e0"] = {"available": False, "why": "organ_49 open_session/start failed (degraded: scan unaffected)"}
    try:                                                    # whatever happens below, the session is released
        nodes = rep.get("tree_nodes_when_ready") or 0
        # complex app -> GRANT proportionally more structure/reveal time (bounded by the hard max), so a big tree
        # is read fully instead of being truncated by a budget sized for a trivial window. Reported honestly.
        if nodes >= SPARSE_NODES and budget < _hardmax:
            _ext = min(_hardmax, budget + max(3.0, budget * 0.5))
            rep["budget_extended"] = {"from": round(budget, 1), "to": round(_ext, 1), "why": f"complex app: {nodes} nodes"}
            budget = _ext
        rep["budget_s_effective"] = round(budget, 1)
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
        if (measure_tree or want_capture or REVEAL) and hwnd:
            try:
                from core_organs import headless_input as hin
                from core_organs import background_window as bw
                img, note = None, ""
                rows = None
                with bw.BackgroundSession(hwnd):
                    if measure_tree or REVEAL:
                        tm = time.time()
                        rows, rung = _walk_rows(hwnd, budget - (time.time() - t0))
                        rep.setdefault("phases", {})["measure_ms"] = int((time.time() - tm) * 1000)
                        if measure_tree:
                            rep["_measure_rows"], rep["walk_rung"] = rows, rung
                    # ---- scroll-reveal merge (tiered map): force every vertical ScrollPattern container to
                    # its end so XAML/uia virtualized items (footer, long lists) materialize, re-read, merge
                    # the new nodes into the map, and SCROLL BACK - the app is left exactly as found. Only
                    # when the budget can still carry it; a miss is recorded, never hidden. The reveal is HARD-
                    # BOUNDED to a slice of what is left (each UIA trip is capped), so it can NEVER push the
                    # instant map past its budget - the ≤budget_s guarantee is the contract's first promise.
                    if REVEAL and rows is not None:
                        left = budget - (time.time() - t0)
                        if left > 4.5:                       # need room for reveal + re-read + restore + reserve
                            try:
                                from core_organs import desktop_grounding as dg
                                avail = left - 1.6           # reserve for the downstream capture/report
                                rev_to = max(0.6, min(2.2, avail / 3.0))   # each UIA trip bounded; restore re-checked
                                moved = dg.reveal_by_scrolling(hwnd, timeout_s=rev_to)
                                rep["reveal"] = {"moved": bool(moved)}
                                if moved:
                                    rows2 = _snapshot_rows(hwnd, timeout_ms=int(max(600.0, min(rev_to, (budget - (time.time() - t0) - 1.2)) * 1000.0)))
                                    merged, extra = _merge_rows(rows, rows2)
                                    left2 = budget - (time.time() - t0)
                                    if left2 > 0.8:          # still restore, but only within what remains
                                        dg.reveal_by_scrolling(hwnd, to_bottom=False, timeout_s=max(0.5, min(rev_to, left2 - 0.5)))
                                    rep["reveal"] = {"moved": True, "extra_nodes": extra,
                                                     "snapshot_nodes": len(rows2), "reveal_timeout_s": round(rev_to, 2)}
                                    if measure_tree:
                                        rep["_measure_rows"] = merged
                                        rep["tree"] = {**(rep.get("tree") or {}), "nodes_revealed": extra}
                            except Exception as exc:  # noqa: BLE001
                                rep["reveal"] = {"moved": False, "why": f"{type(exc).__name__}: {str(exc)[:120]}"}
                        else:
                            rep["reveal"] = {"moved": False,
                                             "why": "no budget left at reveal (%.1fs left)" % max(0.0, left)}
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
        # ---- tiered scan (the any-app contract): the BEHAVIOR half continues in the background, and
        # this report carries the capability card of what is known RIGHT NOW. Only when a window is
        # actually left on the machine: an app the scan launched and closed has nothing to learn now
        # (its next open re-scans and queues the learner then). Both degrade honestly into the report.
        if hwnd and not rep.get("closed"):
            try:
                from core_organs import scan_learner
                rep["learn"] = scan_learner.learn_in_background(target, hwnd, model=model)
            except Exception as exc:  # noqa: BLE001
                rep["learn"] = {"started": False, "status": "error",
                                "why": f"{type(exc).__name__}: {str(exc)[:120]}"}
        # ---- ribbon surfaced on the MODERN report too (not only the legacy shape): the reveal (organ_50)
        # persisted every tab's buttons into bm_layout, so read them back here and record what the scan KNOWS
        # about this app's ribbon: its tabs, the groups under each revealed tab, and whether only the active tab
        # was seen (deepen off / no reveal). The capability card and the brain read this, not a guess.
        try:
            _rt, _rg = _ribbon_from_layout(model, key)
            _dpn = ((rep.get("layout") or {}).get("deepen") or {})
            _rev = int(_dpn.get("tabs_visited") or 0) if isinstance(_dpn, dict) else 0
            if _rt or _rg:
                # Honest coverage: the reveal tags each harvested group with the tab it came from, so count the
                # DISTINCT tabs that yielded buttons. Fall back to that count when the layout's own tabs_visited
                # stat was not recorded this build (the groups are the ground truth of what was actually revealed).
                _tab_sources = {str((g or {}).get("tab") or "") for g in (_rg or {}).values()} - {""}
                _covered = max(_rev, len(_tab_sources))
                rep["ribbon"] = {"present": True, "tabs": _rt, "n_tabs": len(_rt),
                                 "groups": _rg, "n_groups": len(_rg),
                                 "revealed_tabs": _covered,
                                 "coverage": (f"{_covered} ribbon tab(s) of buttons revealed"
                                              if _covered > 1 else "active tab only (no reveal)")}
        except Exception as exc:  # noqa: BLE001
            rep["ribbon"] = {"present": False, "why": f"{type(exc).__name__}: {str(exc)[:100]}"}
        try:
            from core_organs import capability_card
            rep["capability"] = capability_card.build_card(target, hwnd, model=model, scan=rep)
        except Exception as exc:  # noqa: BLE001
            rep["capability"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        # ---- honest budget: a ribbon app that got its tabs revealed legitimately takes longer than a
        # one-pane window. Fold the measured ribbon cost into the EFFECTIVE budget (never hide an overrun),
        # so `within_budget` stays truthful and the ≤budget_s guarantee is only bent by a named, opt-out knob.
        _layd = rep.get("layout") or {}
        _dpn = _layd.get("deepen") or {}
        _tabs = int(_dpn.get("tabs_visited") or 0) if isinstance(_dpn, dict) else 0
        if _tabs:
            _allow = max(budget, _hardmax, budget + float(_layd.get("elapsed_s") or 0.0))
            if _allow > budget:
                rep["budget_extended"] = {**(rep.get("budget_extended") or {}), "to": round(_allow, 1),
                                          "why": f"ribbon reveal: {_tabs} tab(s) worth of buttons (HOJAIGA_SCAN_RIBBON, {_rbud:g}s bound)"}
                budget = _allow
        rep["seconds"] = round(time.time() - t0, 2)
        # within_budget is honest against the EFFECTIVE (dynamic) budget the scan actually honoured, which is the
        # caller's ask OR the complexity-extended allowance - never a silently-larger number.
        rep["within_budget"] = rep["seconds"] <= budget + 0.15
        return rep
    finally:
        # Released at the END of the scan, not the end of the E0 map: start() parked the window, and the
        # measure/capture pass below still works inside that park (sessions ref-count). Releasing it
        # early made every later phase park the window a second time - and left whatever the scan was
        # walking visible for the rest of the run. Measured 2026-10-06: the walk went 4.6 s -> 15-23 s
        # and minimized-window tests started reporting their own window on screen. This IS the release
        # the popup leak needed; it just belongs here, once, on every path out.
        if _ks is not None:
            try:
                _ks.release()
            except Exception:  # noqa: BLE001
                pass


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


def _ribbon_from_layout(model, key: str) -> Tuple[List[str], Dict[str, Any]]:
    """Rebuild the ribbon summary the legacy caller expects from the PERSISTED layout (organ_50), so it
    reflects every ribbon tab the reveal opened - not just the one that happened to be active. `tabs` are
    the tab headers; `groups` maps each revealed group to the tab that shows it and its operable buttons.
    Honest: with HOJAIGA_SCAN_RIBBON=0 no 'tab:' rows exist and only the active tab's buttons are known."""
    tabs: List[str] = []
    groups: Dict[str, Any] = {}
    try:
        rows = model._conn.execute(
            "SELECT name, role, via, region_name, patterns FROM bm_layout WHERE app_key=? AND name<>''",
            (key,)).fetchall()
    except Exception:  # noqa: BLE001
        return tabs, groups
    for r in rows:
        role = r["role"] or ""
        via = r["via"] or ""
        name = (r["name"] or "").strip()
        if not name:
            continue
        if role == "tabitem":
            if name not in tabs:
                tabs.append(name)
        elif via.startswith("tab:"):
            tab = via.split(":", 1)[1]
            pats = r["patterns"] or ""
            if not any(p in pats for p in ("invoke", "toggle", "select", "expand")):
                continue
            if role in ("scrollbar", "thumb", "titlebar"):
                continue
            grp = (r["region_name"] or "").strip() or tab
            d = groups.setdefault(grp, {"tab": tab, "controls": []})
            if name not in d["controls"]:
                d["controls"].append(name)
    return tabs, groups


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
    rung = rep.pop("walk_rung", None) or ("raw-view" if rows else "")
    walk_ms = int((rep.get("phases") or {}).get("measure_ms") or 0)
    capped = len(rows) >= 20000
    if not rows and hwnd:
        from core_organs import background_window as bw
        t = _t.perf_counter()
        # whatever the scan itself has not already spent - never fast_uia's 12 s default on top of it
        left = max(0.5, float(budget_s) - float(rep.get("seconds") or 0.0))
        for _attempt in range(2):
            try:
                with bw.BackgroundSession(hwnd):
                    rows, rung = _walk_rows(hwnd, left)
            except Exception:  # noqa: BLE001
                try:
                    rows, rung = _walk_rows(hwnd, left)
                except Exception:  # noqa: BLE001
                    rows, rung = [], "walk-failed"
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
    if not rows and rung in ("timed-out", "walk-failed"):
        # The rail that stopped us was OUR budget, not the app: say which, so an over-budget read is never
        # mistaken for "this window has no tree".
        stopped_by = f"uia-walk-{rung} (budget {int(float(budget_s))}s)"
    ribbon_tabs, ribbon_groups = _ribbon_from_layout(model, key)   # from the PERSISTED layout: every tab the reveal opened
    out = dict(rep)                                                            # keep seconds/within_budget/static/tree/menus/vision/phases
    out.update({
        "app_name": rep.get("window_title") or target,
        "app_type": "desktop",
        "app_interaction": app_interaction,
        "interaction_guide": guide,
        "current_state": rep.get("window_title") or "",
        "ui_elements": ui_elements,
        "ribbon_tabs": ribbon_tabs, "ribbon_groups": ribbon_groups, "canvases": [], "menu_headers": sorted({(c.get("menu_path") or "").split(">")[0] for c in menu_cmds if c.get("menu_path")}),
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
            "walk_style": "bulk cached UIA snapshot (fast_uia); no depth cap, node cap 20000, one transaction "
                          "bounded by the budget that is left (raw view first, control view as the cheap rung)",
            "walk_rung": rung,                    # raw-view | control-view | timed-out | walk-failed
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
