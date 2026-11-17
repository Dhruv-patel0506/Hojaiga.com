"""
atlas.teach -- the TEACHER: "how do I ... in this application?" answered from what the scanner actually saw.

The cartographer (atlas.uimap) leaves a structured map: surface (ribbon tab / menu bar / File view) -> group -> control -> what it leads to (menu items, gallery
items, a dialog with its fields). This module turns that map into

    howto(app, "insert a picture")   ranked ROUTES, each a list of human steps ("Open the Insert tab > in the Images group open the Pictures drop-down > choose
                                     This Device...") with the shortcut, what appears next (a dialog and its fields), preconditions (a control that was
                                     DISABLED when scanned needs a selection first) and the evidence behind it
    overview(app)                    what the application is, section by section, from the map
    explain(app, "Pictures")         one control: where it lives, what it opens, its shortcut and state

Everything is read from the stored map; nothing is invented. A question the map cannot answer says so and lists the nearest things it does know.
Matching is lexical (stemmed, camel-case split, small general-English synonym table) and, when the local model is reachable, expanded with a few related words
the model proposes for the task. The synonym table is general vocabulary (picture/image), never application names.
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import common as C

SYN: Dict[str, List[str]] = {
    "image": ["picture", "photo", "graphic", "illustration", "icon"], "picture": ["image", "photo", "graphic"], "photo": ["picture", "image"], "pic": ["picture", "image"],
    "table": ["grid", "spreadsheet"], "chart": ["graph", "plot", "diagram"], "graph": ["chart", "plot"], "diagram": ["smartart", "flowchart", "chart"],
    "delete": ["remove", "erase", "clear"], "remove": ["delete", "erase", "clear"], "color": ["colour", "fill", "shade", "tint"], "colour": ["color", "fill"],
    "font": ["typeface", "text", "type"], "text": ["font", "word", "type", "label"], "size": ["scale", "resize", "dimension"], "bold": ["strong", "emphasis"],
    "save": ["store", "keep"], "open": ["load", "browse"], "new": ["create", "add", "blank"], "add": ["insert", "create", "new"], "insert": ["add", "place", "embed"], "create": ["new", "make", "add"],
    "make": ["create", "new"], "undo": ["revert"], "copy": ["duplicate"], "paste": ["insert"], "find": ["search", "locate"], "search": ["find", "locate"], "replace": ["substitute", "change"],
    "video": ["movie", "clip", "media"], "audio": ["sound", "music", "narration"], "sound": ["audio", "music"], "link": ["hyperlink", "url"], "hyperlink": ["link", "url"],
    "page": ["slide", "sheet"], "slide": ["page"], "sheet": ["worksheet", "tab"], "shape": ["rectangle", "oval", "line", "arrow"], "style": ["theme", "format", "design"],
    "theme": ["design", "style", "template"], "design": ["theme", "layout"], "animation": ["motion", "effect"], "transition": ["effect", "change"], "header": ["heading", "title"],
    "footer": ["bottom"], "number": ["numbering", "count", "digit"], "list": ["bullet", "numbering"], "bullet": ["list"], "align": ["alignment", "justify", "center"],
    "margin": ["indent", "spacing", "padding"], "border": ["outline", "line", "frame"], "print": ["printing", "output"], "export": ["save as", "publish", "convert"], "share": ["send", "collaborate"],
    "comment": ["note", "annotation", "review"], "spell": ["proofing", "spelling", "grammar"], "zoom": ["magnify", "scale"], "view": ["display", "show", "mode"], "draw": ["pen", "ink", "sketch"],
    "formula": ["function", "calculation", "equation"], "equation": ["formula", "math"], "symbol": ["character", "special"], "reference": ["citation", "bibliography", "footnote"],
    "citation": ["reference", "source", "bibliography"], "footnote": ["reference", "note"], "toc": ["table of contents"], "contents": ["toc"], "ai": ["designer", "copilot", "ideas", "intelligent"],
}
STOP = {"the", "a", "an", "to", "in", "on", "of", "and", "is", "it", "do", "does", "how", "what", "which", "can", "i", "you", "this", "that", "for", "with", "are", "my", "me", "want", "need", "please",
        "should", "would", "could", "from", "into", "using", "use", "app", "application", "program", "way", "make", "get", "put", "be", "by", "at", "or", "so", "if", "then", "when", "where"}
LIGHT = {"add", "insert", "creat", "make", "new", "chang", "set", "use", "open", "show", "turn", "appl", "edit", "get", "go", "do", "have", "need", "start", "want"}
NOISE_MEMBERS = {"AddRef", "Release", "QueryInterface", "GetTypeInfo", "GetTypeInfoCount", "GetIDsOfNames", "Invoke", "Dispose", "Finalize", "ToString", "Equals", "GetHashCode"}
_W = re.compile(r"[a-z0-9]+")


def stem(w: str) -> str:
    w = w.lower()
    for suf in ("ations", "ation", "ings", "ing", "ies", "ied", "ed", "es", "s", "e"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[:-len(suf)] + ("y" if suf in ("ies", "ied") else "")
            break
    return w[:8]


def toks(s: str, keep_stop: bool = False) -> List[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s or "")
    s = re.sub(r"[_\-\.‑]+", " ", s)
    return [stem(w) for w in _W.findall(s.lower()) if len(w) > 1 and (keep_stop or w not in STOP)]


def map_path(key: str) -> str:
    return os.path.join(C.ATLAS_DIR, "uimap", f"{key}.json")


def load_map(key: str) -> Dict[str, Any]:
    try:
        with open(map_path(key), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


# ---------------------------------------------------------------------------------------------------- flatten
def flatten(m: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every control / menu item / gallery item / dialog field as an entry carrying its full path."""
    out: List[Dict[str, Any]] = []

    def add(path: List[Tuple[str, str]], c: Dict[str, Any], surf: Dict[str, Any], group: str, depth: int, parent: Optional[Dict[str, Any]]) -> None:
        lt = c.get("leads_to") or {}
        ent = {"path": path, "name": c.get("name", ""), "kind": c.get("kind", ""), "aid": c.get("aid", ""), "accel": c.get("accel", ""), "enabled": c.get("enabled", True), "surface": surf["name"],
               "surface_kind": surf["kind"], "group": group, "depth": depth, "lt": lt, "state": c.get("state", ""), "help": c.get("help", ""), "parent": parent}
        out.append(ent)
        items = lt.get("items") if isinstance(lt.get("items"), list) else []
        for it in items:
            if isinstance(it, dict):
                add(path + [("item", it["name"])], it, surf, group, depth + 1, ent)
            elif isinstance(it, str):
                out.append({"path": path + [("item", it)], "name": it, "kind": "item", "aid": "", "accel": "", "enabled": True, "surface": surf["name"], "surface_kind": surf["kind"], "group": group,
                            "depth": depth + 1, "lt": {}, "state": "", "help": "", "parent": ent})
        for f in lt.get("fields") or []:
            if isinstance(f, dict) and f.get("name"):
                out.append({"path": path + [("dialog", lt.get("dialog") or "dialog"), ("field", f["name"])], "name": f["name"], "kind": "field:" + f.get("kind", ""), "aid": "", "accel": "", "enabled": True,
                            "surface": surf["name"], "surface_kind": surf["kind"], "group": group, "depth": depth + 2, "lt": {}, "state": "", "help": "", "parent": ent, "dialog": lt.get("dialog")})

    for s in m.get("surfaces", []):
        for g in s.get("groups", []):
            for c in g.get("controls", []):
                base = [("surface", s["name"])]
                if g.get("name") and g["name"] not in ("(ungrouped)", "Backstage pages", ""):
                    base.append(("group", g["name"]))
                add(base + [("control", c["name"])], c, s, g.get("name", ""), 0, None)
    return out


