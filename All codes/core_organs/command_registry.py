"""
command_registry.py -- ONE command map per app, and the questions you can ask of everything known about it.

Knowledge about an app's commands arrives from many independent sources: the program file's menu resources, the live menu
crawl (E0), shipped keymap/manifest files, ribbon/toolbar controls of the layout map, explored dropdowns/context menus/tabs,
tested conventions. Each stores rows in `bm_commands` under its own origin. This module unifies them:

  build(model, key)        merge rows that describe the SAME command (canonical label), keeping every shortcut, menu ID,
                           automation ID, help text and access-key chain, and counting INDEPENDENT sources: a command
                           that the file's resources AND the live menu AND an explored probe all agree on is corroborated
  lookup(model, key, goal) rank unified commands for a natural-language goal and attach the ordered ROUTES to execute each
                           (WM_COMMAND id, UIA menu path, key chord, control invoke, context menu) given what is known
                           about how this app accepts input
  dossier(model, key)      everything known, in one structure: identity, toolkit + how to drive it, commands (counted by
                           source), dialogs, state variables, transitions, conventions, regions, plus GAPS: what is not
                           known yet and why
  refresh_profile          re-infer the capability profile / archetype from ALL labels learned so far (evidence, not names)
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from core_organs import knowledge_store as ks

TRUST = {"learned": 4, "catalog": 3, "archetype": 2, "distilled": 1}
_CHORD_IN_NAME = re.compile(r"\(?\b((?:ctrl|control|alt|shift|win|cmd)(?:\s*\+\s*(?:ctrl|alt|shift|[a-z0-9]|f\d{1,2}|enter|space|tab|esc|del|home|end|up|down|left|right|plus|minus|=|-|,|\.))+)\b\)?", re.I)
_TAIL_NOISE = re.compile(r"(\.\.\.|…)\s*$")


def chord_in_name(name: str) -> str:
    """UIA names often embed the chord: 'Bold (Ctrl+B)', 'Save (Ctrl+S)'. Returns a normalised chord or ''."""
    m = _CHORD_IN_NAME.search(name or "")
    if not m:
        return ""
    return re.sub(r"\s*\+\s*", "+", m.group(1).lower().replace("control", "ctrl")).strip("+ ")


def canon(label: str) -> str:
    """Canonical form of one label: no mnemonic, no ellipsis, no embedded chord, case/space folded."""
    s = (label or "").replace("&", "")
    s = _CHORD_IN_NAME.sub("", s)
    s = _TAIL_NOISE.sub("", s.strip())
    s = re.sub(r"\(\s*\)", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def canon_path(path: str, name: str) -> str:
    segs = [canon(p) for p in (path or "").split(">") if p.strip()]
    return " > ".join(segs) if segs else canon(name)


_origin_class = ks.origin_class


def _kind_of(row: Dict[str, Any]) -> str:
    o = row.get("origin") or ""
    if row.get("verb") == "palette":
        return "palette"
    if row.get("verb") == "context" or "context-menu" in o or "[right-click" in (row.get("menu_path") or ""):
        return "context"
    if row.get("verb") == "setting":
        return "setting"
    if o.startswith("e0:") or "pe-menu" in o:
        return "menu"
    if o.startswith("e1:convention"):
        return "key"
    return "control"


def _ev_field(evidence: str, tag: str) -> str:
    m = re.search(rf"{tag}=([^;]*)", evidence or "")
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------------------------

def build(model, app_key: str) -> List[Dict[str, Any]]:
    """Unified command list (one entry per real command), best-trust first."""
    rows = [dict(r) for r in model._conn.execute("SELECT * FROM bm_commands WHERE app_key=?", (app_key,))]
    prov: Dict[str, List[str]] = {}
    try:
        for p in model._conn.execute("SELECT s.cmd_id, s.origin_class FROM bm_cmd_sources s JOIN bm_commands c ON c.cmd_id=s.cmd_id WHERE c.app_key=?", (app_key,)):
            prov.setdefault(p["cmd_id"], []).append(p["origin_class"])
    except Exception:
        prov = {}
    groups: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        kind = _kind_of(r)
        key = f"{kind}|{canon_path(r['menu_path'], r['name'])}"
        if kind == "control":                      # a plain control label: the leaf is the identity (the region path varies)
            key = f"control|{canon(r['name'])}"
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": key, "kind": kind, "name": r["name"], "names": set(), "menu_paths": set(), "shortcuts": {},
                               "menu_ids": set(), "automation_ids": set(), "help": "", "access_chain": "", "sources": set(),
                               "origins": set(), "trust": 0, "confidence": 0.0, "successes": 0, "failures": 0, "risk": "EU",
                               "post": [], "pre": [], "opaque": 1, "stale": 0, "cmd_ids": [], "verbs": set(), "checkable": False}
        g["names"].add(r["name"])
        if r["menu_path"]:
            g["menu_paths"].add(r["menu_path"])
        classes = set(prov.get(r["cmd_id"], [])) or {_origin_class(r["origin"])}
        sc = r["shortcut"] or chord_in_name(r["name"])
        if sc:
            g["shortcuts"].setdefault(sc, set()).update(classes)
        if r["menu_id"]:
            g["menu_ids"].add(int(r["menu_id"]))
        if r["automation_id"]:
            g["automation_ids"].add(r["automation_id"])
        h = _ev_field(r["evidence"], "help")
        if h and not g["help"]:
            g["help"] = h
        ac = _ev_field(r["evidence"], "alt")
        if ac and not g["access_chain"]:
            g["access_chain"] = ac
        g["sources"].update(classes)
        g["origins"].add(r["origin"])
        g["cmd_ids"].append(r["cmd_id"])
        g["verbs"].add(r["verb"])
        if TRUST.get(r["source"], 0) > g["trust"]:
            g["trust"] = TRUST[r["source"]]
        g["confidence"] = max(g["confidence"], r["confidence"] or 0.0)
        g["successes"] += r["successes"] or 0
        g["failures"] += r["failures"] or 0
        # risk: any E2 row wins (never relax a destructive classification); otherwise a PROVEN reversible (E1) beats unknown (EU)
        rr = r["risk"] or "EU"
        if rr == "E2" or g["risk"] == "E2":
            g["risk"] = "E2"
        elif rr == "E1" or g["risk"] == "E1":
            g["risk"] = "E1"
        else:
            g["risk"] = rr
        try:
            post = json.loads(r["post_json"] or "[]")
        except Exception:
            post = []
        if post and not g["post"]:
            g["post"] = post
        try:
            pre = json.loads(r["pre_json"] or "[]")
        except Exception:
            pre = []
        if pre and not g["pre"]:
            g["pre"] = pre
        if not r["opaque"]:
            g["opaque"] = 0
        g["stale"] = max(g["stale"], r["stale"] or 0)
    out: List[Dict[str, Any]] = []
    for g in groups.values():
        shortcuts = sorted(g["shortcuts"].items(), key=lambda kv: -len(kv[1]))
        g["shortcut"] = shortcuts[0][0] if shortcuts else ""
        g["alt_shortcuts"] = [s for s, _ in shortcuts[1:]]
        g["shortcut_agreement"] = len(shortcuts[0][1]) if shortcuts else 0
        g["corroborated"] = len(g["sources"] - {"other"})
        g["menu_id"] = sorted(g["menu_ids"])[0] if g["menu_ids"] else None
        g["menu_path"] = sorted(g["menu_paths"], key=lambda p: (-p.count(">"), p))[0] if g["menu_paths"] else ""
        g["names"] = sorted(g["names"])
        g["sources"] = sorted(g["sources"])
        g["verified"] = g["trust"] >= 4 and g["successes"] >= 1
        for k in ("shortcuts", "menu_ids", "menu_paths", "automation_ids", "verbs", "origins"):
            g[k] = sorted(g[k]) if not isinstance(g[k], dict) else sorted(g[k])
        out.append(g)
    out.sort(key=lambda g: (-g["trust"], -g["corroborated"], -g["confidence"], g["name"].lower()))
    return out


# ---------------------------------------------------------------------------------------------
# routes + lookup
# ---------------------------------------------------------------------------------------------

def _toks(s: str) -> set:
    return {w[:5] for w in re.findall(r"[a-z0-9]+", canon(s)) if len(w) > 1}


_STOP = {"the", "a", "an", "to", "in", "on", "of", "and", "my", "it", "this", "that", "for", "with", "please", "now", "then", "file"}


def goal_tokens(goal: str) -> set:
    return {t for t in _toks(goal) if t not in {w[:5] for w in _STOP}}


def routes_for(model, app_key: str, cmd: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ordered ways to execute a unified command, using what is known about how THIS app accepts input."""
    strategy = ks.get_fact(model, app_key, "strategy", {}) or {}
    delivery = (ks.get_fact(model, app_key, "key_delivery", {}) or {}).get("status", "unknown")
    eff = {}
    try:
        eff = model.effector_coverage(app_key)
    except Exception:
        pass
    key_stat = eff.get("key", {}).get("key", {"ok": 0, "fail": 0})
    keys_ok = delivery == "works" or (key_stat["ok"] > key_stat["fail"])
    keys_bad = delivery == "not-delivered" or (key_stat["fail"] >= 2 and key_stat["ok"] == 0) or strategy.get("posted_keys") == "ignored"
    out: List[Dict[str, Any]] = []
    if cmd["menu_id"] and strategy.get("native_menus"):
        out.append({"effector": "wm_command", "menu_id": cmd["menu_id"], "why": "classic menu ID: headless, needs no tree"})
    if cmd["kind"] in ("menu", "control") and cmd["menu_path"] and " > " in cmd["menu_path"] and cmd["kind"] == "menu":
        out.append({"effector": "menu_path", "path": cmd["menu_path"], "why": "UIA expand + invoke"})
    if cmd["shortcut"] and not keys_bad:
        r = {"effector": "key", "keys": cmd["shortcut"], "why": "accelerator" + (" (key delivery proven on this app)" if keys_ok else " (delivery unproven)")}
        if keys_ok:
            out.insert(0, r)
        else:
            out.append(r)
    if cmd["kind"] == "context":
        out.append({"effector": "context", "path": cmd["menu_path"], "why": "right-click target, then the item"})
    if cmd["kind"] == "palette":
        out.append({"effector": "palette", "title": (cmd["names"] or [cmd["name"]])[0], "why": "command palette entry"})
    if cmd["kind"] in ("control", "menu"):
        out.append({"effector": "invoke_control", "label": (cmd["names"] or [cmd["name"]])[0], "why": "UIA invoke by label"})
    if cmd["access_chain"] and strategy.get("native_menus") and not keys_bad:
        out.append({"effector": "access_chain", "keys": "alt+" + "+".join(cmd["access_chain"]), "why": "menu mnemonics (keyboard-only route)"})
    seen, uniq = set(), []
    for r in out:
        k = (r["effector"], json.dumps({a: b for a, b in r.items() if a != "why"}, sort_keys=True))
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def lookup(model, app_key: str, goal: str, limit: int = 8, registry: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Unified commands ranked for `goal` with their routes. Pure data lookup: no LLM, no per-app branches."""
    reg = registry if registry is not None else build(model, app_key)
    gt = goal_tokens(goal)
    gcanon = canon(goal)
    if not gt:
        return []
    scored: List[Tuple[float, Dict[str, Any], float]] = []
    for c in reg:
        if c["kind"] == "setting" or c["risk"] == "E2" and not any(w in gcanon for w in ("delete", "remove", "close", "exit")):
            continue
        hay = set()
        for n in c["names"]:
            hay |= _toks(n)
        hay |= _toks(c["menu_path"].rsplit(">", 1)[-1])
        hay_help = _toks(c["help"]) if c["help"] else set()
        if not (gt & (hay | hay_help)):
            continue
        overlap = len(gt & hay) / len(gt)
        score = overlap * 3 + 0.4 * (len(gt & hay_help) / len(gt))
        if any(canon(n) == gcanon for n in c["names"]) or canon(c["menu_path"].rsplit(">", 1)[-1]) == gcanon:
            score += 2.0
        if len(hay) > len(gt) + 3:
            score -= 0.4 * (len(hay) - len(gt) - 3) / max(len(hay), 1)       # a long unrelated label that merely contains a word
        score += 0.35 * c["trust"] + 0.25 * min(c["corroborated"], 3) + (0.3 if c["verified"] else 0)
        if c["kind"] == "context":
            score -= 0.3                                                      # prefer the direct command over a right-click route
        scored.append((score, c, overlap))
    scored.sort(key=lambda t: -t[0])
    out = []
    for s, c, cov in scored[:limit]:
        d = {k: c[k] for k in ("name", "names", "kind", "menu_path", "shortcut", "alt_shortcuts", "menu_id", "help", "risk", "trust", "corroborated",
                              "sources", "verified", "post", "pre", "opaque", "successes", "failures", "access_chain", "cmd_ids")}
        d["score"] = round(s, 2)
        d["coverage"] = round(cov, 2)
        d["routes"] = routes_for(model, app_key, c)
        out.append(d)
    return out


# ---------------------------------------------------------------------------------------------
# profile + dossier + gaps
# ---------------------------------------------------------------------------------------------

def refresh_profile(model, app_key: str) -> Dict[str, Any]:
    """Re-infer capabilities / archetype from every label learned so far (static + live + explored) and store it."""
    from core_organs import static_knowledge as sk
    reg = build(model, app_key)
    labels = []
    for c in reg:
        if c["kind"] == "control" and c["sources"] == ["layout"]:
            continue                       # bare layout labels ('Grid > O8') carry position, not capability
        labels.append(c["menu_path"] or c["name"])
        if c["kind"] in ("control",):
            labels.append(c["name"])
    dtitles = [d["title"] for d in ks.dialogs(model, app_key) if d["title"]]
    regions = [r["region_kind"] for r in model._conn.execute("SELECT DISTINCT region_kind FROM bm_layout WHERE app_key=?", (app_key,))
               if r["region_kind"]] if _table(model, "bm_layout") else []
    exts = ks.get_fact(model, app_key, "file_types", []) or []
    fws = [f["id"] for f in (ks.get_fact(model, app_key, "frameworks", []) or [])]
    prof = sk.infer_profile(labels=labels, exts=exts, dialog_titles=dtitles, regions=regions, framework_ids=fws)
    ks.put_fact(model, app_key, "profile", prof, source="live:inference", confidence=0.7)
    return {"archetype": prof["archetype"], "margin": prof["margin"], "top": prof["archetypes"][:3], "capabilities": sorted(prof["capabilities"]),
            "unified_commands": len(reg)}


def _table(model, name: str) -> bool:
    return bool(model._conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


QUICK_INTENTS = ["save", "save as", "open", "new", "find", "replace", "undo", "redo", "copy", "paste", "select all", "print", "settings", "zoom in",
                 "bold", "close", "exit"]


def gaps(model, app_key: str, reg: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    reg = reg if reg is not None else build(model, app_key)
    out: List[str] = []
    fs = ks.frontier_stats(model, app_key)
    n_open = fs["by_status"].get("open", 0)
    if n_open:
        kinds: Dict[str, int] = {}
        for r in ks.frontier_open(model, app_key, limit=1000):
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        out.append(f"{n_open} discovered surface(s) not explored yet ({', '.join(f'{k}:{v}' for k, v in sorted(kinds.items()))}): another run continues them")
    unsafe = fs["by_status"].get("unsafe", 0)
    if unsafe:
        out.append(f"{unsafe} control(s) look destructive/outward-facing: known to exist, deliberately never probed (their effect is unverified)")
    failed = fs["by_status"].get("failed", 0)
    if failed:
        out.append(f"{failed} probe(s) failed (control not reachable or call refused): effect unknown")
    opaque = sum(1 for c in reg if c["opaque"] and c["kind"] in ("menu", "control") and c["risk"] != "E2")
    if opaque:
        out.append(f"{opaque} command(s) have no machine-checkable postcondition (effect never observed)")
    for intent in ("save as", "open", "find", "undo"):
        if not any(canon(intent) in canon(n) for c in reg for n in c["names"]):
            out.append(f"no command matching '{intent}' found (the app may not have it, or it lives in a surface not explored)")
    kd = (ks.get_fact(model, app_key, "key_delivery", {}) or {}).get("status", "unknown")
    if kd in ("unknown", "not-delivered"):
        out.append("keyboard shortcuts: " + ("not delivered by this app's input stack (use UIA routes)" if kd == "not-delivered" else "delivery not tested yet"))
    strat = ks.get_fact(model, app_key, "strategy", {}) or {}
    if strat.get("uia") in ("after-wake", "after-wake-often-empty", "absent-without-access-bridge", "none", "partial", "semantics-only-when-enabled"):
        out.append(f"toolkit limits UIA ({strat.get('uia')}): the accessibility tree may be incomplete; OCR/vision rung may be needed")
    if not ks.dialogs(model, app_key):
        out.append("no dialog schema known (no dialog was opened or found in the program file)")
    prof = ks.get_fact(model, app_key, "profile", {}) or {}
    if prof.get("archetype") in (None, "", "unclassified"):
        out.append("app kind not classified (not enough evidence yet)")
    if ks.get_fact(model, app_key, "requires_elevation", False):
        out.append("the program requests elevation: launching it shows a UAC prompt that is never auto-accepted (human step)")
    return out


def _surface_of(c: Dict[str, Any]) -> str:
    """The surface a unified command lives on: a top-level menu, the context menus, a dropdown / tab / surface region, or the plain controls."""
    p = (c.get("menu_path") or "").strip()
    kind = c.get("kind") or ""
    if p.startswith("[right-click"):
        return "context menus"
    if ">" in p:
        top = p.split(">")[0].strip()
        if top and not top.startswith("[") and kind == "menu":
            return f"menu: {top}"
        if top:
            return f"panel: {top}"
    if kind == "menu":
        return "menu bar"
    if kind == "key":
        return "keyboard shortcuts"
    return "controls"


def capability_summary(model, app_key: str, reg: List[Dict[str, Any]], facts: Dict[str, Any], dlgs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """'What is this app and how do I use it to the full extent' - written from DATA only (the profile inferred from evidence, the unified
    command map, observed dialogs): no per-app text. Each SURFACE lists what lives there and ONE task that a live probe VERIFIED on that
    surface when there is one (a learned command with a success); a surface with no verified task says so instead of inventing one."""
    t0 = time.time()
    prof = facts.get("profile") or {}
    vi = facts.get("version_info") or {}
    surfaces: Dict[str, Dict[str, Any]] = {}
    for c in reg:
        s = surfaces.setdefault(_surface_of(c), {"surface": _surface_of(c), "commands": 0, "verified": [], "example": None})
        s["commands"] += 1
        if s["example"] is None or (c["trust"] > s["example"]["trust"]):
            s["example"] = {"command": c["name"], "path": c["menu_path"], "shortcut": c["shortcut"], "trust": c["trust"]}
        if c["verified"]:
            s["verified"].append({"command": c["name"], "path": c["menu_path"], "shortcut": c["shortcut"], "successes": c["successes"],
                                  "risk": c["risk"], "route": (c.get("routes") or [{}])[0].get("effector", "") if c.get("routes") else ""})
    for d in dlgs:                                                      # a dialog the loop actually saw OPEN is a verified surface
        title = (d.get("title") or "").strip()
        if not title:
            continue
        src = str(d.get("source") or "")
        s = surfaces.setdefault(f"dialog: {title}", {"surface": f"dialog: {title}", "commands": 0, "verified": [], "example": None})
        s["commands"] += len(d.get("controls") or [])
        if src.startswith("live"):
            s["verified"].append({"command": f"open '{title}'", "path": str(d.get("via") or ""), "successes": 1, "risk": "E1", "route": src})
    ordered = sorted(surfaces.values(), key=lambda s: (-len(s["verified"]), -s["commands"]))
    for s in ordered:
        s["verified_task"] = s["verified"][0] if s["verified"] else None
        s["verified_n"] = len(s["verified"])
        s.pop("verified")
    caps = prof.get("capabilities") or []
    strat = facts.get("strategy") or {}
    how: List[str] = []
    if strat.get("native_menus"):
        how.append("classic menu bar: every menu entry can be run by its command id (no focus needed)")
    if strat.get("posted_keys") == "ignored":
        how.append("keyboard shortcuts are NOT delivered to this app (XAML): use UIA invoke on the control instead")
    if (facts.get("key_delivery") or {}).get("status") == "works":
        how.append("keyboard shortcuts were verified to arrive")
    if facts.get("cli_open"):
        how.append(f"files can be opened from the command line: {facts['cli_open']}")
    if facts.get("requires_elevation"):
        how.append("the program asks for elevation: a human must approve it (never auto-accepted)")
    covered = sum(1 for s in ordered if s["verified_task"])
    return {
        "what_it_is": (vi.get("FileDescription") or "") or (prof.get("archetype") or "unclassified"),
        "archetype": prof.get("archetype") or "not classified (not enough evidence yet)",
        "capabilities": caps,
        "opens": sorted((prof.get("ext_categories") or {}).keys()),
        "how_to_use": how,
        "surfaces": ordered,
        "coverage": {"surfaces": len(ordered), "with_verified_task": covered,
                     "note": "a surface with no verified task has only been READ, not exercised: run mastery (know(target, live=True)) to verify more"},
        "elapsed_ms": round((time.time() - t0) * 1000, 1),
    }


def dossier(model, app_key: str, *, with_registry: bool = True) -> Dict[str, Any]:
    """Everything known about an app, in one structure."""
    ks.ensure(model)
    f = ks.facts(model, app_key)
    reg = build(model, app_key) if with_registry else []
    from core_organs import organ_63_app_mastery as am
    d: Dict[str, Any] = {
        "app_key": app_key,
        "identity": {"exe": f.get("exe", ""), "description": (f.get("version_info") or {}).get("FileDescription", ""),
                     "company": (f.get("version_info") or {}).get("CompanyName", ""), "package": (f.get("appx") or {}).get("package", ""),
                     "requires_elevation": f.get("requires_elevation", False)},
        "toolkit": [x["id"] for x in (f.get("frameworks") or [])],
        "how_to_drive": {"strategy": f.get("strategy", {}), "key_delivery": f.get("key_delivery", {}),
                         "effectors": model.effector_coverage(app_key) if hasattr(model, "effector_coverage") else {}},
        "kind": f.get("profile", {}),
        "opens_files": f.get("file_types", []), "open_from_cli": f.get("cli_open", ""),
        "commands": {"unified": len(reg), "by_kind": {}, "verified": sum(1 for c in reg if c["verified"]),
                     "with_shortcut": sum(1 for c in reg if c["shortcut"]), "corroborated_by_2plus_sources": sum(1 for c in reg if c["corroborated"] >= 2)},
        "dialogs": ks.dialogs(model, app_key),
        "state_variables": ks.statevars(model, app_key),
        "conventions": ks.conventions(model, app_key),
        "transitions": model._conn.execute("SELECT COUNT(*) FROM bm_transitions WHERE app_key=?", (app_key,)).fetchone()[0],
        "regions": len(model.regions(app_key)),
        "frontier": ks.frontier_stats(model, app_key),
        "runs": [{"run": r["run_no"], "gain": r["metrics"].get("gain", {}), "s": r["metrics"].get("elapsed_s")} for r in ks.run_log(model, app_key) if r["phase"] == "run"],
        "measure": am.measure(model, app_key),
    }
    for c in reg:
        d["commands"]["by_kind"][c["kind"]] = d["commands"]["by_kind"].get(c["kind"], 0) + 1
    quick = {}
    for intent in QUICK_INTENTS:
        hit = lookup(model, app_key, intent, limit=1, registry=reg)
        if hit and hit[0]["score"] >= 2.0:
            quick[intent] = {"command": hit[0]["name"], "path": hit[0]["menu_path"], "shortcut": hit[0]["shortcut"],
                             "route": (hit[0]["routes"] or [{}])[0].get("effector", ""), "trust": hit[0]["trust"], "verified": hit[0]["verified"]}
    d["quick_answers"] = quick
    d["gaps"] = gaps(model, app_key, reg)
    try:
        for c in reg[:400]:
            if "routes" not in c:
                c["routes"] = routes_for(model, app_key, c)
        d["summary"] = capability_summary(model, app_key, reg, f, d["dialogs"])
    except Exception as exc:  # noqa: BLE001
        d["summary"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    return d
