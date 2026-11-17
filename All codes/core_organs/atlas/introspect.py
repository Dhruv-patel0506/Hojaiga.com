"""
atlas.introspect - ask the program's OWN runtime what it can do.

For programs that embed a scripting API (Blender/bpy, ...), running the program headless in a separate invisible process with a recipe script yields the
authoritative inventory: every operator with its description and parameters, every menu (replayed -> real menu structure), panels, editors, modes,
workspaces and the data model. It never touches the user's running window, so it is the safest deep source for programs that are blind to UI automation.

Selection is by evidence (recipes in data/introspect_recipes.json), results are cached by (exe size, mtime), and every claim carries a file+ref evidence.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from . import common as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT_DIR = os.path.join(C.ATLAS_DIR, "introspect")
FLAG_OFF = os.environ.get("HOJAIGA_ATLAS_INTROSPECT", "1") == "0"


def recipes() -> List[Dict[str, Any]]:
    try:
        with open(os.path.join(DATA, "introspect_recipes.json"), "r", encoding="utf-8") as fh:
            return json.load(fh).get("recipes", [])
    except Exception:
        return []


def pick(exe: str) -> Optional[Dict[str, Any]]:
    """The recipe whose evidence matches this program (exe name, or marker files near the exe), else None."""
    if not exe or not os.path.isfile(exe):
        return None
    base, root = os.path.basename(exe).lower(), os.path.dirname(exe)
    for r in recipes():
        m = r.get("match", {})
        if m.get("exe_regex") and re.search(m["exe_regex"], base, re.I):
            return r
        for pat in m.get("files_any", []):
            try:
                if glob.glob(os.path.join(root, pat)):
                    return r
            except Exception:
                continue
    return None


def _cache_path(key: str, exe: str, rid: str) -> str:
    st = os.stat(exe)
    return os.path.join(OUT_DIR, f"{key}_{rid}_{st.st_size}_{int(st.st_mtime)}.json")


def run(exe: str, key: str, *, budget_s: float = 90.0, force: bool = False) -> Dict[str, Any]:
    """Run the matching recipe (cached). Returns {ok, recipe, file, data|why}."""
    if FLAG_OFF:
        return {"ok": False, "why": "disabled (HOJAIGA_ATLAS_INTROSPECT=0)"}
    r = pick(exe)
    if not r:
        return {"ok": False, "why": "no introspection recipe matches this program"}
    os.makedirs(OUT_DIR, exist_ok=True)
    out = _cache_path(key, exe, r["id"])
    t0 = time.time()
    if not force and os.path.isfile(out) and os.path.getsize(out) > 1000:
        try:
            with open(out, "r", encoding="utf-8") as fh:
                return {"ok": True, "recipe": r["id"], "file": out, "data": json.load(fh), "cached": True, "seconds": 0.0, "route": r}
        except Exception:
            pass
    script = os.path.join(DATA, r["script"])
    cmd = [c.format(exe=exe, script=script, out=out) for c in r["command"]]
    try:
        flags = 0x08000000 if os.name == "nt" else 0                 # CREATE_NO_WINDOW; background mode opens no window anyway
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=min(budget_s, r.get("timeout_s", 90)), creationflags=flags, cwd=os.path.dirname(exe))
    except subprocess.TimeoutExpired:
        return {"ok": False, "recipe": r["id"], "why": f"timed out after {budget_s:.0f}s"}
    except Exception as exc:
        return {"ok": False, "recipe": r["id"], "why": f"{type(exc).__name__}: {str(exc)[:120]}"}
    if not os.path.isfile(out):
        return {"ok": False, "recipe": r["id"], "why": "recipe wrote no output: " + (p.stderr or p.stdout or "")[-200:]}
    with open(out, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {"ok": True, "recipe": r["id"], "file": out, "data": data, "cached": False, "seconds": round(time.time() - t0, 1), "route": r}


def to_claims(key: str, res: Dict[str, Any]) -> List[C.Claim]:
    """Evidenced claims from a recipe result. Kinds: api.runtime, api.operators, api.menu, api.panels, api.area, api.mode, ui.workspace."""
    d, f = res["data"], res["file"]
    out: List[C.Claim] = []
    ev = lambda ref, q="": [C.Evidence("runtime", f"{res['recipe']}:{ref}", q or f"dump {os.path.basename(f)}")]
    ver = d.get("version", "")
    out.append(C.Claim(key, "api.runtime", f"Exposes its object model through {res['route']['runtime']} (version {ver}): {d.get('ops_count', 0)} operators, {d.get('menus_count', 0)} menus, {d.get('panels_count', 0)} panels",
                       "measured", 0.97, ev("runtime", f"{res['recipe']} {ver} headless"), {"file": f, "recipe": res["recipe"], "version": ver, "call_template": res["route"].get("call_template", ""),
                                                                                               "workspaces": d.get("workspaces", [])}, "atlas.introspect"))
    for cat, ops in sorted((d.get("operators") or {}).items()):
        names = [o["name"] for o in ops if o.get("name")]
        out.append(C.Claim(key, "api.operators", f"Operator group '{cat}' ({len(ops)}): " + ", ".join(names[:14]) + (" ..." if len(names) > 14 else ""), "measured", 0.95,
                           ev(f"ops:{cat}", f"{len(ops)} operators"), {"group": cat, "ids": [o["id"] for o in ops], "file": f}, "atlas.introspect"))
    for idn, m in sorted((d.get("menus") or {}).items()):
        if not m.get("n_items"):
            continue
        items = [(i.get("id") or i.get("text") or "") for i in m["items"] if i.get("t") in ("op", "menu")]
        out.append(C.Claim(key, "api.menu", f"Menu '{m.get('label') or idn}' [{idn}] offers: " + ", ".join(i for i in items[:12] if i) + (" ..." if len(items) > 12 else ""), "measured", 0.9,
                           ev(f"menu:{idn}", f"{m['n_items']} entries replayed"), {"menu": m.get("label") or idn, "id": idn, "items": m["items"][:120]}, "atlas.introspect"))
    spaces: Dict[str, List[str]] = {}
    for p in d.get("panels") or []:
        spaces.setdefault(p.get("space") or "?", []).append(p.get("label") or p.get("id"))
    for sp, labels in sorted(spaces.items()):
        out.append(C.Claim(key, "api.panels", f"Editor '{sp}' has {len(labels)} panels, e.g. " + ", ".join(labels[:10]), "measured", 0.9, ev(f"panels:{sp}", f"{len(labels)} panels"),
                           {"space": sp, "panels": labels}, "atlas.introspect"))
    en = d.get("enums") or {}
    for name, kind, what in (("area_types", "api.area", "Editor types"), ("object_modes", "api.mode", "Modes"), ("object_types", "api.objects", "Object types"), ("modifier_types", "api.modifiers", "Modifier types"),
                             ("render_engines", "api.render", "Render engines")):
        vals = en.get(name) or []
        if vals:
            out.append(C.Claim(key, kind, f"{what}: " + ", ".join(v[1] or v[0] for v in vals), "measured", 0.95, ev(f"enum:{name}", f"{len(vals)} values"), {"values": vals}, "atlas.introspect"))
    if d.get("workspaces"):
        out.append(C.Claim(key, "ui.workspace", "Workspaces: " + ", ".join(d["workspaces"]), "measured", 0.95, ev("workspaces"), {"workspaces": d["workspaces"]}, "atlas.introspect"))
    for sname, s in sorted((d.get("rna") or {}).items()):
        out.append(C.Claim(key, "model.struct", f"Data type '{sname}' has {s['n']} properties, e.g. " + ", ".join(p[0] for p in s["props"][:12]), "measured", 0.92, ev(f"rna:{sname}", f"{s['n']} properties"),
                           {"struct": sname, "props": [p[0] for p in s["props"]]}, "atlas.introspect"))
    return out


def operators_of(key: str, store: C.AtlasStore) -> List[Dict[str, Any]]:
    """All introspected operators (id, name, desc, props) for a program, read from the cached dump named in its api.runtime claim."""
    for c in store.claims(key, "api.runtime"):
        f = (c.get("value") or {}).get("file")
        if f and os.path.isfile(f):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                return [o for ops in (d.get("operators") or {}).values() for o in ops]
            except Exception:
                continue
    return []


def call_template_of(key: str, store: C.AtlasStore) -> str:
    for c in store.claims(key, "api.runtime"):
        t = (c.get("value") or {}).get("call_template")
        if t:
            return t
    return ""


def learn(exe: str, key: str, store: C.AtlasStore, budget_s: float = 90.0) -> Dict[str, Any]:
    res = run(exe, key, budget_s=budget_s)
    rep: Dict[str, Any] = {k: res.get(k) for k in ("ok", "recipe", "why", "cached", "seconds")}
    if not res.get("ok"):
        return rep
    store.delete_claims(key, source="atlas.introspect")
    n = 0
    for c in to_claims(key, res):
        try:
            store.put_claim(c)
            n += 1
        except C.EvidenceRequired:
            continue
    d = res["data"]
    rep.update(claims=n, operators=d.get("ops_count"), menus=d.get("menus_count"), panels=d.get("panels_count"), errors=d.get("errors", [])[:3], file=res["file"])
    return rep
