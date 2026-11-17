"""
professor.workflows -- THE GUIDES, AS A LIBRARY OF WORKFLOWS: every procedure a user guide describes, read, analysed against the application's real controls, and written down in a form that is readable by a
person, fetchable by a program, and runnable by the Professor (through the virtual cursor, step by step, with every step verified).

Nothing in a workflow is written by the Professor: the goal, the steps' wording and the source URL are the guide's. What the Professor adds is the ANALYSIS of each step against the live application:
which control it names (path / label / chord / typed text / a pick from a group / optional / a file dialog), how it would be performed (route), how safe it is, what it needs (a file dialog, the
clipboard, a pointer gesture, a human, an account), and what happened the last time it was run.

  build(app)            guides + catalog -> data/professor/workflows/<app>.json, <app>.md ; INDEX.json / INDEX.md for every application
  fetch(app, query)     the workflows whose goal / steps match a request, best first            get(id)  one workflow
  record_run(report)    after a run: every workflow gets its last result (ok / blocked / failed / skipped, with the reason and the report)
  to_task(workflow)     the structure AppRun.run_task() performs                              run(app, id)  perform it on an owned instance with the virtual cursor shown
The same format is used for every application; no step or rule here names one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import config as CFG
from .schema import fold

WF_DIR = os.path.join(CFG.DATA_DIR, "workflows")
GLYPH = {"ok": "✔", "blocked": "⏸", "failed": "✖", "skipped": "·", "never": "○"}
STATUS_ORDER = ["runnable", "needs-file-dialog", "needs-pointer", "needs-human", "partial", "ungrounded", "other-edition"]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:48] or "workflow"


def workflow_id(app: str, goal: str, cite: str, steps: Sequence[Any]) -> str:
    h = hashlib.sha1((goal + "|" + cite + "|" + "|".join(getattr(s, "raw", str(s)) for s in steps)).encode("utf-8", "replace")).hexdigest()[:6]
    return f"{_slug(app)}.{_slug(goal)}-{h}"


# ----------------------------------------------------------------------------------------------------------------- analysis
def _needs(step: Any, how: str, verb: Any) -> List[str]:
    from .dialogs import is_file_step_text, COPY_RX, PASTE_RX
    from .apprun import ACCOUNT_RX
    need: List[str] = []
    raw = getattr(step, "raw", "") or ""
    key = f"{getattr(verb, 'label', '')} {getattr(verb, 'shortcut', '')} {getattr(step, 'chord', '')} {getattr(step, 'target', '')}"
    if how == "dialog" or is_file_step_text(raw):
        need.append("file_dialog")
    if COPY_RX.search(key) or PASTE_RX.search(key):
        need.append("clipboard")
    if how == "gesture":
        need.append("pointer")
    if how == "human":
        need.append("human")
    if ACCOUNT_RX.search(raw):
        need.append("account")
    return need


def app_words_for(app_key: str, catalog: Any = None) -> Tuple[str, ...]:
    """The words a guide uses for the application itself ('Open PowerPoint'): its catalog name / key / process names from the guide corpus catalogue, and the catalog's title."""
    words = set()
    try:
        from .knowledge import guide_corpus as GCP
        a = GCP.find_app(app_key)
        if a:
            for s in [a.get("name", ""), a.get("key", "")] + [p.rsplit(".", 1)[0] for p in a.get("processes", [])]:
                words |= {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2 and w not in ("microsoft", "windows", "app", "the")}
    except Exception:
        pass
    words |= {w for w in re.findall(r"[a-z0-9]+", (app_key + " " + getattr(catalog, "title", "") + " " + str(getattr(catalog, "process", "")).rsplit(".", 1)[0]).lower()) if len(w) > 2}
    return tuple(sorted(words - {"exe", "microsoft", "windows"}))


