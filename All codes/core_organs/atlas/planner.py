"""
atlas.planner -- a task in plain words -> a GROUNDED plan: how each step can really be done in THIS application.

Knowledge is primary, the path is derived from it. For every sub-goal the planner collects every way the learned knowledge says it can be done:

    control / menu route   a command the live scan or a probe found (menu path, control label), with its verified-ness and risk
    dialog path            a control that lives inside a dialog schema -> [open the dialog by its opener, act, close]
    shortcut               a keyboard chord (measured, shipped in the program file, or published) -- trusted only if key delivery is proven
    COM method             a method of the application's own object model (Document.SaveAs2 ...)
    command-line switch    a switch found in the binaries (--startrecording)
    gesture                a measured or published pointer gesture (middle-drag = orbit)
    scripting               the application embeds a scripting runtime: a documented, input-independent way to do anything

and ranks them by how well the evidence supports them AND by the measured input channels (an app that ignores a posted pointer gets its pointer
routes demoted and its scripting / COM / command-line routes promoted). A sub-goal nothing supports is reported `ungrounded`: the planner never invents a step.

`execute()` runs the steps that have a headless effector (UIA invoke, menu path, posted key, WM_COMMAND), verifies each with a before/after read and
refuses anything risky unless allowed. It is the proof that the plan is made of real knowledge.
"""

from __future__ import annotations

import collections
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import common as C
from . import llm

VERB_EFFECT = {"rotate": ["rotate", "nonrigid"], "orbit": ["rotate", "nonrigid"], "turn": ["rotate"], "spin": ["rotate"], "pan": ["pan", "scroll"], "move view": ["pan"],
               "scroll": ["scroll", "pan"], "zoom": ["zoom"], "dolly": ["zoom"], "select": ["rubber_band", "rubber_band_with_selection", "local_change"], "move": ["translate_object"],
               "drag": ["translate_object", "pan"], "draw": ["stroke", "shape_draw"], "paint": ["stroke"], "menu": ["opens_menu"], "context": ["opens_menu"], "hold": ["opens_menu"]}
CREATE_VERBS = re.compile(r"\b(create|make|build|model|design|add|generate|render|import|export|compose|write|draw|animate|sculpt|mix|record)\b", re.I)
STOP = {"the", "a", "an", "to", "in", "on", "of", "and", "my", "it", "this", "that", "for", "with", "please", "now", "then", "file", "app", "application", "program", "using", "into", "from"}


def _stem(w: str) -> str:
    return re.sub(r"(ing|ed|es|s|e)$", "", w) if len(w) > 4 else w


def toks(s: str) -> List[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s or "")
    return [_stem(w)[:6] for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 1 and w not in STOP]


def overlap(a: Sequence[str], b: Sequence[str]) -> float:
    A, B = set(a), set(b)
    return len(A & B) / len(A) if A else 0.0


# --------------------------------------------------------------------------------------------------
# decomposition
# --------------------------------------------------------------------------------------------------

def decompose(task: str, context: Dict[str, Any], *, use_model: bool = True) -> Tuple[List[str], Dict[str, Any]]:
    meta: Dict[str, Any] = {"method": "split"}
    parts = [p.strip(" .") for p in re.split(r"\s*(?:,\s*then|\bthen\b|;|\band then\b|\bafter that\b|\bnext\b|\n)\s*", task) if p.strip(" .")]
    if len(parts) > 1 or not use_model or not llm.available():
        return parts[:10] or [task.strip()], meta
    sys_p = ('Break the user task into 2-8 short, ordered sub-goals that can each be done with ONE command, menu entry, dialog or gesture of the described application. '
             'Reply JSON only: {"subgoals":["..."]}. Use the application\'s own vocabulary from the CONTEXT when it fits. Do not add goals the task does not imply.')
    r = llm.chat(sys_p, f"APPLICATION CONTEXT:\n{json.dumps(context)[:2600]}\n\nTASK: {task}", timeout=60, max_tokens=400)
    sg = (r.get("json") or {}).get("subgoals") if isinstance(r.get("json"), dict) else None
    if isinstance(sg, list) and sg and all(isinstance(x, str) for x in sg):
        meta.update(method="model", model=r.get("model"), seconds=r.get("seconds"))
        return [x.strip() for x in sg][:8], meta
    meta["model_error"] = r.get("error")
    return parts or [task.strip()], meta