# ---------------------------------------------------------------------------------------------------- scoring
def expand_query(question: str, use_model: bool = True) -> Tuple[List[str], Dict[str, float], Dict[str, Any]]:
    """(query stems, weights, meta). Original words weigh 1.0, vocabulary synonyms 0.6, model-proposed related words 0.5."""
    base = toks(question)
    w: Dict[str, float] = {t: 1.0 for t in base}
    raw = [x for x in _W.findall(question.lower()) if x not in STOP]
    for r in raw:
        for syn in SYN.get(r, []) + SYN.get(stem(r), []):
            for t in toks(syn):
                w.setdefault(t, 0.6)
    meta: Dict[str, Any] = {"synonyms": True}
    if use_model:
        try:
            from . import llm
            if llm.available():
                r = llm.chat("You help find a command in a desktop application's menus. Given the user's goal, list up to 8 SHORT words or 2-word phrases that a menu item, ribbon button or dialog for it "
                             "would probably contain. Reply JSON only: {\"words\": [\"...\"]}", f"GOAL: {question}", timeout=40, max_tokens=120)
                ws = (r.get("json") or {}).get("words") if isinstance(r.get("json"), dict) else None
                if isinstance(ws, list):
                    for x in ws[:8]:
                        for t in toks(str(x)):
                            w.setdefault(t, 0.5)
                    meta["model_words"] = [str(x) for x in ws[:8]]
        except Exception:
            pass
    return list(w.keys()), w, meta


