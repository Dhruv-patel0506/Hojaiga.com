"""
object_knowledge -- what a builder knows about everyday objects, as data: part ROLES, proportions, and how each part is placed.

    category_of(task)                       -> category name | None      'a dining table with a thick top' -> 'table' (longest keyword wins: 'desk lamp' is a lamp, 'coffee table' is not a dining table)
    compile_design(task, shapes)            -> {design, category, dims, params, notes} | None
                                              dimensions from the store's ranges (size words and measures in the order move them inside the range), part count from the order
                                              ('five shelves', 'three legged stool'), every part from a formula of those dimensions: no model call, a few milliseconds
    role_critic(task, design)               -> [problems]                what is wrong with a design (compiled OR planned by a model) judged by the object's roles:
                                              overall size inside the real-world range, a shelf / seat / top is a slab, a leg / post is slender, a backrest sits at the rear edge, every required role exists

The store is data/object_knowledge.json: a new object is a new entry (dims [min, max, typical] in metres, params, parts with formulas), no code. Formulas are evaluated by a whitelist
interpreter (numbers, + - * / **, min / max / abs, the dimension names, SX / SY = corner signs, K / N = level index / count).
"""
from __future__ import annotations

import ast
import contextlib
import json
import math
import operator
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
STORE = os.path.join(DATA, "object_knowledge.json")
_CACHE: Dict[str, Any] = {}

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"min": min, "max": max, "abs": abs}


GENERATED = os.path.join(DATA, "object_knowledge_generated.json")      # categories WRITTEN BY THE SYSTEM (world_designer: Qwen's own recipes and the scene pieces compiled from its plans), merged under the hand-made ones


def store() -> Dict[str, Any]:
    try:
        mt = (os.path.getmtime(STORE), os.path.getmtime(GENERATED) if os.path.isfile(GENERATED) else 0.0)
        if _CACHE.get("mt") != mt:
            data = json.load(open(STORE, encoding="utf-8"))
            if os.path.isfile(GENERATED):
                with contextlib.suppress(Exception):
                    data = {**data, "categories": {**json.load(open(GENERATED, encoding="utf-8")).get("categories", {}), **data.get("categories", {})}}
            _CACHE["data"], _CACHE["mt"] = data, mt
        return _CACHE["data"]
    except Exception:
        return {"categories": {}}