# --------------------------------------------------------------------------------------------------
# route collection
# --------------------------------------------------------------------------------------------------

def _com_methods(store: C.AtlasStore, key: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for c in store.claims(key, "ext.com.model"):
        f = (c.get("value") or {}).get("file")
        if f and os.path.isfile(f):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                for lib in d.get("typelibs", {}).values():
                    for t, ms in (lib.get("methods") or {}).items():
                        out.setdefault(t.lstrip("_"), []).extend(m for m in ms if "[" not in m)
            except Exception:
                continue
    return out


def collect_routes(key: str, subgoal: str, store: C.AtlasStore, model, channels: Dict[str, Any]) -> List[Dict[str, Any]]:
    g = toks(subgoal)
    routes: List[Dict[str, Any]] = []
    mouse_bad = channels.get("posted_mouse") == "ineffective"
    # --- commands & controls (the engine's registry)
    try:
        from core_organs import command_registry as cr
        reg = cr.build(model, key)
        gcanon = cr.canon(subgoal)
        explicit_e2 = set()
        reg2 = []
        for c in reg:
            if c["risk"] == "E2" and (cr.canon(c["name"]) == gcanon or any(cr.canon(n) == gcanon for n in c["names"])):
                c = dict(c)
                c["risk"] = "EU"
                explicit_e2.add(cr.canon(c["name"]))
            reg2.append(c)
        for h in cr.lookup(model, key, subgoal, limit=4, registry=reg2):
            if cr.canon(h["name"]) in explicit_e2:
                h = dict(h, risk="E2")                                # the user NAMED it, so a route exists; it stays flagged destructive for execute()
            for r in h["routes"][:3]:
                trust = {4: "measured", 3: "static", 2: "inferred", 1: "inferred", 0: "inferred"}.get(h["trust"], "inferred")
                score = 2.0 + h["score"] + (1.0 if h["verified"] else 0.0) - (0.5 if h["risk"] == "E2" else 0.0)
                if r["effector"] in ("key",) and "delivery proven" not in r.get("why", ""):
                    score -= 0.8
                routes.append({"effector": r["effector"], "detail": {k: v for k, v in r.items() if k not in ("effector", "why")}, "label": h["name"], "why": r.get("why", ""), "trust": trust,
                               "risk": h["risk"], "score": score, "expect": h.get("post") or [], "verified": h["verified"], "evidence": [f"command:{h['cmd_ids'][0] if h.get('cmd_ids') else h['name']}"]})
    except Exception:
        pass
    # --- controls inside dialogs: [open the dialog] -> control
    try:
        from core_organs import knowledge_store as ks
        for d in ks.dialogs(model, key, with_controls=True):
            for c in d.get("controls") or []:
                nm = c.get("name") if isinstance(c, dict) else str(c)
                if nm and overlap(g, toks(nm)) >= 0.99 and len(g) <= 4:
                    opener = None
                    for cmd in model.commands(key, limit=5000):
                        if overlap(toks(d["title"]), toks(cmd["name"])) >= 0.99 or overlap(toks(d["title"]), toks(cmd["name"])) >= 0.8 and cmd["name"].strip().endswith(("...", "…")):
                            opener = cmd
                            break
                    routes.append({"effector": "dialog_path", "detail": {"dialog": d["title"], "control": nm, "opener": opener["name"] if opener else None, "opener_path": (opener or {}).get("menu_path", "")},
                                   "label": f"{d['title']} > {nm}", "why": "control found in a learned dialog schema", "trust": "measured", "risk": "E1", "score": 3.0 if opener else 1.5, "expect": [], "verified": False,
                                   "evidence": [f"dialog:{d['title']}"]})
    except Exception:
        pass
    # --- published / measured shortcuts
    for c in store.claims(key, "ui.shortcut"):
        v = c.get("value") or {}
        s = overlap(g, toks(v.get("action", "")))
        if s >= 0.6:
            routes.append({"effector": "shortcut", "detail": {"keys": v.get("input")}, "label": v.get("action"), "why": "published shortcut", "trust": "published", "risk": "EU", "score": 1.0 + 2 * s, "expect": [], "verified": False,
                           "evidence": [c["id"]]})
    # --- COM object model
    for typ, ms in _com_methods(store, key).items():
        for m in ms:
            s = overlap(g, toks(m))
            if s >= 0.99 and len(g) <= 3 or (s >= 0.66 and len(g) >= 3):
                routes.append({"effector": "com_method", "detail": {"type": typ, "method": m}, "label": f"{typ}.{m}", "why": "method of the application's registered object model", "trust": "static", "risk": "EU",
                               "score": 2.6 + (0.6 if channels.get("posted_mouse") == "ineffective" else 0), "expect": [], "verified": False, "evidence": [f"com:{typ}.{m}"]})
    # --- operators the program's own runtime reported (introspection): input-independent, documented
    try:
        from . import introspect
        tmpl = introspect.call_template_of(key, store)
        if tmpl:
            for o in introspect.operators_of(key, store):
                nt, it, dt = toks(o.get("name", "")), toks(o["id"].replace(".", " ").replace("_", " ")), toks(o.get("desc", ""))
                s = max(overlap(g, nt), overlap(g, it), 0.85 * overlap(g, dt))
                jac = len(set(g) & (set(nt) | set(it))) / max(1, len(set(g) | set(nt)))          # exactness: "Add Cube" beats "Add Cube Gizmo"
                if s >= 0.99 and len(g) <= 4 or (s >= 0.66 and len(g) >= 3):
                    routes.append({"effector": "api_operator", "detail": {"id": o["id"], "call": tmpl.format(id=o["id"]), "params": [p[0] for p in o.get("props", [])][:8]}, "label": f"{o.get('name') or o['id']} ({o['id']})",
                                   "why": (o.get("desc") or "operator reported by the program's own runtime")[:140], "trust": "measured", "risk": "EU",
                                   "score": 2.4 + 1.2 * jac + (0.8 if channels.get("posted_mouse") == "ineffective" else 0), "expect": [], "verified": False, "evidence": [f"api:{o['id']}"]})
    except Exception:
        pass
    # --- the scanned UI map (ribbon / menu / File view): step-by-step routes with the items inside drop-downs and the dialogs they open
    try:
        from . import teach, uimap as _um
        from . import explorer as _xp
        tr = teach.routes_for(key, subgoal, limit=4, use_model=False)
        for r in tr.get("routes", []) if tr.get("ok") else []:
            if r["score"] < 2.5:
                continue
            risky = bool(_xp.UNSAFE_RX.search(r["control"]) or _xp.SENSITIVE_RX.search(r["control"]) or _um.RUNTIME_RX.search(r["control"]))
            routes.append({"effector": "ribbon_path", "detail": {"path": r["path"], "shortcut": r["shortcut"], "dialog": r["dialog"]}, "label": r["text"].replace("**", "")[:140],
                           "why": (r["outcome"] or "route read from the live window") + ("; needs a selection first" if r["preconditions"] else ""), "trust": "measured", "risk": "E2" if risky else "EU",
                           "score": 2.2 + min(2.0, r["score"] / 6.0) - (0.6 if r["preconditions"] else 0.0), "expect": [], "verified": False, "evidence": [f"uimap:{key}"]})
    except Exception:
        pass
    # --- command-line switches
    for c in store.claims(key, "ext.cli"):
        for flag in (c.get("value") or []) if isinstance(c.get("value"), list) else []:
            flat = flag.lower().replace("-", "")
            s = (sum(1 for t in g if len(t) >= 3 and t[:5] in flat) / len(g)) if g else 0.0       # switches are often concatenated words: --startrecording
            if s >= 0.99:
                routes.append({"effector": "cli_switch", "detail": {"flag": flag}, "label": flag, "why": "switch present in the binaries (applies at launch)", "trust": "static", "risk": "EU", "score": 2.0 + s,
                               "expect": [], "verified": False, "evidence": [c["id"]]})
    # --- gestures
    for gm in store.gestures(key):
        eff = gm["effect_class"]
        for verb, classes in VERB_EFFECT.items():
            if re.search(r"\b" + verb + r"\b", subgoal, re.I) and eff in classes and gm.get("effective"):
                routes.append({"effector": "gesture", "detail": {"gesture": gm["gesture"], "region": gm["region_kind"], "effect": eff, "reversible": bool(gm["reversible"])}, "label": f"{gm['gesture']} on {gm['region_kind']}",
                               "why": "measured pointer gesture", "trust": "measured", "risk": "E1" if gm["reversible"] else "EU", "score": 2.4 - (3.0 if mouse_bad else 0), "expect": [eff], "verified": True, "evidence": [f"gesture:{gm['id']}"]})
    for c in store.claims(key, "gesture.shipped"):
        v = c.get("value") or {}
        act = (v.get("action") or "").replace(".", " ").replace("_", " ")
        for verb in VERB_EFFECT:
            if re.search(r"\b" + verb + r"\b", subgoal, re.I) and re.search(verb.split()[0][:4], act, re.I):
                routes.append({"effector": "gesture", "detail": {"gesture": v.get("input"), "region": v.get("context"), "action": v.get("action")}, "label": f"{v.get('input')} ({v.get('action')})",
                               "why": "published keymap (not verified live)", "trust": "published", "risk": "EU", "score": 1.6 - (2.0 if mouse_bad else 0), "expect": [], "verified": False, "evidence": [c["id"]]})
                break
    # --- scripting as the input-independent fallback for creative goals
    scr = store.claims(key, "stack.scripting")
    if scr and CREATE_VERBS.search(subgoal):
        routes.append({"effector": "scripting_api", "detail": {"runtime": scr[0]["statement"].split(":")[0]}, "label": "drive it through its embedded scripting runtime",
                       "why": "the program embeds a scripting runtime: documented, input-independent control", "trust": "static", "risk": "EU", "score": 1.2 + (2.2 if mouse_bad else 0), "expect": [], "verified": False,
                       "evidence": [scr[0]["id"]]})
    # de-duplicate by (effector, label) keeping the best
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in routes:
        k = (r["effector"], str(r["label"]).lower())
        if k not in best or r["score"] > best[k]["score"]:
            best[k] = r
    out = sorted(best.values(), key=lambda r: -r["score"])
    if mouse_bad:
        for r in out:
            if r["effector"] in ("gesture", "invoke_control", "context") and r["trust"] != "measured":
                r["note"] = "posted pointer input is ignored by this application"
    return out


def plan(app_key: str, task: str, store: Optional[C.AtlasStore] = None, model=None, *, use_model: bool = True) -> Dict[str, Any]:
    store = store or C.get_store()
    if model is None:
        from core_organs import organ_48_app_behavior_model as bm
        model = bm.get_model()
    t0 = time.time()
    channels: Dict[str, Any] = {}
    for c in store.claims(app_key, "input.channel"):
        if isinstance(c.get("value"), dict):
            channels = c["value"]
    try:
        cmds = [c["name"] for c in model.commands(app_key, limit=200)][:100]
    except Exception:
        cmds = []
    ctx = {"commands": cmds, "gestures": sorted({f"{g['gesture']}->{g['effect_class']}" for g in store.gestures(app_key) if g.get("effective")})[:20],
           "scripting": [c["statement"][:60] for c in store.claims(app_key, "stack.scripting")][:3]}
    subs, meta = decompose(task, ctx, use_model=use_model)
    steps: List[Dict[str, Any]] = []
    for i, sg in enumerate(subs):
        rts = collect_routes(app_key, sg, store, model, channels)
        step: Dict[str, Any] = {"n": i + 1, "goal": sg, "grounded": bool(rts), "routes": rts[:5]}
        if rts:
            best = rts[0]
            step["chosen"] = {"effector": best["effector"], "label": best["label"], "trust": best["trust"], "risk": best["risk"], "detail": best["detail"]}
            step["expect"] = best.get("expect", [])
            step["fallbacks"] = [{"effector": r["effector"], "label": r["label"]} for r in rts[1:4]]
        else:
            step["ungrounded"] = "no learned command, control, shortcut, object-model method, switch or gesture supports this sub-goal"
        steps.append(step)
    n_ok = sum(1 for s in steps if s["grounded"])
    return {"app_key": app_key, "task": task, "decomposition": meta, "steps": steps, "grounded": n_ok, "total": len(steps), "complete": n_ok == len(steps), "channels": channels,
            "seconds": round(time.time() - t0, 2)}


# --------------------------------------------------------------------------------------------------
# execution (headless effectors only, verified)
# --------------------------------------------------------------------------------------------------

EXECUTABLE = ("invoke_control", "menu_path", "key", "wm_command", "dialog_path", "ribbon_path")


def _find(nodes, label: str):
    lf = C.fold(label)
    exact = [n for n in nodes if C.fold(n.name) == lf]
    if exact:
        return sorted(exact, key=lambda n: (not n.enabled, n.offscreen))[0]
    part = [n for n in nodes if lf and lf in C.fold(n.name) and len(n.name) < 60]
    return part[0] if part else None


def _invoke(node) -> Tuple[bool, str]:
    from core_organs import organ_63_app_mastery as m63
    for pat, getter, call in (("invoke", "GetInvokePattern", "Invoke"), ("toggle", "GetTogglePattern", "Toggle"), ("select", "GetSelectionItemPattern", "Select"), ("expand", "GetExpandCollapsePattern", "Expand")):
        if pat in node.pats:
            return m63._uia_call(node, getter, call)
    return False, "no actionable pattern"


def execute(pl: Dict[str, Any], hwnd: int, *, dry_run: bool = True, allow_destructive: bool = False, log=print) -> Dict[str, Any]:
    from core_organs import background_window as bw
    from core_organs import fast_uia
    from core_organs import headless_input as hin
    res: Dict[str, Any] = {"steps": [], "dry_run": dry_run}
    with bw.BackgroundSession(hwnd):
        time.sleep(0.4)
        for st in pl["steps"]:
            rec: Dict[str, Any] = {"n": st["n"], "goal": st["goal"]}
            ch = st.get("chosen")
            if not ch:
                rec["status"] = "skipped: ungrounded"
                res["steps"].append(rec)
                continue
            if ch["effector"] not in EXECUTABLE:
                rec["status"] = f"not executable headlessly ({ch['effector']}); route: {ch['label']}"
                res["steps"].append(rec)
                continue
            if ch["risk"] == "E2" and not allow_destructive:
                rec["status"] = "refused: destructive route (allow_destructive=False)"
                res["steps"].append(rec)
                continue
            if dry_run:
                rec["status"] = f"would run {ch['effector']}: {ch['label']}"
                res["steps"].append(rec)
                continue
            before = fast_uia.snapshot(hwnd, timeout_ms=5000) or []
            ok, how = False, ""
            d = ch["detail"]
            if ch["effector"] == "invoke_control":
                n = _find(before, d.get("label", ch["label"]))
                ok, how = _invoke(n) if n else (False, "control not found")
            elif ch["effector"] == "menu_path":
                segs = [s.strip() for s in str(d.get("path", "")).split(">")]
                ok, how = True, "menu path"
                for s in segs:
                    n = _find(fast_uia.snapshot(hwnd, timeout_ms=5000) or [], s)
                    if not n:
                        ok, how = False, f"menu entry '{s}' not found"
                        break
                    ok, how = _invoke(n)
                    time.sleep(0.35)
                    if not ok:
                        break
            elif ch["effector"] == "ribbon_path":
                from . import uimap as _um
                dr = _um.drive(hwnd, d.get("path") or [])
                ok, how = bool(dr.get("ok")), dr.get("why") or "; ".join(str(x) for x in dr.get("steps", []))[:200]
            elif ch["effector"] == "key":
                ok, how = hin.post_key_combo(hwnd, d.get("keys", ""))
            elif ch["effector"] == "wm_command":
                ok = bool(hin._u32.PostMessageW(hwnd, 0x111, int(d.get("menu_id", 0)), 0))
                how = "WM_COMMAND"
            elif ch["effector"] == "dialog_path":
                op = d.get("opener_path") or d.get("opener")
                n = _find(before, d.get("opener") or "") if d.get("opener") else None
                if n is None and op:
                    n = _find(before, str(op).split(">")[-1])
                ok, how = _invoke(n) if n else (False, "opener not found")
                time.sleep(0.8)
            time.sleep(0.5)
            after = fast_uia.snapshot(hwnd, timeout_ms=5000) or []
            names_b, names_a = {C.fold(n.name) for n in before if n.name}, {C.fold(n.name) for n in after if n.name}
            changed = (names_b != names_a) or len(before) != len(after)
            rec.update(status="done" if ok else f"failed: {how}", delivered=ok, how=how, structure_changed=changed, new_controls=sorted(names_a - names_b)[:12], gone=sorted(names_b - names_a)[:12])
            res["steps"].append(rec)
            log(f"  step {st['n']}: {rec['status']}  ({ch['effector']}: {ch['label']})")
    return res