def score_entries(entries: List[Dict[str, Any]], qt: List[str], w: Dict[str, float]) -> List[Tuple[float, Dict[str, Any]]]:
    # document frequency over entry names for an IDF
    N = max(1, len(entries))
    df: Dict[str, int] = {}
    cache: List[Tuple[set, set, set, set]] = []
    for e in entries:
        nm = set(toks(e["name"]))
        ids = set(toks(e["aid"]))
        ctx = set(toks(" ".join(p[1] for p in e["path"][:-1] if p[0] in ("surface", "group", "control", "item"))))
        extra = set(toks((e.get("help") or "") + " " + " ".join(str(x.get("name", "")) for x in (e["lt"].get("fields") or [])[:12] if isinstance(x, dict)) + " " + (e["lt"].get("dialog") or "")))
        cache.append((nm, ids, ctx, extra))
        for t in nm | ids:
            df[t] = df.get(t, 0) + 1
    scored: List[Tuple[float, Dict[str, Any]]] = []
    content = [t for t in qt if t not in LIGHT]
    orig = {t for t in qt if w.get(t, 1.0) >= 1.0}
    for e, (nm, ids, ctx, extra) in zip(entries, cache):
        n_name = max(1, len(nm))
        exact = syn = 0.0                                   # evidence from the user's own words vs from synonyms (a synonym family can only add ONE hit's worth)
        m_name = set()
        best_syn = 0.0
        for t in qt:
            wt = w.get(t, 1.0) * (0.25 if t in LIGHT and content else 1.0)    # "add" / "insert" / "make" say little; the thing being added says everything
            idf = math.log(1 + N / (1 + df.get(t, 0)))
            if t in nm:
                v, m_name = 3.0 * wt * idf, m_name | {t}
            elif t in ids:
                v = 2.0 * wt * idf
            elif t in extra:
                v = 0.8 * wt * idf
            elif t in ctx:
                v = 0.5 * wt * idf
            else:
                continue
            if t in orig:
                exact += v
            else:
                best_syn = max(best_syn, v)
        s = exact + best_syn
        if s <= 0:
            continue
        hit = [t for t in content if t in nm or t in ids or t in extra or t in ctx]
        if content and not hit:
            continue                                                              # only a light verb matched: not an answer
        s *= 0.5 + 0.5 * len(m_name) / n_name                                     # a name that IS the thing beats a long name that merely contains it
        s *= 0.5 + 0.5 * len(hit) / max(1, len(content))                          # ... and every content word of the question should be accounted for
        if exact <= 0 and content:
            s *= 0.45                                                             # matched only through synonyms of the user's words
        if e["kind"].startswith("field"):
            s *= 0.55                                                             # a dialog field is rarely THE answer, but explains a route
        if e["surface_kind"] == "backstage":
            s *= 0.9
        s *= 1.0 / (1.0 + 0.12 * e["depth"])
        if not e["enabled"]:
            s *= 0.85
        scored.append((s, e))
    scored.sort(key=lambda x: -x[0])
    return scored


# ---------------------------------------------------------------------------------------------------- rendering
def _step_texts(e: Dict[str, Any]) -> List[str]:
    steps: List[str] = []
    sk = e["surface_kind"]
    path = e["path"]
    lt = e["lt"]
    surf = next((v for k, v in path if k == "surface"), "")
    group = next((v for k, v in path if k == "group"), "")
    ctrl = next((v for k, v in path if k == "control"), "")
    if sk == "ribbon-tab":
        steps.append(f"Open the **{surf}** tab of the ribbon")
        if group:
            steps.append(f"in the **{group}** group")
    elif sk == "menubar":
        steps.append(f"Open the **{ctrl}** menu in the menu bar" if len(path) <= 2 else f"Open the **{ctrl}** menu in the menu bar")
    elif sk == "backstage":
        steps.append("Open the **File** menu (the full-screen File view)")
    else:
        steps.append(f"In **{surf}**")
    # control + items
    items = [v for k, v in path if k == "item"]
    if sk == "menubar":
        if not items:
            pass
        else:
            steps.append("choose " + " > ".join(f"**{i}**" for i in items))
    else:
        parent_kind = "drop-down" if (items or lt.get("type") in ("menu", "gallery")) else "button"
        if not items:
            verb = {"toggle": "turn on/off", "checkbox": "tick", "combobox": "set", "edit": "type into", "spinner": "set", "slider": "set"}.get(e["kind"], "click")
            steps.append(f"{verb} **{ctrl}**")
        else:
            steps.append(f"open the **{ctrl}** drop-down")
            steps.append("choose " + " > ".join(f"**{i}**" for i in items))
    return steps


