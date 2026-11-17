"""
professor.app_record -- FULL APP KNOWLEDGE IN ONE PLACE: one persistent record per application, with a coverage score.

What the Professor knows about an application used to be spread over the catalog file (controls), the history database (what each action did), the skills database (routes that
worked), the workflow library (the guide, step by step) and the run reports. This module JOINS them - nothing is re-measured here - into

  data/professor/apps/<app>.json   identity (name, exe, version, toolkit, kind of software)
                                    controls      every control: path, label, role, shortcut, what it leads to, safety, where the fact came from, its last seen state
                                    effects       per control: what acting on it did (opens_dialog / state_change / context_change / no_effect - counted) and the route that worked
                                    routes        verified skills (chains that ran end to end) and their success rates
                                    workflows     the guide's procedures: grounding, status, last result
                                    coverage      known / tried / grounded / verified, and one SCORE (0-100) with how it was made
  data/professor/apps/INDEX.md     every application side by side, sorted by score

  build(app) -> record     build_all() -> index       (CLI: hojaiga_professor.py knowledge <app>|--all)
"""

from __future__ import annotations

import glob
import json
import os
import time
from typing import Any, Dict, List, Optional

from . import config as CFG
from .schema import fold

APPS_DIR = os.path.join(CFG.DATA_DIR, "apps")
LIVE_SOURCES = {"uia", "win32-menu", "menu-expand", "ribbon", "reveal", "ocr", "vision", "label", "hover-tooltip"}


def _last_report(app_key: str) -> Dict[str, Any]:
    from .apprun import OUT_DIR
    files = sorted(glob.glob(os.path.join(OUT_DIR, f"{app_key}_*.json")), key=os.path.getmtime)
    for p in reversed(files):
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("phases", {}).get("catalog"):
                d["_file"] = p
                return d
        except Exception:
            continue
    return {}


