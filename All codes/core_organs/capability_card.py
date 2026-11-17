"""
capability_card.py — what Hojaiga CAN DO in this app, RIGHT NOW, honestly.

The any-app contract in one dict. Every actor (brain, capsule, report, test) that must answer "will
this work here?" reads THIS instead of guessing from the app's name:

  surface        what kind of pixels/structure this window presents (capability_probe: classic-win32,
                 xaml/winui, chromium/cef, directx/opaque, mixed/unknown) and the wall note if any
  map            the structural map the scan produced: nodes, rung actually reached, sections/regions,
                 whether virtualized content was scroll-revealed
  knowledge      what is KNOWN about behavior: commands by trust (learned > catalog > archetype >
                 distilled), transitions, regions, frontier progress, and the background learner's
                 honest state (pending | learning | partial | complete | stale | failed:<why>)
  can_do         the navigation/action graph extracted FROM the scan itself: menu routes, key chords,
                 learned invokes and what each revealed (transition/region) — "which button leads to
                 what" as data, not as a guess
  blind          what cannot be grounded here (opaque canvas, timed-out walk, unreachable tree) with
                 the reason, and which fallback (OCR/vision tier) covers it
  verdict        one of: actionable | actionable-partial | learning | blind-fallback | not-groundable.
                 NEVER a promise beyond what the rows below it support.

No app name ever enters a decision here: the card is built from measured rows, exactly like the
actuation ladder. A missing tier is reported as missing.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hojaiga.capability_card")

CAN_DO_CAP = int(os.environ.get("HOJAIGA_CARD_CAN_DO_CAP", "60"))


def build_card(target: str, hwnd: int = 0, *, model=None, scan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Assemble the card for `target` (app name). `scan` is the fast_scan report of THIS run when the
    caller has one (it carries the freshest tree/vision/reveal facts); without it the card still
    builds from persisted knowledge + a live probe of `hwnd`."""
    from core_organs import organ_48_app_behavior_model as bm
    model = model or bm.get_model()
    key = bm._app_key(target)

    # ---- knowledge: measure through organ_63's one honest counter (falls back to raw model rows) ----
    knowledge: Dict[str, Any] = {}
    try:
        from core_organs import organ_63_app_mastery as m63
        knowledge = m63.measure(model, key)
    except Exception as exc:  # noqa: BLE001
        try:
            cmds = model.commands(key, limit=5000)
            knowledge = {"commands": len(cmds),
                         "commands_learned": sum(1 for c in cmds if c.get("source") == "learned"),
                         "regions": len(model.regions(key)),
                         "transitions": len(model.transitions(key)),
                         "measure_error": f"{type(exc).__name__}"}
        except Exception as exc2:  # noqa: BLE001
            knowledge = {"measure_error": f"{type(exc2).__name__}: {str(exc2)[:120]}"}

    # ---- learner state ----
    try:
        from core_organs import scan_learner
        learn = scan_learner.status(key, model=model)
    except Exception as exc:  # noqa: BLE001
        learn = {"status": "unknown", "why": f"scan_learner unavailable: {type(exc).__name__}"}

    # ---- surface ----
    surface: Dict[str, Any] = {}
    if hwnd:
        try:
            from core_organs import capability_probe
            surface = capability_probe.probe(hwnd)
        except Exception as exc:  # noqa: BLE001
            surface = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}

    # ---- the map: prefer this run's scan report, else the persisted layout ----
    map_info: Dict[str, Any] = {}
    if scan:
        tree = scan.get("tree") or {}
        map_info = {"nodes": tree.get("nodes") or scan.get("tree_nodes_when_ready"),
                    "sections": len(scan.get("sections") or []),
                    "regions": tree.get("regions"), "controls_mapped": tree.get("controls_mapped"),
                    "walk_rung": (scan.get("tree_stats") or {}).get("walk_rung") or scan.get("walk_rung"),
                    "revealed": (scan.get("reveal") or {}).get("extra_nodes"),
                    "seconds": scan.get("seconds"), "within_budget": scan.get("within_budget")}
        vision = scan.get("vision") or {}
        map_info["vision"] = {"state": vision.get("state"), "why": vision.get("why")}
    try:
        from core_organs import organ_50_layout_map as lm
        vh = bm.app_version_hash(bm._exe_of_hwnd(hwnd)) if hwnd else ""
        cached = lm.layout_cached(model, key, vh) if vh else None
        if cached:
            map_info["layout_cached"] = {"regions": cached.get("regions"), "signature": cached.get("signature")}
    except Exception:  # noqa: BLE001
        pass

    # ---- ribbon: the app's tab/group structure (any-app contract). Prefer this run's reveal report; otherwise
    # read the persisted layout so a warm card still advertises the ribbon. Never a guess - only what was walked.
    try:
        _rib = (scan or {}).get("ribbon")
        if not isinstance(_rib, dict) or not _rib.get("present"):
            from core_organs import fast_scan as _fs
            _rt, _rg = _fs._ribbon_from_layout(model, key)
            _rib = {"present": bool(_rt or _rg), "tabs": _rt, "groups": _rg}
        _tabs: List[str] = []
        _groups: Dict[str, Any] = {}
        _tv = _rib.get("tabs")
        _gv = _rib.get("groups")
        if isinstance(_tv, list):
            _tabs = [str(t) for t in _tv]
        if isinstance(_gv, dict):
            _groups = dict(_gv)
        if _rib.get("present") and (_tabs or _groups):
            map_info["ribbon"] = {"present": True, "n_tabs": len(_tabs), "n_groups": len(_groups),
                                  "tabs": _tabs[:32], "coverage": _rib.get("coverage")}
    except Exception:  # noqa: BLE001
        pass

    # ---- pixel grounding: addressable OCR/vision rows (the tree-blind app's fallback, plan section B) ----
    pixels: Dict[str, int] = {}
    try:
        from core_organs import organ_50_layout_map as lm
        pixels = lm.count_pixels(model, key)
    except Exception:  # noqa: BLE001
        pass
    if pixels.get("pixel"):
        map_info["pixel_grounded"] = pixels

    # ---- can_do: routes and effects, from the stored rows themselves ----
    can_do: List[Dict[str, Any]] = []
    unknowns: List[str] = []
    try:
        cmds = model.commands(key, limit=5000)
        tr_count = {str(t.get("action")): t for t in model.transitions(key)}
        region_via: Dict[str, str] = {}
        for r in model.regions(key):
            via = str(r.get("via") or "")
            if via and via not in region_via:
                region_via[via] = str(r.get("title") or "")
        learned_or_risky = [c for c in cmds if c.get("source") == "learned"]
        others = [c for c in cmds if c.get("source") != "learned" and c.get("risk") != "E2"]
        for c in (learned_or_risky + others)[:CAN_DO_CAP]:
            action = f"invoke:{c.get('name')}"
            row: Dict[str, Any] = {"name": c.get("name"), "trust": c.get("source"),
                                   "risk": c.get("risk"), "verb": c.get("verb")}
            if c.get("menu_path"):
                row["route"] = str(c["menu_path"]).replace(">", " > ").strip()
            if c.get("shortcut"):
                row["key"] = c["shortcut"]
            tr = tr_count.get(action)
            if tr:
                row["effect"] = f"-> state {tr.get('state_to')}"
            if action in region_via:
                row["opens"] = region_via[action]
            if row.get("trust") != "learned" and not row.get("effect") and not row.get("opens"):
                row["effect"] = "unknown (not probed yet)"
            can_do.append(row)
        e2 = sum(1 for c in cmds if c.get("risk") == "E2")
        if e2:
            unknowns.append(f"{e2} destructive-class (E2) controls: catalogued, never probed or auto-actuated")
    except Exception as exc:  # noqa: BLE001
        unknowns.append(f"can_do graph incomplete: {type(exc).__name__}")

    # ---- blind spots ----
    blind: List[Dict[str, Any]] = []
    if surface.get("wall_risk"):
        blind.append({"what": "actuation wall", "why": surface["wall_risk"],
                      "fallback": "ladder tiers are ordered by the probe; pixel tiers last"})
    nodes = map_info.get("nodes")
    if isinstance(nodes, int):
        if nodes == 0 and map_info.get("walk_rung") in ("timed-out", "walk-failed"):
            blind.append({"what": "UIA tree unread this run", "why": f"walk {map_info['walk_rung']}",
                          "fallback": "vision/OCR tier; retry with a larger budget"})
        elif nodes < 25:
            from core_organs import fast_scan
            covered = pixels.get("pixel", 0)
            blind.append({"what": "sparse UIA tree", "why": f"{nodes} nodes",
                          "fallback": (f"{covered} cached pixel targets are addressable (re-grounded before act)"
                                       if covered else
                                       ("OCR/vision enrichment scheduled or cached"
                                        if (map_info.get("vision") or {}).get("state") in ("scheduled", "done")
                                        else "none ran: fast_scan.SPARSE_NODES=" + str(fast_scan.SPARSE_NODES)))})
    if surface.get("surface") in ("directx/opaque",) or (
            (surface.get("flags") or {}).get("d3d_opaque") and not (surface.get("native_tree") or {}).get("reachable")):
        blind.append({"what": "canvas/opaque surface", "why": "content is drawn, not structured: no UIA nodes inside",
                      "fallback": "OCR/pixel grounding only; actions here are weakly grounded and slower"})

    # ---- verdict: the honest one-line state of the contract ----
    learned_n = int(knowledge.get("commands_learned") or 0)
    reachable = bool((surface.get("native_tree") or {}).get("reachable")) if surface else True
    if learn.get("status") in ("learning", "pending"):
        verdict = "learning"
    elif learned_n >= 3:
        verdict = "actionable"
    elif reachable and int(knowledge.get("commands") or 0) > 0:
        verdict = "actionable-partial"       # mapped, not yet behaviorally probed
    elif pixels.get("pixel"):
        verdict = "actionable-partial"       # only pixel-addressable (re-grounded before act): weaker, but real
    elif blind:
        verdict = "blind-fallback"           # only pixel/OCR tiers can see it, and none are cached yet
    else:
        verdict = "not-groundable"
    contract = ("deep map in seconds + background learning of what each control opens + honest unknowns; "
                "NEVER a promise of success on this specific surface")

    return {"app_key": key, "target": target, "hwnd": hwnd or None,
            "surface": {k: surface.get(k) for k in ("surface", "root_class", "posted_mouse_expectation",
                                                    "native_tree", "wall_risk") if k in surface},
            "map": map_info, "knowledge": knowledge, "learn": learn,
            "can_do": can_do, "unknowns": unknowns, "blind": blind,
            "verdict": verdict, "contract": contract}