def _outcome(e: Dict[str, Any]) -> str:
    lt = e["lt"]
    t = lt.get("type", "")
    if t == "dialog" and lt.get("dialog"):
        fields = [f["name"] for f in (lt.get("fields") or []) if isinstance(f, dict) and f.get("name")][:10]
        return f"A dialog **{lt['dialog']}** opens" + (f" with: {', '.join(fields)}" if fields else "") + (f" (confirm with **{lt['commit']}**, back out with **{lt['cancel']}**)" if lt.get("commit") and lt.get("cancel") else "")
    if t in ("menu", "gallery") and lt.get("items"):
        names = [i["name"] if isinstance(i, dict) else str(i) for i in lt["items"]]
        txt = f"It offers {len(names)} choice(s): " + ", ".join(names[:10]) + (" ..." if len(names) > 10 else "")
        more = []
        for i in lt["items"]:
            if isinstance(i, dict) and (i.get("leads_to") or {}).get("type") == "dialog":
                il = i["leads_to"]
                flds = [f["name"] for f in (il.get("fields") or []) if isinstance(f, dict) and f.get("name")][:8]
                more.append(f"choosing **{i['name']}** opens the dialog **{il.get('dialog')}**" + (f" ({', '.join(flds)})" if flds else ""))
        if more:
            txt += ". " + "; ".join(more[:3])
        return txt
    if t == "toggle":
        return "It switches a setting on or off" + (f" (was {e['state']} when scanned)" if e.get("state") else "")
    if t == "pane":
        return "A side pane opens in the window"
    if t in ("value-entry", "choice-list"):
        return "You set a value there"
    return ""


def route_of(e: Dict[str, Any], score: float) -> Dict[str, Any]:
    steps = _step_texts(e)
    pre: List[str] = []
    if not e["enabled"]:
        pre.append("this control was DISABLED when scanned: it needs something selected or created first (an object, text, a table...)")
    p = e["parent"]
    if p is not None and not p.get("enabled", True):
        pre.append(f"'{p['name']}' was disabled when scanned (needs a selection first)")
    out = _outcome(e)
    return {"score": round(score, 2), "steps": steps, "text": " > ".join(steps), "shortcut": e["accel"] or (p or {}).get("accel", ""), "outcome": out, "preconditions": pre, "control": e["name"],
            "kind": e["kind"], "surface": e["surface"], "dialog": e["lt"].get("dialog") or e.get("dialog") or "", "automation_id": e["aid"],
            "path": [{"kind": k, "name": v} for k, v in e["path"]]}