def evaluate(expr: Any, env: Dict[str, float]) -> float:
    """A formula from the store, evaluated without eval(): arithmetic on numbers and the names in env only."""
    if isinstance(expr, (int, float)):
        return float(expr)

    def go(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return go(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Name) and n.id in env:
            return float(env[n.id])
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](go(n.left), go(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](go(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return float(_FUNCS[n.func.id](*[go(a) for a in n.args]))
        raise ValueError(f"not allowed in a formula: {ast.dump(n)[:60]}")
    return go(ast.parse(str(expr), mode="eval"))


# ------------------------------------------------------------------------------------------------------------------------------------------------ which object
def _stem(w: str) -> str:
    return w[:-3] + "f" if w.endswith("ves") else (w[:-1] if w.endswith("s") and not w.endswith("ss") and len(w) > 3 else w)


def category_of(task: str) -> Optional[str]:
    words = [_stem(w) for w in re.findall(r"[a-z]+", task.lower())]
    text = " " + " ".join(words) + " "
    best, blen = None, 0
    for name, c in store().get("categories", {}).items():
        for kw in c.get("keywords", []) + [name]:
            k = " ".join(_stem(w) for w in kw.lower().split())
            if f" {k} " in text and len(k) > blen:
                best, blen = name, len(k)
    return best


# ------------------------------------------------------------------------------------------------------------------------------------------------ the order's own words
SIZE_WORDS = {"tiny": 0.0, "mini": 0.05, "small": 0.12, "little": 0.12, "compact": 0.2, "short": 0.1, "low": 0.1, "narrow": 0.1, "big": 0.9, "large": 0.9, "huge": 1.0, "tall": 0.92, "high": 0.92, "wide": 0.92, "long": 0.92, "deep": 0.9}
AXIS_OF = {"tall": "H", "high": "H", "short": "H", "low": "H", "wide": "W", "narrow": "W", "long": "D", "deep": "D"}
UNIT = {"m": 1.0, "meter": 1.0, "metre": 1.0, "cm": 0.01, "centimeter": 0.01, "centimetre": 0.01, "mm": 0.001}
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _fraction(r: Sequence[float]) -> float:
    lo, hi, typ = r
    return 0.5 if hi <= lo else (typ - lo) / (hi - lo)


def _in_range(r: Sequence[float], f: float) -> float:
    return r[0] + max(0.0, min(1.0, f)) * (r[1] - r[0])


def counts_of(task: str) -> Dict[str, int]:
    """{'shelf': 5, 'leg': 3} from 'five shelves' / 'three legged' / '4 tiers'."""
    out: Dict[str, int] = {}
    for m in re.finditer(r"\b(\d+|" + "|".join(NUM_WORDS) + r")[\s-]+([a-z]+)", task.lower()):
        n = int(m.group(1)) if m.group(1).isdigit() else NUM_WORDS[m.group(1)]
        noun = "leg" if m.group(2).endswith("legged") else _stem(m.group(2))
        if 1 <= n <= 12:
            out[noun] = n
    return out


def resolve(task: str, cat: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, float], List[str]]:
    """(dims, params, notes): typical values, moved by the size words and measures in the order, always clamped to the range the real object has (a 'tall' chair is not a ladder)."""
    notes: List[str] = []
    t = task.lower()
    frac = {k: _fraction(v) for k, v in cat["dims"].items()}
    for w, f in SIZE_WORDS.items():
        if re.search(rf"\b{w}\b", t):
            axes = [AXIS_OF[w]] if w in AXIS_OF else list(cat["dims"])
            for a in axes:
                if a in frac:
                    frac[a] = f
                    notes.append(f"'{w}' -> {a} at {int(f * 100)}% of its range")
    dims = {k: _in_range(cat["dims"][k], frac[k]) for k in cat["dims"]}
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(m|meters?|metres?|cm|centimet(?:er|re)s?|mm)\b\s*(tall|high|wide|long|deep)?", t):         # '1.8 m tall'
        axis = AXIS_OF.get(m.group(3) or "")
        if axis in dims:
            u = m.group(2)
            v = float(m.group(1)) * (0.01 if u.startswith("c") else 0.001 if u == "mm" else 1.0)
            lo, hi, _t = cat["dims"][axis]
            dims[axis] = max(0.7 * lo, min(1.5 * hi, v))
            notes.append(f"{m.group(0).strip()} -> {axis} = {dims[axis]:.2f} m")
    params = {k: float(v[2]) for k, v in cat.get("params", {}).items()}
    cnt = counts_of(task)
    if "N" in params:
        for noun in ("shelf", "tier", "level", "board", "shelve", "step"):
            if noun in cnt:
                lo, hi, _t = cat["params"]["N"]
                params["N"] = float(max(lo, min(hi, cnt[noun])))
                notes.append(f"{int(params['N'])} levels from the order")
                break
    if "seat_h" in params:
        params["seat_h"] = min(params["seat_h"], dims.get("H", 1.0) * 0.55)
    return dims, params, notes


def _signs(kind: str, n_legs: int) -> List[Tuple[float, float, int]]:
    if kind == "sides":
        return [(-1.0, 1.0, 0), (1.0, 1.0, 1)]
    if kind == "corners_front":
        return [(-1.0, 1.0, 0), (1.0, 1.0, 1)]
    if kind == "corners":
        if n_legs == 3:
            return [(0.0, 1.0, 0), (-0.87, -0.5, 1), (0.87, -0.5, 2)]
        base = [(-1.0, -1.0, 0), (1.0, -1.0, 1), (-1.0, 1.0, 2), (1.0, 1.0, 3)]
        if n_legs >= 5:
            base += [(0.0, -1.0, 4), (0.0, 1.0, 5)]
        return base[:max(n_legs, 3)] if n_legs >= 3 else base
    return [(1.0, 1.0, 0)]


def compile_design(task: str, shapes: Sequence[str]) -> Optional[Dict[str, Any]]:
    cname = category_of(task)
    if not cname:
        return None
    cat = store()["categories"][cname]
    dims, params, notes = resolve(task, cat)
    wood = store().get("wood", [0.55, 0.38, 0.22])
    n_legs = counts_of(task).get("leg", 4)
    env0 = {**dims, **params}
    parts: List[Dict[str, Any]] = []
    for spec in cat["parts"]:
        kind = spec.get("repeat")
        runs: List[Dict[str, float]]
        if kind in ("corners", "corners_front", "sides"):
            runs = [{"SX": sx, "SY": sy, "i": i + 1} for sx, sy, i in _signs(kind, n_legs)]
        elif kind == "levels":
            n = int(env0.get("N", 3))
            boards = int(evaluate(spec.get("count", "N"), env0))                              # e.g. 'N + 1': N compartments need N + 1 boards
            runs = [{"K": k, "N": n, "i": k + 1} for k in range(boards)]
        else:
            runs = [{"i": 1}]
        for r in runs:
            env = {**env0, **r}
            try:
                size = [max(0.005, evaluate(x, env)) for x in spec["size"]]
                at = [evaluate(x, env) for x in spec["at"]]
            except Exception as e:
                notes.append(f"{spec.get('name')}: {e}")
                continue
            shape = spec.get("shape", "cube")
            if shape not in shapes:                                                           # the app's own name for it first ('sphere' is Blender's 'uv_sphere': live Oct-27 heads came out as cubes)
                shape = next((s for s in sorted(shapes) if shape in s.split("_")), "cube" if "cube" in shapes else (shapes[0] if shapes else shape))
            parts.append({"name": spec["name"].replace("{i}", str(int(r.get("i", 1)))), "shape": shape, "size": [round(x, 4) for x in size], "at": [round(x, 4) for x in at],
                          "rotate": [0.0, 0.0, 0.0], "color": list(spec.get("color", wood))})
    design = {"object": cname, "parts": parts}
    return {"design": design, "category": cname, "dims": {k: round(v, 3) for k, v in dims.items()}, "params": {k: round(v, 3) for k, v in params.items()}, "notes": notes, "scene": bool(cat.get("scene"))}


# ------------------------------------------------------------------------------------------------------------------------------------------------ the critic
def form_of(size: Sequence[float]) -> str:
    s = sorted(size)
    if s[0] < 0.2 * s[1] and s[0] < 0.2 * s[2]:
        return "slab"
    if s[2] > 3.0 * s[1]:
        return "post"
    return "block"


def _role(name: str) -> str:
    return _stem(re.sub(r"[\d_\- ]+$", "", name.lower()))


def role_critic(task: str, design: Dict[str, Any]) -> List[str]:
    """Judge a design by the object's ROLES (compiled or model-planned): overall size inside the real range, each part's form matches its role, a part that sits at the back in the real object sits at the back here."""
    cname = category_of(task)
    parts = design.get("parts", [])
    if not cname or not parts:
        return []
    cat = store()["categories"][cname]
    out: List[str] = []
    lo = [min(p["at"][i] - p["size"][i] / 2 for p in parts) for i in range(3)]
    hi = [max(p["at"][i] + p["size"][i] / 2 for p in parts) for i in range(3)]
    ext = {"W": hi[0] - lo[0], "D": hi[1] - lo[1], "H": hi[2] - max(lo[2], 0.0)}
    for a, v in ext.items():
        r = cat["dims"].get(a)
        if r and not (0.55 * r[0] <= v <= 1.6 * r[1]) and not re.search(r"\b(giant|miniature|toy|huge|tiny|mini|doll)\b", task.lower()):
            out.append(f"the {cname} is {v:.2f} m in {'width' if a == 'W' else 'depth' if a == 'D' else 'height'}; a real {cname} is {r[0]:.2f}-{r[1]:.2f} m")
    dims, params, _n = resolve(task, cat)
    ref = compile_design(task, ["cube", "cylinder", "cone", "sphere"])
    by_role: Dict[str, List[Dict[str, Any]]] = {}
    for p in parts:
        by_role.setdefault(_role(p["name"]), []).append(p)
    ref_parts = (ref or {}).get("design", {}).get("parts", [])
    seen = set()
    for rp in ref_parts:
        role = _role(rp["name"])
        if role in seen:
            continue
        seen.add(role)
        group = [q for q in ref_parts if _role(q["name"]) == role]
        have = by_role.get(role, [])
        if not have:
            if role in ("seat", "top", "leg", "side", "shelf", "backrest_slat_top", "rearpost", "headboard", "mattress", "base", "pole", "shade"):
                out.append(f"a {cname} needs its {role.replace('_', ' ')} but the design has no part named like that")
            continue
        want = form_of(rp["size"])
        for p in have:
            got = form_of(p["size"])
            if want in ("slab", "post") and got != want and not (want == "post" and got == "block" and max(p["size"]) > 2.2 * max(p["size"][0], p["size"][1])):
                out.append(f"'{p['name']}' is a {got} ({'x'.join('%.2f' % s for s in p['size'])} m) but a {cname}'s {role.replace('_', ' ')} is a {want}")
        ys = [q["at"][1] for q in group]
        if all(y * ys[0] > 0 for y in ys) and abs(ys[0]) > 0.3 * dims.get("D", 1.0):         # a role that sits wholly at the rear (or front) edge in the real object
            cy = (lo[1] + hi[1]) / 2
            if any((p["at"][1] - cy) * ys[0] < 0 for p in have):
                out.append(f"the {role.replace('_', ' ')} of a {cname} is at the {'rear' if ys[0] < 0 else 'front'} edge, not the opposite side")
    return list(dict.fromkeys(out))[:8]


def known_categories() -> List[str]:
    return sorted(store().get("categories", {}))