def build(app_key: str, write: bool = True) -> Dict[str, Any]:
    from .harvest import Catalog
    from . import history as HS, skills as SK, workflows as WF
    cat = Catalog.load(app_key)
    rep = _last_report(app_key)
    hist = HS.library()
    sk = SK.library()
    rec: Dict[str, Any] = {"app": app_key, "built": time.strftime("%Y-%m-%d %H:%M:%S")}
    ph = rep.get("phases", {})
    tgt = ph.get("target", {})
    rec["identity"] = {"name": rep.get("name", app_key), "exe": tgt.get("exe", ""), "version": (ph.get("vendor_manifest") or {}).get("build") or (ph.get("vendor_manifest") or {}).get("exe_version", ""),
                       "toolkit": ((ph.get("deep_scan") or {}).get("profile") or {}).get("family", ""), "kind": (cat.archetype if cat is not None else {}) or {},
                       "perception": (ph.get("perception") or {}).get("used", "tree" if ph else ""), "last_run": rep.get("started", ""), "last_report": rep.get("html") or rep.get("_file", "")}
    controls: List[Dict[str, Any]] = []
    eff_rows: Dict[str, Dict[str, int]] = {}
    try:
        for r in hist.rows(app_key):
            t = fold(r.get("target", "") or "")
            if not t:
                continue
            d = eff_rows.setdefault(t, {})
            d[r.get("effect", "") or "?"] = d.get(r.get("effect", "") or "?", 0) + 1
            if r.get("ok"):
                d["_route:" + str(r.get("route", ""))[:40]] = d.get("_route:" + str(r.get("route", ""))[:40], 0) + 1
    except Exception:
        pass
    if cat is not None:
        for v in cat.verbs:
            e = eff_rows.get(fold(v.label), {})
            routes = sorted(((k[7:], n) for k, n in e.items() if k.startswith("_route:")), key=lambda t: -t[1])
            controls.append({"path": list(v.path), "label": v.label, "role": v.role, "shortcut": v.shortcut, "leads_to": v.leads_to, "safety": v.safety, "sources": list(v.sources or []),
                             "live": bool(set(v.sources or []) & LIVE_SOURCES), "enabled": v.enabled, "checked": v.checked, "desc": (v.desc or "")[:160],
                             "effects": {k: n for k, n in e.items() if not k.startswith("_")}, "route_that_worked": routes[0][0] if routes else ""})
    rec["controls"] = controls
    rec["routes"] = []
    try:
        for s in sk.all(app_key):
            rec["routes"].append({"id": s.id, "goals": list(getattr(s, "goals", []))[:3], "steps": [getattr(x, "label", "") or getattr(x, "text", "") for x in s.steps], "success_rate": round(s.success_rate(), 2),
                                  "status": getattr(s, "status", "")})
    except Exception:
        pass
    wf = WF.load(app_key) or {}
    ws = wf.get("summary", {})
    rec["workflows"] = {"documents": wf.get("documents", 0), "workflows": ws.get("workflows", 0), "by_status": ws.get("by_status", {}), "grounding_applicable": ws.get("grounding_applicable"),
                        "grounding_raw": ws.get("grounding_raw"), "steps": ws.get("steps"), "applicable_steps": ws.get("applicable_steps"),
                        "last_results": {k: sum(1 for w in wf.get("workflows", []) if w.get("last_run", {}).get("result") == k) for k in ("ok", "blocked", "failed", "skipped")}}
    cov = ph.get("coverage") or {}
    live = sum(1 for c in controls if c["live"])
    tried = sum(1 for c in controls if c["effects"])
    led = rep.get("counts", {}) or {}                                        # the procedures this run actually performed (ok / blocked on purpose / failed)
    attempted = sum(v for k, v in led.items() if k in ("ok", "failed"))       # blocked-on-purpose (a human's yes) is not a failure of the Professor
    parts = {
        "controls_seen_live": min(100.0, 100.0 * live / max(1, len(controls))) if controls else 0.0,
        "safe_controls_tried": float(cov.get("percent", 0.0) or (100.0 * tried / max(1, live))),
        "guide_steps_grounded": 100.0 * float(rec["workflows"]["grounding_applicable"] or 0.0),
        "procedures_verified": 100.0 * led.get("ok", 0) / max(1, attempted) if attempted else 0.0,
    }
    weights = {"controls_seen_live": 0.2, "safe_controls_tried": 0.25, "guide_steps_grounded": 0.35, "procedures_verified": 0.2}
    score = sum(parts[k] * w for k, w in weights.items())
    rec["coverage"] = {"controls": len(controls), "live_controls": live, "controls_with_a_measured_effect": tried, "button_coverage": cov, "procedures_attempted": attempted,
                       "procedures_ok": led.get("ok", 0), "parts": {k: round(v, 1) for k, v in parts.items()}, "weights": weights, "score": round(score, 1),
                       "how": "0.20 x share of controls seen live + 0.25 x safe controls tried + 0.35 x guide steps grounded (applicable) + 0.20 x guide procedures that ran and verified"}
    try:
        hist.close()
        sk.close()
    except Exception:
        pass
    if write:
        os.makedirs(APPS_DIR, exist_ok=True)
        with open(os.path.join(APPS_DIR, f"{app_key}.json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=1, ensure_ascii=False, default=str)
    return rec


def build_all(apps: Optional[List[str]] = None) -> str:
    from .harvest import CATALOG_DIR
    keys = apps or sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(CATALOG_DIR, "*.json")))
    rows = []
    for k in keys:
        try:
            r = build(k)
            c = r["coverage"]
            rows.append((c["score"], k, c, r["workflows"], r["identity"]))
        except Exception as exc:
            rows.append((0.0, k, {"error": f"{type(exc).__name__}: {exc}"}, {}, {}))
    rows.sort(key=lambda t: -t[0])
    lines = ["# What the Professor knows, per application", "", f"_updated {time.strftime('%Y-%m-%d %H:%M:%S')}_ · score = " + "0.20 seen live + 0.25 tried + 0.35 guide grounded + 0.20 procedures verified", "",
             "| app | score | controls (live) | safe controls tried | guide grounded | procedures ok / attempted | perception |", "|---|---|---|---|---|---|---|"]
    for sc, k, c, w, ident in rows:
        if "error" in c:
            lines.append(f"| {k} | - | {c['error'][:60]} | | | | |")
            continue
        bc = c.get("button_coverage") or {}
        lines.append(f"| [{k}]({k}.json) | **{sc}** | {c['controls']} ({c['live_controls']}) | {bc.get('percent', '-')}% | {round(100 * float(w.get('grounding_applicable') or 0), 1)}% | "
                     f"{c['procedures_ok']} / {c['procedures_attempted']} | {ident.get('perception', '')} |")
    os.makedirs(APPS_DIR, exist_ok=True)
    p = os.path.join(APPS_DIR, "INDEX.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return p