# ---------------------------------------------------------------------------------------------------- public API
def routes_for(key: str, question: str, *, limit: int = 5, use_model: bool = True, entries: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    m = load_map(key)
    if entries is None:
        entries = flatten(m) if m else []
    if not entries:
        return {"ok": False, "why": "no UI map for this application yet (run: hojaiga_atlas.py learn <app> --tier full)", "routes": []}
    qt, w, meta = expand_query(question, use_model)
    if not qt:
        return {"ok": False, "why": "the question has no usable words", "routes": []}
    scored = score_entries(entries, qt, w)
    routes: List[Dict[str, Any]] = []
    seen = set()
    for s, e in scored:
        k = (e["name"].lower(), tuple(p[1] for p in e["path"][:2]))
        if k in seen:
            continue
        seen.add(k)
        routes.append(route_of(e, s))
        if len(routes) >= limit:
            break
    return {"ok": bool(routes), "routes": routes, "query": {"stems": qt, **meta}, "entries": len(entries)}


def _com_libs(key: str) -> List[Dict[str, Any]]:
    f = os.path.join(C.ATLAS_DIR, "com", f"{key}.json")
    try:
        with open(f, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        progs = [c.get("progid") for c in d.get("classes", []) if c.get("progid")]
        return [dict(lib, _progids=progs) for lib in (d.get("typelibs") or {}).values() if lib.get("ok")]
    except Exception:
        return []


def api_routes(key: str, question: str, *, limit: int = 3, store: Optional[C.AtlasStore] = None) -> List[Dict[str, Any]]:
    """Programmatic ways to do the same thing: the program's registered object model (COM type library: member names + parameter names) and the operators its own
    runtime reported (introspection). Input-independent, so they matter for programs that ignore posted input."""
    qt, w, _ = expand_query(question, False)
    out: List[Dict[str, Any]] = []
    for lib in _com_libs(key):
        sigs = lib.get("sigs") or {}
        meth = lib.get("methods") or {}
        seen = set()
        for tname in set(list(sigs.keys()) + list(meth.keys())):
            tt = set(toks(tname.lstrip("_")))
            for m in list(sigs.get(tname, {}).keys()) + [x for x in meth.get(tname, []) if "[" not in x]:
                if (tname, m) in seen or m in NOISE_MEMBERS or tname.startswith("E") and tname.endswith(("Application", "Events")) or tname.endswith("Events"):
                    continue
                seen.add((tname, m))
                mt = set(toks(m))
                s = sum(3.0 * w.get(t, 1.0) for t in qt if t in mt) + sum(1.0 * w.get(t, 1.0) for t in qt if t in tt)
                if s <= 0 or not any(t in mt for t in qt):
                    continue
                params = sigs.get(tname, {}).get(m)
                call = (f"{tname.lstrip('_')}.{m}(" + ", ".join(params) + ")") if params is not None else f"{tname.lstrip('_')}.{m}"
                out.append({"score": s + (0.8 if params is not None else 0.0), "via": "COM object model" + (f" ({lib['_progids'][0]})" if lib.get("_progids") else ""),
                            "member": f"{tname.lstrip('_')}.{m}", "call": call, "params": params or []})
    try:
        from . import introspect
        st = store or C.get_store()
        tmpl = introspect.call_template_of(key, st)
        if tmpl:
            for o in introspect.operators_of(key, st):
                mt = set(toks(o.get("name", ""))) | set(toks(o["id"].replace(".", " ").replace("_", " ")))
                s = sum(3.0 * w.get(t, 1.0) for t in qt if t in mt)
                if s > 0:
                    out.append({"score": s, "via": "the program's own scripting runtime", "member": o["id"], "call": tmpl.format(id=o["id"]), "params": [x[0] for x in o.get("props", [])][:8],
                                "doc": o.get("desc", "")[:120]})
    except Exception:
        pass
    out.sort(key=lambda r: -r["score"])
    return out[:limit]


def howto(key: str, question: str, *, limit: int = 4, use_model: bool = True) -> Dict[str, Any]:
    res = routes_for(key, question, limit=limit, use_model=use_model)
    if not res.get("ok"):
        res["answer"] = res.get("why") or "The scanned map does not contain anything that matches that."
        return res
    best = res["routes"][0]
    lines = [f"To **{question.strip().rstrip('?.')}** in this application:", "", f"1. {best['text']}."]
    if best["outcome"]:
        lines.append(f"   {best['outcome']}.")
    if best["shortcut"]:
        lines.append(f"   Shortcut: **{best['shortcut']}**.")
    for p in best["preconditions"]:
        lines.append(f"   Note: {p}.")
    if len(res["routes"]) > 1:
        lines += ["", "Other ways / related controls:"]
        for r in res["routes"][1:]:
            lines.append(f"- {r['text']}" + (f" ({r['shortcut']})" if r["shortcut"] else "") + (f" - {r['outcome']}" if r["outcome"] else ""))
    try:
        api = api_routes(key, question)
    except Exception:
        api = []
    if api:
        res["api"] = api
        lines += ["", "Programmatic route (no clicking):"]
        for a in api[:2]:
            lines.append(f"- `{a['call']}` - {a['via']}" + (f"; {a['doc']}" if a.get("doc") else ""))
    res["answer"] = "\n".join(lines)
    res["best"] = best
    return res


def explain(key: str, control: str) -> Dict[str, Any]:
    entries = flatten(load_map(key))
    q = C.fold(control)
    cands = [e for e in entries if C.fold(e["name"]) == q] or [e for e in entries if q in C.fold(e["name"])]
    if not cands:
        return {"ok": False, "why": f"no control called '{control}' in the map"}
    cands.sort(key=lambda e: e["depth"])
    e = cands[0]
    r = route_of(e, 1.0)
    r["alternatives"] = [route_of(x, 0.5)["text"] for x in cands[1:5]]
    r["ok"] = True
    return r


def overview(key: str) -> Dict[str, Any]:
    m = load_map(key)
    if not m:
        return {"ok": False, "why": "no UI map for this application yet"}
    secs = []
    for s in m.get("surfaces", []):
        groups = []
        for g in s.get("groups", []):
            names = [c["name"] for c in g.get("controls", [])]
            groups.append({"group": g.get("name") or "", "controls": len(names), "sample": names[:8]})
        secs.append({"surface": s["name"], "kind": s["kind"], "groups": groups, "controls": sum(x["controls"] for x in groups)})
    return {"ok": True, "app": key, "surfaces": secs, "stats": m.get("stats", {}), "workspace": m.get("workspace")}


# ---------------------------------------------------------------------------------------------------- descriptions + workflows
def describe(key: str, control: str, *, use_model: bool = True) -> Dict[str, Any]:
    """What does this control DO, in plain words. The structural facts come from the map (certain); the one-sentence meaning comes from the local language model
    reading ONLY that context (marked inferred - it is the model's understanding of the label, not something the scan measured)."""
    ex = explain(key, control)
    if not ex.get("ok"):
        return ex
    ex["trust"] = "measured (structure)"
    if not use_model:
        return ex
    try:
        from . import llm
        if not llm.available():
            return ex
        ctx = {"control": ex["control"], "where": ex["text"].replace("**", ""), "shortcut": ex["shortcut"], "outcome": ex["outcome"].replace("**", ""), "dialog": ex["dialog"]}
        r = llm.chat("You explain desktop-application commands to a beginner. Using ONLY the context, say in 1-2 plain sentences what the control does and when a person would use it. "
                     "Do not invent options that are not in the context. Reply JSON: {\"meaning\": \"...\"}", json.dumps(ctx), timeout=60, max_tokens=160)
        mean = (r.get("json") or {}).get("meaning") if isinstance(r.get("json"), dict) else None
        if isinstance(mean, str) and mean.strip():
            ex["meaning"] = mean.strip()
            ex["meaning_trust"] = "inferred (local model reading the scanned context)"
    except Exception:
        pass
    return ex


def workflow(key: str, task: str, *, use_model: bool = True) -> Dict[str, Any]:
    """A multi-step task ("make a short presentation with a title slide, a picture and a table"): decomposed into sub-goals, each answered with its best route from the
    scanned map (and a programmatic alternative where the object model has one). Ungrounded steps are said to be ungrounded."""
    from . import planner
    from core_organs import organ_48_app_behavior_model as bm
    st = C.get_store()
    pl = planner.plan(key, task, st, bm.get_model(), use_model=use_model)
    steps = []
    for stp in pl["steps"]:
        rts = [r for r in stp.get("routes", []) if r["effector"] in ("ribbon_path", "dialog_path", "menu_path", "invoke_control", "api_operator", "com_method")]
        item = {"n": stp["n"], "goal": stp["goal"], "grounded": stp["grounded"]}
        if rts:
            item["route"] = rts[0]["label"]
            item["why"] = rts[0].get("why", "")
            item["effector"] = rts[0]["effector"]
        elif stp.get("chosen"):
            item["route"] = stp["chosen"]["label"]
            item["effector"] = stp["chosen"]["effector"]
        api = api_routes(key, stp["goal"], limit=1)
        if api:
            item["programmatic"] = api[0]["call"] + " (" + api[0]["via"] + ")"
        steps.append(item)
    lines = [f"Plan for: {task}", ""]
    for i in steps:
        lines.append(f"{i['n']}. {i['goal']}" + ("" if i["grounded"] else "  [NOT GROUNDED: the scan found nothing for this]"))
        if i.get("route"):
            lines.append(f"   {i['route']}" + (f" - {i['why']}" if i.get("why") else ""))
        if i.get("programmatic"):
            lines.append(f"   or by code: {i['programmatic']}")
    return {"ok": True, "steps": steps, "complete": pl.get("complete"), "answer": "\n".join(lines), "decomposition": pl.get("decomposition")}