def analyse_steps(steps: Sequence[Any], catalog: Any, app_words: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """Each parsed guide step, grounded against the catalog, as a plain dict."""
    from .knowledge import guide_steps as GS
    from . import safety
    out: List[Dict[str, Any]] = []
    near: Sequence[str] = ()
    rc = False
    for st in steps:
        g = GS.ground_step(st, catalog, near, app_words, rc)
        rc = st.action == "right_click"
        v = g.verb
        if v is not None:
            near = GS.near_of(v)
        cls = safety.classify(v.label, " ".join(v.path)) if v is not None else "n/a"
        route = ""
        if v is not None:
            route = ("shortcut:" + v.shortcut) if v.shortcut else ("command" if v.command_id else "control")
        elif g.how == "typed":
            route = "text:posted > text:uia"
        elif g.how == "key":
            route = "key"
        elif g.how == "dialog":
            route = "dialog: sandbox file"
        out.append({"n": st.n, "text": st.raw, "action": st.action, "target": st.target, "path": list(st.path), "typed": st.text, "chord": st.chord, "how": g.how, "verb": (v.label if v else ""),
                    "verb_path": (list(v.path) if v else []), "verb_id": (v.id if v else ""), "shortcut": (v.shortcut if v else ""), "route": route, "safety": cls, "confidence": round(float(g.conf), 2),
                    "needs": _needs(st, g.how, v), "note": g.note, "alts": list(st.alts), "optional": bool(st.optional), "group": st.group, "cite": st.cite})
    return out


def _status(steps: Sequence[Dict[str, Any]]) -> str:
    from .knowledge.guide_steps import GROUNDED_HOW, EXCLUDED_HOW
    if steps and all(s["how"] in EXCLUDED_HOW for s in steps):
        return "other-edition"
    steps = [s for s in steps if s["how"] not in EXCLUDED_HOW]
    hows = [s["how"] for s in steps]
    if not steps:
        return "ungrounded"
    if all(h in GROUNDED_HOW for h in hows):
        return "needs-file-dialog" if any("file_dialog" in s["needs"] for s in steps) else "runnable"
    if "gesture" in hows:
        return "needs-pointer"
    if "human" in hows:
        return "needs-human"
    return "partial" if sum(1 for h in hows if h in GROUNDED_HOW) * 2 >= len(hows) else "ungrounded"


# ----------------------------------------------------------------------------------------------------------------- build
def build(app_key: str, ix: Any = None, catalog: Any = None, guide_key: str = "", write: bool = True) -> Dict[str, Any]:
    """Every procedure of the application's guide, analysed against its catalog (data/professor/catalogs/<app>.json when no catalog is given)."""
    from .harvest import Catalog
    from .knowledge import guide_card as GC
    from .knowledge import manual_rag as MR
    own = ix is None
    ix = ix or MR.ManualIndex()
    try:
        gkey = guide_key or app_key
        cat = catalog if catalog is not None else (Catalog.load(app_key) or Catalog(app_key=app_key))
        procs = GC.procedures(gkey, ix, min_steps=1, max_steps=14)
        words = app_words_for(gkey, cat)
        from .knowledge import guide_steps as _GS
        _GS.SANDBOX_FILES = True                                            # as in every AppRun: file dialogs are completed with sandbox files by professor.dialogs
        old = load(app_key) or {}
        old_runs = {w["id"]: w.get("runs", []) for w in old.get("workflows", [])}
        wfs: List[Dict[str, Any]] = []
        explained: Dict[str, List[str]] = {}
        for p in procs:
            steps = analyse_steps(p["steps"], cat, words)
            wid = workflow_id(app_key, p["goal"], p["cite"], p["steps"])
            from .knowledge.guide_steps import GROUNDED_HOW, EXCLUDED_HOW
            grounded = sum(1 for s in steps if s["how"] in GROUNDED_HOW)
            outside = sum(1 for s in steps if s["how"] in EXCLUDED_HOW)
            requires = sorted({n for s in steps for n in s["needs"]})
            wf = {"id": wid, "app": app_key, "goal": p["goal"], "source": p["source"], "cite": p["cite"], "steps": steps, "step_count": len(steps), "grounded_share": round(grounded / max(1, len(steps) - outside), 2) if len(steps) > outside else 0.0,
                  "grounded_n": grounded, "outside_n": outside, "requires": requires, "status": _status(steps), "runs": old_runs.get(wid, [])}
            wf["last_run"] = wf["runs"][-1] if wf["runs"] else {"result": "never", "reason": "", "at": ""}
            wfs.append(wf)
            for s in steps:
                if s["verb_id"]:
                    explained.setdefault(s["verb_id"], []).append(wid)
        functions = [{"path": list(v.path), "label": v.label, "shortcut": v.shortcut, "role": v.role, "leads_to": v.leads_to, "safety": v.safety, "explained_by": explained.get(v.id, [])[:6]}
                     for v in sorted(cat.verbs, key=lambda x: (x.path, x.label.lower()))]
        mentioned = {s["target"] for w in wfs for s in w["steps"] if s["how"] in ("none", "human") and s["target"]}
        doc = {"app": app_key, "guide_key": gkey, "built": time.strftime("%Y-%m-%d %H:%M:%S"), "documents": _docs(ix, gkey), "workflows": wfs,
               "summary": {"workflows": len(wfs), "by_status": {k: sum(1 for w in wfs if w["status"] == k) for k in STATUS_ORDER if any(w["status"] == k for w in wfs)},
                           "steps": sum(w["step_count"] for w in wfs), "grounded_steps": sum(w["grounded_n"] for w in wfs),
                           "outside_steps": sum(w["outside_n"] for w in wfs), "applicable_steps": sum(w["step_count"] - w["outside_n"] for w in wfs),
                           "grounding_applicable": round(sum(w["grounded_n"] for w in wfs) / max(1, sum(w["step_count"] - w["outside_n"] for w in wfs)), 3),
                           "grounding_raw": round(sum(w["grounded_n"] for w in wfs) / max(1, sum(w["step_count"] for w in wfs)), 3),
                           "by_how": {h: sum(1 for w in wfs for st in w["steps"] if st["how"] == h) for h in sorted({st["how"] for w in wfs for st in w["steps"]})},
                           "catalog_functions": len(functions), "functions_explained_by_a_guide": sum(1 for f in functions if f["explained_by"]),
                           "named_by_guide_but_not_in_the_application": sorted(mentioned)[:40]},
               "functions": functions}
        if write:
            save(doc)
        return doc
    finally:
        if own:
            ix.close()


def _docs(ix: Any, key: str) -> int:
    try:
        return int(ix.db.execute("SELECT COUNT(*) FROM docs WHERE app=?", (key,)).fetchone()[0])
    except Exception:
        return 0


# ----------------------------------------------------------------------------------------------------------------- store
def path_of(app_key: str, ext: str = "json") -> str:
    return os.path.join(WF_DIR, f"{_slug(app_key)}.{ext}")


def load(app_key: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path_of(app_key), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def save(doc: Dict[str, Any], out_dir: str = "") -> str:
    d = out_dir or WF_DIR
    os.makedirs(d, exist_ok=True)
    jp = os.path.join(d, f"{_slug(doc['app'])}.json")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False, default=str)
    with open(os.path.join(d, f"{_slug(doc['app'])}.md"), "w", encoding="utf-8") as fh:
        fh.write(to_markdown(doc))
    if not out_dir:
        write_index()
    return jp


def write_index() -> str:
    rows = []
    for fn in sorted(os.listdir(WF_DIR)) if os.path.isdir(WF_DIR) else []:
        if fn.endswith(".json") and fn != "INDEX.json":
            try:
                with open(os.path.join(WF_DIR, fn), encoding="utf-8") as fh:
                    d = json.load(fh)
                s = d.get("summary", {})
                runs = [w.get("last_run", {}).get("result", "never") for w in d.get("workflows", [])]
                rows.append({"app": d["app"], "documents": d.get("documents", 0), "workflows": s.get("workflows", 0), "by_status": s.get("by_status", {}), "steps": s.get("steps", 0),
                             "grounded_steps": s.get("grounded_steps", 0), "ran": {k: runs.count(k) for k in ("ok", "blocked", "failed", "skipped", "never") if runs.count(k)}, "built": d.get("built", ""),
                             "file": fn[:-5] + ".md"})
            except Exception:
                continue
    with open(os.path.join(WF_DIR, "INDEX.json"), "w", encoding="utf-8") as fh:
        json.dump({"updated": time.strftime("%Y-%m-%d %H:%M:%S"), "apps": rows}, fh, indent=1, ensure_ascii=False)
    lines = ["# Workflow library", "", f"_updated {time.strftime('%Y-%m-%d %H:%M:%S')}_ - every procedure of every indexed user guide, analysed against the real application. One file per application.", "",
             "| app | guide docs | workflows | runnable | need file dialog | need pointer | need human | steps grounded | last runs |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        b = r["by_status"]
        lines.append(f"| [{r['app']}]({r['file']}) | {r['documents']} | {r['workflows']} | {b.get('runnable', 0)} | {b.get('needs-file-dialog', 0)} | {b.get('needs-pointer', 0)} | {b.get('needs-human', 0)} | "
                     f"{r['grounded_steps']}/{r['steps']} | " + (", ".join(f"{GLYPH[k]}{v}" for k, v in r["ran"].items()) or "-") + " |")
    p = os.path.join(WF_DIR, "INDEX.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return p


def to_markdown(doc: Dict[str, Any]) -> str:
    s = doc.get("summary", {})
    lines = [f"# {doc['app']} - workflows from the user guide", "",
             f"_built {doc.get('built', '')} from {doc.get('documents', 0)} guide document(s)_", "",
             f"**{s.get('workflows', 0)} workflows** · {s.get('grounded_steps', 0)}/{s.get('steps', 0)} steps tied to a real control · by status: " + ", ".join(f"{k} {v}" for k, v in s.get("by_status", {}).items()),
             f"· {s.get('functions_explained_by_a_guide', 0)} of the application's {s.get('catalog_functions', 0)} functions are explained by at least one guide procedure", ""]
    if s.get("named_by_guide_but_not_in_the_application"):
        lines += ["Named by the guide but not found in the application's catalog (a menu / dialog not opened yet, a different version, or a name the interface spells differently): "
                  + ", ".join(f"`{x}`" for x in s["named_by_guide_but_not_in_the_application"][:20]), ""]
    for w in doc.get("workflows", []):
        lr = w.get("last_run", {})
        lines += [f"## {w['goal']}", "", f"`{w['id']}` · {w['step_count']} steps · {int(w['grounded_share'] * 100)}% grounded · **{w['status']}**"
                  + (f" · needs: {', '.join(w['requires'])}" if w["requires"] else "") + f" · last run: {GLYPH.get(lr.get('result', 'never'), '○')} {lr.get('result', 'never')}"
                  + (f" ({lr['reason'][:90]})" if lr.get("reason") else ""), f"source: {w['source']}", "",
                  "| # | what the guide says | control | how | route | safety |", "|---|---|---|---|---|---|"]
        for st in w["steps"]:
            ctl = " > ".join((st["verb_path"] + [st["verb"]]) if st["verb"] else (st["path"] or ([st["target"]] if st["target"] else [])))
            lines.append(f"| {st['n']} | {st['text'][:110].replace('|', '/')} | {ctl.replace('|', '/')[:60] or '-'} | {st['how']}{' (optional)' if st['optional'] else ''} | {st['route'] or '-'} | {st['safety']} |")
        lines.append("")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------------------------- fetch
def fetch(app_key: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """The workflows of an application that answer a request ('change the header', 'rotate an image'), best match first. Words are stemmed and matched against the goal and the steps."""
    doc = load(app_key) or build(app_key)
    q = {w[:5] for w in fold(query).split() if len(w) > 2}
    scored = []
    for w in doc.get("workflows", []):
        gw = {x[:5] for x in fold(w["goal"]).split() if len(x) > 2}
        sw = {x[:5] for s in w["steps"] for x in fold(s["text"]).split() if len(x) > 2}
        sc = 3.0 * len(q & gw) + 1.0 * len(q & sw) + (0.5 if w["status"] == "runnable" else 0.0)
        if q & (gw | sw):
            scored.append((sc, w))
    scored.sort(key=lambda t: -t[0])
    return [w for _s, w in scored[:limit]]


def get(workflow_id_: str) -> Optional[Dict[str, Any]]:
    app = workflow_id_.split(".", 1)[0]
    for fn in ([f"{app}.json"] + sorted(os.listdir(WF_DIR) if os.path.isdir(WF_DIR) else [])):
        try:
            with open(os.path.join(WF_DIR, fn), encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        for w in d.get("workflows", []):
            if w["id"] == workflow_id_ or w["id"].startswith(workflow_id_):
                return w
    return None


# ----------------------------------------------------------------------------------------------------------------- results
def record_run(app_key: str, report: Dict[str, Any], out_dir: str = "") -> Optional[Dict[str, Any]]:
    """Merge the outcome of a run into the library: each guide procedure that was attempted, blocked on purpose, or set aside gets its last result."""
    doc = load(app_key) or build(app_key, write=False)
    by_goal: Dict[str, Dict[str, Any]] = {}
    for row in report.get("ledger", []) or []:
        by_goal[(row.get("goal", "").lower(), row.get("cite", ""))] = row
    tasks = {(t.get("goal", "").lower(), t.get("cite", "")): t for t in report.get("tasks", []) or []}
    when = report.get("started") or time.strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for w in doc["workflows"]:
        key = (w["goal"].lower(), w["cite"])
        row = by_goal.get(key)
        if row is None:
            continue
        t = tasks.get(key)
        at = (t["attempts"][-1] if t and t.get("attempts") else {})
        entry = {"result": row.get("disposition", "never"), "reason": str(row.get("reason", ""))[:240], "at": when, "steps_done": at.get("done"), "attempts": len(t["attempts"]) if t else 0,
                 "report": report.get("html") or report.get("path") or ""}
        w["runs"] = (w.get("runs", []) + [entry])[-10:]
        w["last_run"] = entry
        n += 1
    doc["summary"]["last_run_matched"] = n
    save(doc, out_dir) if out_dir else save(doc)
    return doc


# ----------------------------------------------------------------------------------------------------------------- run
def to_task(wf: Dict[str, Any]) -> Dict[str, Any]:
    """The structure AppRun.run_task() performs: the guide's own steps (re-parsed from the guide's words) - grounding happens against the LIVE application at run time."""
    from .knowledge import guide_steps as GS
    steps = []
    for s in wf["steps"]:
        gs = GS.parse_line(s["text"], s["n"], s.get("cite", wf.get("cite", "")))
        if gs is not None:
            steps.append(gs)
    return {"goal": wf["goal"], "cite": wf["cite"], "source": wf["source"], "steps": steps, "grounded": wf.get("grounded_share", 0.0)}


def run(app: str, wf_id: str, cursor: bool = True, vision: bool = True) -> Dict[str, Any]:
    """Perform ONE workflow on an owned instance of the application, with the virtual cursor shown (the window is left visible so the cursor can be watched), and record the result."""
    from . import apprun as AR
    wf = get(wf_id)
    if wf is None:
        return {"error": f"no workflow '{wf_id}'"}
    spec = AR.spec_for(app)
    r = AR.AppRun(spec, vision=vision, overlay_visible=cursor, visible=cursor, phases=())
    out: Dict[str, Any] = {}
    try:
        if not r.start():
            return {"error": "could not start an owned instance"}
        r.perceive()
        tr = r.run_task(to_task(wf))
        out = tr.to_dict()
    finally:
        rep = r.finish()
    record_run(wf["app"], {"started": rep.get("started"), "path": rep.get("path"), "html": rep.get("html"), "ledger": [{"goal": wf["goal"], "cite": wf["cite"], "disposition": out.get("final", "failed"),
                                                                                                                      "reason": (out.get("attempts") or [{}])[-1].get("why", "")}], "tasks": [out]})
    return out
