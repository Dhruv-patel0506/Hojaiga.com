"""
brain_planner -- the system-RAM planner / tutor: ZERO VRAM.

The vision model (Qwen3-VL-2B + adapter) lives on the GPU and only LOOKS and POINTS. Everything that needs language - what the person wants, how to split a job into parts, how to say a pathway - runs here, in
system RAM, on the CPU:

    Brain             a text model served by the local Ollama with `num_gpu=0` (every layer on the CPU, nothing on the 6 GB card). llama.cpp is what Ollama runs; no new software is installed.
    classify_intent   understand / teach / delegate, read from the words of the request (a model is asked only when the words do not decide).
    detect_app        which installed program the request is about: the longest catalogue name found in the text.
    design_parts      a job like "a table with four legs" becomes a list of PARTS (a shape the application itself offers, a size, a place, a colour), checked against the application's own command registry.
    pathways          what the RAG knows about a goal, as Menu -> Tab -> Flyout -> Button + Shortcut text.

Nothing here knows an application. The shapes come from the registry of the program that is running; the pathways come from the retrieval.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

OLLAMA = os.environ.get("HOJAIGA_OLLAMA", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("HOJAIGA_BRAIN_MODEL", "qwen2.5:7b")


class Brain:
    """A text model on the CPU. `generate` is one request; nothing is kept between requests."""

    def __init__(self, model: str = "", cpu_only: bool = True, num_ctx: int = 4096, threads: int = 0):
        self.model = model or DEFAULT_MODEL
        self.cpu_only = cpu_only
        self.num_ctx = num_ctx
        self.threads = threads or max(2, (os.cpu_count() or 8) // 2)
        self.calls: List[Dict[str, Any]] = []

    def alive(self) -> bool:
        import requests
        try:
            names = [m["name"] for m in requests.get(OLLAMA + "/api/tags", timeout=5).json().get("models", [])]
            return self.model in names or any(n.split(":")[0] == self.model.split(":")[0] and (":" not in self.model) for n in names)
        except Exception:
            return False

    def generate(self, prompt: str, system: str = "", json_mode: bool = False, max_tokens: int = 700, temperature: float = 0.2, timeout: float = 1200.0) -> Dict[str, Any]:
        import requests
        opts: Dict[str, Any] = {"temperature": temperature, "num_predict": max_tokens, "num_ctx": self.num_ctx, "num_thread": self.threads}
        if self.cpu_only:
            opts["num_gpu"] = 0                                   # no layer on the card: the vision model owns the VRAM
        body: Dict[str, Any] = {"model": self.model, "prompt": prompt, "system": system, "stream": False, "options": opts, "keep_alive": "10m"}
        if json_mode:
            body["format"] = "json"
        t0 = time.time()
        try:
            r = requests.post(OLLAMA + "/api/generate", json=body, timeout=timeout).json()
            out = {"ok": "response" in r, "text": r.get("response", ""), "seconds": round(time.time() - t0, 1), "prompt_tokens": r.get("prompt_eval_count"), "tokens": r.get("eval_count"), "error": r.get("error", "")}
        except Exception as exc:
            out = {"ok": False, "text": "", "seconds": round(time.time() - t0, 1), "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        self.calls.append({k: out.get(k) for k in ("ok", "seconds", "prompt_tokens", "tokens", "error")})
        return out

    def json(self, prompt: str, system: str = "", **kw: Any) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        r = self.generate(prompt, system, json_mode=True, **kw)
        try:
            return json.loads(r["text"]), r
        except Exception:
            m = re.search(r"\{.*\}", r.get("text", ""), re.S)
            try:
                return (json.loads(m.group(0)) if m else None), r
            except Exception:
                return None, r


# ------------------------------------------------------------------------------------------------------------------------------------------------ intent
TEACH_RX = re.compile(r"\b(how (?:do|can|could|would|should|to|does)|teach|show me how|explain|walk me through|where (?:is|are|do|can)|what does|what is the|which (?:menu|tab|button|key)|shortcut|hotkey|guide me|"
                      r"help me (?:find|use|learn)|tutorial|steps? (?:to|for)|how-to)\b", re.I)
UNDERSTAND_RX = re.compile(r"\b(learn|understand|onboard|study|scan|map out|get to know|explore|familiari[sz]e|catalogue|index)\b", re.I)
DELEGATE_RX = re.compile(r"(?:^|\b(?:please|then|and|can you|could you|just)\s+)(make|create|build|draw|paint|write|type|add|insert|design|model|generate|produce|save|export|render|fill|set up|automate|do|open|compose|"
                         r"prepare|put|place|colou?r|trace|sketch)\b|\bfor me\b|\bdo it\b", re.I)


def classify_intent(task: str, brain: Optional[Brain] = None) -> Dict[str, Any]:
    """understand | teach | delegate, from the words; a model decides only when the words give no majority. `also` lists the other modes the text asks for (teach AND do)."""
    t = task.strip()
    scores = {"teach": len(TEACH_RX.findall(t)) + (1 if t.endswith("?") else 0), "understand": len(UNDERSTAND_RX.findall(t)), "delegate": len(DELEGATE_RX.findall(t))}
    if re.match(r"\s*(?:how|where|what|which|why|can i|is there)\b", t, re.I):
        scores["teach"] += 2
    if re.match(r"\s*(?:please\s+)?(?:make|create|build|draw|paint|write|type|add|design|model|generate|open|set|put)\b", t, re.I):
        scores["delegate"] += 2
    if not TEACH_RX.search(t) and not t.endswith("?") and re.search(r"\b(type|write|add|insert|create|make|build|draw|paint|trace|put|set|change|fill|save|export|open|delete|rename|copy|paste|format|colou?r|select|click|press)\b", t, re.I):
        scores["delegate"] += 1                                                       # an order with its verb after the program's name ('in Word type a heading ...')
    best = sorted(scores.items(), key=lambda kv: -kv[1])
    if best[0][1] > 0 and best[0][1] > best[1][1]:
        mode, how = best[0][0], "words"
    elif brain is not None and brain.alive():
        obj, _ = brain.json(f'Request: "{t}"\nDecide what the person wants from an assistant that works inside a computer program: '
                            '"teach" (explain how to do it, point at the controls), "delegate" (do the job for them) or "understand" (learn the program first). '
                            'Answer JSON {"mode": "teach|delegate|understand"}.', max_tokens=30)
        mode, how = (obj or {}).get("mode", "teach"), "model"
        if mode not in scores:
            mode = "teach"
    else:
        mode, how = "teach", "default"
    return {"mode": mode, "how": how, "scores": scores, "also": [k for k, v in scores.items() if v > 0 and k != mode]}


def detect_app(task: str, names: Sequence[str]) -> str:
    """The longest known program name that appears in the request (whole words, case-insensitive); '' when none does."""
    low = " " + re.sub(r"[^a-z0-9+#. ]+", " ", task.lower()).replace(".", " ") + " "
    hits = []
    for n in names:
        for k in {re.sub(r"[^a-z0-9+# ]+", " ", n.lower()).strip(), re.sub(r"[^a-z0-9+# ]+", " ", strip_version(n).lower()).strip()}:
            if len(k) >= 3 and (" " + k + " ") in low:
                hits.append((len(k), n))
    return max(hits)[1] if hits else ""


def strip_version(name: str) -> str:
    """'Blender 5.2' -> 'Blender', 'Photometric Calc 2025 R2' -> 'Photometric Calc': a name without its release suffix (a program keeps its knowledge across versions)."""
    prev = None
    while prev != name:
        prev = name
        name = re.sub(r"\s+(?:v?\d[\d.]*|r\d+|\(.*?\)|x64|x86|64-bit|32-bit)\s*$", "", name, flags=re.I)
    return name.strip() or prev


# ------------------------------------------------------------------------------------------------------------------------------------------------ 3D design
EXAMPLE = {"object": "mushroom", "parts": [
    {"name": "stem", "shape": "cylinder", "size": [0.08, 0.08, 0.18], "on": "ground", "xy": [0, 0], "rotate": [0, 0, 0], "color": [0.93, 0.9, 0.82]},
    {"name": "cap", "shape": "uv_sphere", "size": [0.28, 0.28, 0.14], "on": ["stem"], "xy": [0, 0], "rotate": [0, 0, 0], "color": [0.75, 0.12, 0.1]}]}

DESIGN_SYSTEM = ("You are a careful 3D modeller. You build objects out of simple parts, in metres, z up, the ground at z=0. You answer with JSON only.")


def shapes_of(registry: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """The shapes the running application can add as one command: {short name: command id}, read from its own registry ('mesh.primitive_cube_add' -> 'cube')."""
    out: Dict[str, str] = {}
    for it in registry:
        m = re.fullmatch(r"mesh\.primitive_(\w+?)_add", it.get("id", ""))
        if m and not m.group(1).startswith(("bz_", "nurbs", "grease")) and m.group(1) not in FLAT:
            out[m.group(1)] = it["id"]
    return out


FLAT = {"plane", "grid", "circle"}                                      # shapes with no thickness: a part that has height is never made from one


def infer_on(design: Dict[str, Any]) -> Dict[str, Any]:
    """For a design in centre points: which parts each part rests on (the parts whose top meets its bottom, with footprints that overlap), or 'ground'."""
    out: Dict[str, Any] = {}
    parts = design.get("parts", [])
    for p in parts:
        bottom = p["at"][2] - p["size"][2] / 2.0
        under = []
        for q in parts:
            if q is p:
                continue
            top = q["at"][2] + q["size"][2] / 2.0
            ox = abs(p["at"][0] - q["at"][0]) < (p["size"][0] + q["size"][0]) / 2.0
            oy = abs(p["at"][1] - q["at"][1]) < (p["size"][1] + q["size"][1]) / 2.0
            if abs(top - bottom) <= 0.02 and ox and oy:
                under.append(q["name"])
        out[p["name"]] = under or "ground"
    return out


def to_prompt_format(design: Dict[str, Any]) -> Dict[str, Any]:
    """A stored design (centre points) in the form the prompt asks for (what each part rests on + its place seen from above)."""
    on = infer_on(design)
    return {"object": design.get("object", ""), "parts": [{"name": p["name"], "shape": p["shape"], "size": p["size"], "on": on[p["name"]], "xy": [p["at"][0], p["at"][1]],
                                                          "rotate": p.get("rotate", [0, 0, 0]), "color": p.get("color", [0.7, 0.7, 0.7])} for p in design.get("parts", [])]}


def design_prompt(task: str, shapes: Sequence[str], examples: Sequence[Dict[str, Any]], problems: Sequence[str] = ()) -> str:
    ex = [to_prompt_format(e) for e in list(examples)[:2]] or [EXAMPLE]
    lines = [f'Job: "{task}"', "", "Build it from simple parts. Every part is ONE of these shapes: " + ", ".join(shapes) + ".",
             "Rules:",
             "- axes: x = left-right, y = front-back, z = UP (height). A cylinder or cone stands along z: a tall post is size [diameter, diameter, height]; to lay one on its side, rotate it 90 degrees.",
             "- size = the part's full width (x), depth (y) and height (z) in metres, measured on its bounding box before it is rotated. Use a cube for any flat board or slab (e.g. size [1.2, 0.7, 0.04]), never a plane.",
             "- on = what the part RESTS ON: \"ground\" or a list with the names of the parts under it. The system puts the part on top of those (its height is worked out for you), so name the SUPPORTS correctly: legs, posts and bases stand on the ground; what they carry rests on them.",
             "- xy = [x, y] where the middle of the part is, seen from above. A part resting on others must be above them (its xy inside their footprint). Put mirrored parts at mirrored coordinates; use real-world sizes.",
             "- rotate = degrees about x, y, z (usually 0). color = [r, g, b] each 0..1, chosen to suit the material the thing is made of.",
             "- 3 to 20 parts. Name every part. Output only the JSON object.", "", "Example of the format (a different object):", json.dumps(ex[0])]
    if len(ex) > 1:
        lines += ["Another, from earlier work:", json.dumps(ex[1])]
    if problems:
        lines += ["", "Your previous answer had these problems, fix them:"] + ["- " + p for p in problems]
    return "\n".join(lines)


def _vec(v: Any, n: int = 3) -> Optional[List[float]]:
    try:
        out = [float(x) for x in v]
        return out if len(out) == n else None
    except Exception:
        return None


def validate_design(d: Any, shapes: Sequence[str]) -> Tuple[Dict[str, Any], List[str]]:
    """(the cleaned design, the problems). A part with an unknown shape or a malformed number is a problem, not silently fixed."""
    problems: List[str] = []
    parts: List[Dict[str, Any]] = []
    if not isinstance(d, dict) or not isinstance(d.get("parts"), list):
        return {"object": "", "parts": []}, ["the answer is not an object with a 'parts' list"]
    for i, p in enumerate(d["parts"][:30]):
        if not isinstance(p, dict):
            problems.append(f"part {i + 1} is not an object")
            continue
        nm = str(p.get("name") or f"part{i + 1}")[:40]
        shape = str(p.get("shape", "")).lower().strip().replace(" ", "_")
        if shape not in shapes:
            near = [s for s in shapes if s in shape or shape in s]
            if len(near) == 1:
                shape = near[0]
            else:
                problems.append(f"part '{nm}': shape '{p.get('shape')}' is not one of {', '.join(shapes)}")
                continue
        size, at = _vec(p.get("size")), _vec(p.get("at"))
        base = _vec(p.get("base"))
        xy = _vec(p.get("xy"), 2)
        if size and base:
            at = [base[0], base[1], base[2] + size[2] / 2.0]                    # bottom-centre -> centre (before any turn)
        if size and xy and "on" in p:
            at = [xy[0], xy[1], size[2] / 2.0]                                  # the height is worked out below from what the part rests on
        if not size or not at:
            problems.append(f"part '{nm}': size and base must each be 3 numbers")
            continue
        if min(size) <= 0:
            problems.append(f"part '{nm}': every size must be above 0")
            continue
        rot = _vec(p.get("rotate")) or [0.0, 0.0, 0.0]
        col = _vec(p.get("color")) or [0.7, 0.7, 0.7]
        on = p.get("on")
        on = [] if on in (None, "ground", "floor", "") else ([on] if isinstance(on, str) else [str(x) for x in on if str(x).lower() not in ("ground", "floor")])
        parts.append({"name": nm, "shape": shape, "size": [min(max(x, 0.005), 50.0) for x in size], "at": at, "rotate": rot, "color": [min(max(c, 0.0), 1.0) for c in col],
                      **({"on": on} if "on" in p else {})})
    if not parts:
        problems.append("no usable part")
    resolve_on(parts)
    problems += stack(parts)
    return {"object": str(d.get("object") or "object")[:60], "parts": parts}, problems


def resolve_on(parts: List[Dict[str, Any]]) -> None:
    """A part says it rests on 'legs' and the plan has leg1 ... leg4: the group name is read as those parts (names equal after dropping digits / a plural 's'). A name that matches nothing is left for stack() to report."""
    import re as _re

    def stem(n: str) -> str:
        n = _re.sub(r"[\d_\- ]+$", "", n.lower())
        return n[:-1] if n.endswith("s") and len(n) > 3 else n
    names = [p["name"] for p in parts]
    for p in parts:
        if not p.get("on"):
            continue
        out: List[str] = []
        for nm in p["on"]:
            if nm in names:
                out.append(nm)
                continue
            grp = [n for n in names if n != p["name"] and (stem(n) == stem(nm) or stem(n).startswith(stem(nm)) or stem(nm).startswith(stem(n)) and len(stem(n)) >= 3)]
            out += grp if grp else [nm]
        p["on"] = list(dict.fromkeys(out))


def stack(parts: List[Dict[str, Any]]) -> List[str]:
    """Work out the height of every part that says what it rests on: the top of whatever is under it (the highest, when it rests on several). Problems: an unknown support, a loop, a part that is not above its supports."""
    byname = {p["name"]: p for p in parts}
    problems: List[str] = []
    done: Dict[str, float] = {}
    busy: set = set()

    def base_z(p: Dict[str, Any]) -> float:
        if p["name"] in done:
            return done[p["name"]]
        if "on" not in p or not p["on"]:
            z = p["at"][2] - p["size"][2] / 2.0 if "on" not in p else 0.0
        elif p["name"] in busy:
            problems.append(f"'{p['name']}' rests on itself through a loop of supports")
            return 0.0
        else:
            busy.add(p["name"])
            tops = []
            for nm in p["on"]:
                q = byname.get(nm)
                if q is None:
                    problems.append(f"'{p['name']}' rests on '{nm}', which is not one of your parts")
                    continue
                tops.append(base_z(q) + q["size"][2])
                if abs(p["at"][0] - q["at"][0]) > (p["size"][0] + q["size"][0]) / 2.0 or abs(p["at"][1] - q["at"][1]) > (p["size"][1] + q["size"][1]) / 2.0:
                    problems.append(f"'{p['name']}' rests on '{nm}' but is not above it: their footprints (seen from above) do not overlap, change xy")
            busy.discard(p["name"])
            z = max(tops) if tops else 0.0
        done[p["name"]] = z
        return z
    for p in parts:
        z = base_z(p)
        if "on" in p:
            p["at"] = [p["at"][0], p["at"][1], z + p["size"][2] / 2.0]
    return problems


def part_box(p: Dict[str, Any]) -> Tuple[List[float], List[float]]:
    """The axis-aligned box a part fills in the world: its size box turned by its rotation (degrees about x, y, z) around its centre."""
    import math
    hx, hy, hz = (s / 2.0 for s in p["size"])
    rx, ry, rz = (math.radians(a) for a in p.get("rotate", [0, 0, 0]))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    lo, hi = [1e9] * 3, [-1e9] * 3
    for ax in (-hx, hx):
        for ay in (-hy, hy):
            for az in (-hz, hz):
                y1, z1 = ay * cx - az * sx, ay * sx + az * cx                      # x, then y, then z (Blender's XYZ Euler order)
                x2, z2 = ax * cy + z1 * sy, -ax * sy + z1 * cy
                x3, y3 = x2 * cz - y1 * sz, x2 * sz + y1 * cz
                for i, v in enumerate((x3 + p["at"][0], y3 + p["at"][1], z2 + p["at"][2])):
                    lo[i], hi[i] = min(lo[i], v), max(hi[i], v)
    return lo, hi


def boxes_touch(a: Tuple[List[float], List[float]], b: Tuple[List[float], List[float]], gap: float = 0.01) -> bool:
    return all(a[0][i] <= b[1][i] + gap and b[0][i] <= a[1][i] + gap for i in range(3))


def components(boxes: Sequence[Tuple[List[float], List[float]]], gap: float = 0.01) -> List[List[int]]:
    """Groups of parts that touch (directly or through other parts)."""
    seen: set = set()
    out: List[List[int]] = []
    for i in range(len(boxes)):
        if i in seen:
            continue
        comp, todo = [], [i]
        while todo:
            j = todo.pop()
            if j in seen:
                continue
            seen.add(j)
            comp.append(j)
            todo += [k for k in range(len(boxes)) if k not in seen and boxes_touch(boxes[j], boxes[k], gap)]
        out.append(sorted(comp))
    return out


def piercing(boxes: Sequence[Tuple[List[float], List[float]]], names: Sequence[str], tol: float = 0.03) -> List[str]:
    """Parts that stick THROUGH another: one part's footprint centre lies inside the other's footprint, they overlap in height, and the first reaches more than `tol` above the other's top surface
    while starting below it (a table leg that is taller than the table and pokes up through its top). Returns 'A through B' strings."""
    out: List[str] = []
    for i in range(len(boxes)):
        for j in range(len(boxes)):
            if i == j:
                continue
            a, b = boxes[i], boxes[j]
            cx, cy = (a[0][0] + a[1][0]) / 2.0, (a[0][1] + a[1][1]) / 2.0
            aw, ad = a[1][0] - a[0][0], a[1][1] - a[0][1]
            m = max(aw, ad) if max(aw, ad) >= 3 * max(min(aw, ad), 1e-6) else 0.0     # a thin PANEL at the edge of a board (a shelf unit's side) is beside it, not through it; a square post (a leg) is through it wherever it is
            inside = b[0][0] + m <= cx <= b[1][0] - m and b[0][1] + m <= cy <= b[1][1] - m
            if inside and a[1][2] > b[1][2] + tol and a[0][2] < b[1][2] - tol and a[1][2] > b[0][2] + tol and (b[1][2] - b[0][2]) < (a[1][2] - a[0][2]) and (a[1][0] - a[0][0]) * (a[1][1] - a[0][1]) < 0.5 * (b[1][0] - b[0][0]) * (b[1][1] - b[0][1]):
                out.append(f"{names[i]} through {names[j]}")
    by_post: Dict[str, List[str]] = {}
    for x in out:
        a_, b_ = x.split(" through ")
        by_post.setdefault(a_, []).append(b_)
    keep: List[str] = []
    for a_, bs in by_post.items():
        zs = sorted(boxes[list(names).index(b_)][1][2] for b_ in bs)
        levels = 1 + sum(1 for u, v in zip(zs, zs[1:]) if v - u >= 0.15)
        if levels < 2:                                                          # a post through ONE board is a leg too tall; through several levels it is the frame of a shelf unit
            keep += [f"{a_} through {b_}" for b_ in bs]
    return keep


def settle(design: Dict[str, Any], tol: float = 0.03) -> List[str]:
    """Plain-geometry repairs, applied to a plan BEFORE the critic reads it (a model's numbers are often a few centimetres or half a metre off; the fix is arithmetic, not another model call). Unrotated parts only.
      - a part that pokes up THROUGH another is shortened so its top ends at the other's underside (a table leg taller than the table);
      - a thin post that stops short of the part above it (footprints overlap) is lengthened up to that part's underside;
      - any other detached part whose footprint overlaps the main body is moved up / down until the boxes touch (never below the ground).
    Returns what was changed (empty when the plan needed nothing)."""
    parts = design.get("parts", [])
    notes: List[str] = []
    if not parts or any(any(abs(a) > 1e-6 for a in p.get("rotate", [0, 0, 0])) for p in parts):
        return notes

    def foot(p: Dict[str, Any]) -> Tuple[float, float, float, float]:
        return p["at"][0] - p["size"][0] / 2, p["at"][1] - p["size"][1] / 2, p["at"][0] + p["size"][0] / 2, p["at"][1] + p["size"][1] / 2

    def zr(p: Dict[str, Any]) -> Tuple[float, float]:
        return p["at"][2] - p["size"][2] / 2, p["at"][2] + p["size"][2] / 2

    def overlap_xy(a: Dict[str, Any], b: Dict[str, Any]) -> float:
        fa, fb = foot(a), foot(b)
        w, h = min(fa[2], fb[2]) - max(fa[0], fb[0]), min(fa[3], fb[3]) - max(fa[1], fb[1])
        return max(0.0, w) * max(0.0, h) / max((fa[2] - fa[0]) * (fa[3] - fa[1]), 1e-9)
    for _round in range(3):
        changed = False
        for b in parts:                                                             # 0. a flat board lying on the ground with posts standing in its footprint: it belongs ON the posts
            if b["size"][2] >= 0.12 * max(b["size"][0], b["size"][1]) or zr(b)[0] > 0.02:
                continue
            posts = [a for a in parts if a is not b and a["size"][2] > 3 * max(a["size"][0], a["size"][1]) and overlap_xy(a, b) >= 0.9 and zr(a)[1] > zr(b)[1] + 0.2 and zr(a)[0] <= zr(b)[0] + 0.02]
            if len(posts) >= 2:
                top = min(zr(a)[1] for a in posts)
                notes.append(f"'{b['name']}' lifted from the ground onto the top of its posts ({top:.2f} m)")
                b["at"][2] = top + b["size"][2] / 2
                changed = True
        def interior(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
            fb = foot(b)
            w, d = a["size"][0], a["size"][1]
            m = max(w, d) if max(w, d) >= 3 * max(min(w, d), 1e-6) else 0.0
            return fb[0] + m <= a["at"][0] <= fb[2] - m and fb[1] + m <= a["at"][1] <= fb[3] - m
        for a in parts:                                                             # 1b. embedded: a part whose bottom is sunk INTO a board it stands on (its top above the board's top): it rests ON the board
            for b in parts:
                if a is b or overlap_xy(a, b) < 0.9 or not interior(a, b) or (foot(a)[2] - foot(a)[0]) * (foot(a)[3] - foot(a)[1]) >= 0.5 * (foot(b)[2] - foot(b)[0]) * (foot(b)[3] - foot(b)[1]):
                    continue
                (alo, ahi), (blo, bhi) = zr(a), zr(b)
                if b["size"][2] < 0.2 * max(b["size"][0], b["size"][1]) and ahi > bhi + tol and blo + tol < alo < bhi - tol:
                    notes.append(f"'{a['name']}' was sunk {bhi - alo:.2f} m into '{b['name']}': it now stands on its top")
                    h = ahi - bhi
                    a["size"][2], a["at"][2] = h, bhi + h / 2
                    changed = True
        for a in parts:                                                             # 1. through
            for b in parts:
                if a is b or overlap_xy(a, b) < 0.9 or not interior(a, b) or (foot(a)[2] - foot(a)[0]) * (foot(a)[3] - foot(a)[1]) >= 0.5 * (foot(b)[2] - foot(b)[0]) * (foot(b)[3] - foot(b)[1]):
                    continue
                (alo, ahi), (blo, bhi) = zr(a), zr(b)
                crossing = sorted(zr(q)[1] for q in parts if q is not a and q is not b and overlap_xy(a, q) >= 0.9 and interior(a, q) and zr(q)[0] > alo and zr(q)[1] < ahi - tol and q["size"][2] < 0.2 * max(q["size"][0], q["size"][1]))
                if crossing and any(abs(c - bhi) >= 0.15 for c in crossing):          # the post carries boards at several heights: a frame, not a leg too tall for its top
                    continue
                if ahi > bhi + tol and alo < bhi - tol and (bhi - blo) < (ahi - alo) and alo < blo + 1e-6:
                    h = blo - alo
                    if h > 0.02:
                        notes.append(f"'{a['name']}' shortened from {a['size'][2]:.2f} to {h:.2f} m so it ends under '{b['name']}'")
                        a["size"][2], a["at"][2] = h, alo + h / 2
                        changed = True
        for a in parts:                                                             # 2. a thin post that stops short: it reaches down to what it stands on (or the ground) and up to what it holds
            w = max(a["size"][0], a["size"][1])
            if a["size"][2] < 2.0 * w:
                continue
            alo, ahi = zr(a)
            below = [b for b in parts if b is not a and zr(b)[1] < alo - 0.005 and overlap_xy(a, b) >= 0.5]
            new_lo = alo
            if not any(zr(b)[1] >= alo - tol and zr(b)[0] < alo and overlap_xy(a, b) >= 0.5 for b in parts if b is not a) and alo > 0.02:
                new_lo = max((zr(b)[1] for b in below), default=0.0)                  # onto the top of the part below, else onto the ground
            above = [b for b in parts if b is not a and zr(b)[0] > ahi + 0.005 and overlap_xy(a, b) >= 0.5 and zr(b)[0] - ahi < 3.0]
            new_hi = ahi
            if above and not any(zr(b)[0] <= ahi + tol and zr(b)[1] >= ahi - tol and overlap_xy(a, b) >= 0.5 for b in parts if b is not a):
                new_hi = zr(min(above, key=lambda q: zr(q)[0]))[0]
            if new_lo < alo - 0.005 or new_hi > ahi + 0.005:
                notes.append(f"'{a['name']}' stretched from {alo:.2f}-{ahi:.2f} m to {new_lo:.2f}-{new_hi:.2f} m so it stands on its support and meets what it holds")
                a["size"][2], a["at"][2] = new_hi - new_lo, (new_hi + new_lo) / 2
                changed = True
        boxes = [part_box(p) for p in parts]
        comps = components(boxes, 0.01)
        if len(comps) > 1:                                                          # 3. a detached group: slide it vertically onto the main body
            main = max(comps, key=lambda c: (len(c), sum((boxes[i][1][0] - boxes[i][0][0]) * (boxes[i][1][1] - boxes[i][0][1]) * (boxes[i][1][2] - boxes[i][0][2]) for i in c)))
            for c in comps:
                if c is main:
                    continue
                mp = [parts[i] for i in main]
                if min(boxes[i][0][2] for i in c) <= 0.02 and min(boxes[i][0][2] for i in main) > 0.02:
                    continue                                                        # a group standing on the ground is never lifted onto something floating
                for i in c:
                    q = parts[i]
                    tgt = [m for m in mp if overlap_xy(q, m) >= 0.3]
                    if not tgt:
                        continue
                    m = min(tgt, key=lambda t: min(abs(zr(q)[0] - zr(t)[1]), abs(zr(q)[1] - zr(t)[0])))
                    (qlo, qhi), (mlo, mhi) = zr(q), zr(m)
                    dz = (mhi - qlo) if qlo > mhi else ((mlo - qhi) if qhi < mlo else 0.0)
                    if abs(dz) > 0.005 and qlo + dz >= -0.005:
                        for k in c:
                            parts[k]["at"][2] += dz
                        notes.append(f"'{', '.join(parts[k]['name'] for k in c)}' moved {dz:+.2f} m to touch '{m['name']}'")
                        changed = True
                        break
        if not changed:
            break
    return notes


def critic(design: Dict[str, Any]) -> List[str]:
    """Geometry that cannot be right for a physical object, whatever it is: parts below the ground, pieces that touch nothing, nothing on the ground, absurd scale."""
    parts = design.get("parts", [])
    if not parts:
        return []
    boxes = [part_box(p) for p in parts]
    out: List[str] = []
    for p, b in zip(parts, boxes):
        if b[0][2] < -0.01:
            out.append(f"part '{p['name']}' goes {-b[0][2]:.2f} m below the ground (z=0): raise its at.z")
    comps = components(boxes)
    if len(comps) > 1:
        main = max(comps, key=len)
        for c in comps:
            if c is not main:
                names = ", ".join(parts[i]["name"] for i in c)
                nb = [boxes[i] for i in main]
                near = min(range(len(main)), key=lambda k: sum(abs(((boxes[c[0]][0][a] + boxes[c[0]][1][a]) - (nb[k][0][a] + nb[k][1][a])) / 2.0) for a in range(3)))
                out.append(f"'{names}' touches no other part (floating): move it so its box meets the box of '{parts[main[near]]['name']}' (their boxes must overlap or be within 0.01 m)")
    for pair in piercing(boxes, [p["name"] for p in parts]):
        a, b = pair.split(" through ")
        out.append(f"'{a}' pokes up through '{b}': it is taller than the level of '{b}'s top. A part that holds '{b}' up must END at the underside of '{b}' (shorten '{a}' so its top is at the height where '{b}' starts, and put '{b}' on it with 'on')")
    if min(b[0][2] for b in boxes) > 0.02:
        out.append("nothing rests on the ground: the lowest part starts at z=%.2f, it should start at z=0" % min(b[0][2] for b in boxes))
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            a, b = boxes[i], boxes[j]
            inter = 1.0
            for ax in range(3):
                inter *= max(0.0, min(a[1][ax], b[1][ax]) - max(a[0][ax], b[0][ax]))
            va = max((a[1][0] - a[0][0]) * (a[1][1] - a[0][1]) * (a[1][2] - a[0][2]), 1e-9)
            vb = max((b[1][0] - b[0][0]) * (b[1][1] - b[0][1]) * (b[1][2] - b[0][2]), 1e-9)
            if inter / min(va, vb) > 0.6:
                out.append(f"'{parts[i]['name']}' and '{parts[j]['name']}' fill the same place: give each part its own position (mirror them left/right, front/back)")
    span = max(max(b[1][i] for b in boxes) - min(b[0][i] for b in boxes) for i in range(3))
    if span > 30 or span < 0.02:
        out.append(f"the whole object is {span:.2f} m across: use real-world metres")
    return out


def describe_design(design: Dict[str, Any]) -> str:
    """The design in plain words, from its MEASURED geometry: what each part is like, how high its bottom is, what it stands or rests on, what it carries. (Spatial relations are easier to judge in words than in coordinates.)"""
    parts = design["parts"]
    on = infer_on(design)
    carries: Dict[str, List[str]] = {p["name"]: [] for p in parts}
    for k, v in on.items():
        if v != "ground":
            for sup in v:
                carries[sup].append(k)
    out = []
    for p in parts:
        w, d, h = p["size"]
        kind = "a flat board" if h < 0.12 * max(w, d) else ("a tall thin post" if h > 3 * max(w, d) else "a block")
        z0 = p["at"][2] - h / 2
        sup = "stands on the ground" if on[p["name"]] == "ground" else "rests on " + " and ".join(on[p["name"]])
        car = ("; it carries " + ", ".join(carries[p["name"]])) if carries[p["name"]] else "; nothing rests on it"
        out.append(f"- {p['name']}: {kind} ({w:.2f} x {d:.2f} wide, {h:.2f} m tall), its bottom is {z0:.2f} m above the ground, it {sup}{car}.")
    return "\n".join(out)


def review_design(brain: Brain, task: str, design: Dict[str, Any]) -> Tuple[bool, str, float]:
    """A strict second reading of a finished design, from its measured description: does the arrangement make physical sense for the job (what must hold up what)? (ok, the problem, seconds)."""
    prompt = (f'Job: "{task}".\nA 3D model was planned. Measured description (heights in metres above the ground):\n{describe_design(design)}\n'
              'Think about what must hold up what in a real one. Does this arrangement make physical sense as that object? '
              'Reply JSON {"ok": true or false, "problem": "what is wrong, in one sentence"}.')
    obj, meta = brain.json(prompt, "You are a strict reviewer of 3D models. JSON only.", max_tokens=120)
    if not isinstance(obj, dict) or "ok" not in obj:
        return True, "", float(meta.get("seconds") or 0.0)                       # no usable answer: the review neither blocks nor approves
    return bool(obj["ok"]), str(obj.get("problem", ""))[:240], float(meta.get("seconds") or 0.0)



NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12}


def _stem(w: str) -> str:
    w = re.sub(r"[^a-z]", "", w.lower())
    for suf in ("ves", "ies", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)] + ("f" if suf == "ves" else "y" if suf == "ies" else "")
    return w


def quantity_wants(task: str) -> List[Tuple[int, str]]:
    """What the ORDER counts: 'a bookshelf with three shelves' -> (3, 'shelf'); 'a four legged chair' -> (4, 'leg'); '12 rooms' -> (12, 'room'). Number words and digits before a noun, 'legged' read as 'leg'."""
    out: List[Tuple[int, str]] = []
    for m in re.finditer(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")[\s-]+([a-z]+)", task.lower()):
        n = int(m.group(1)) if m.group(1).isdigit() else NUMBER_WORDS[m.group(1)]
        noun = re.sub(r"ged$", "", m.group(2)) if m.group(2).endswith("legged") else m.group(2)
        noun = "leg" if m.group(2).endswith("legged") else _stem(noun)
        if noun in ("storey", "story", "floor", "inch", "foot", "metre", "meter", "cm", "mm", "minute", "second", "hour", "day", "year", "time", "step", "point", "pixel", "stroke", "word", "sentence", "line", "page", "slide", "row", "column") or len(noun) < 3:
            continue
        out.append((n, noun))
    return out


def quantity_problems(task: str, names: Sequence[str], design: Optional[Dict[str, Any]] = None) -> List[str]:
    """The plan must hold what the order counts. A part counts toward 'shelf' when its name carries that stem; for stacked boards the design's flat parts at distinct heights are counted too (a shelf is a board)."""
    out: List[str] = []
    for n, noun in quantity_wants(task):
        have = sum(1 for nm in names if noun in _stem(nm) or _stem(nm) in noun and len(_stem(nm)) >= 3)
        if design is not None and noun in ("shelf", "board", "plank", "tier", "level", "step", "layer"):
            zs = sorted(p["at"][2] for p in design.get("parts", []) if p["size"][2] < 0.2 * max(p["size"][0], p["size"][1]))
            levels = 0
            last = -1e9
            for z in zs:                                                          # boards closer than 15 cm in height are one level, not two shelves
                if z - last >= 0.15:
                    levels += 1
                    last = z
            have = levels                                                           # a stack noun counts LEVELS (boards at distinct heights), whatever the parts are named
        if have < n:
            out.append(f"the order says {n} {noun}(s) but the plan has only {have} part(s) that are {noun}s: add the missing ones (each its own part, named '{noun}1', '{noun}2' ..., at its own position; separate levels need at least 0.15 m between them in height)")
    return out



def fulfill_counts(task: str, design: Dict[str, Any]) -> List[str]:
    """Make the plan hold what the ORDER counts, by repeating the model's own part (arithmetic, not another model call):
      - 'N shelves / tiers / levels': the board(s) the plan already has are spread over N evenly spaced heights between the lowest board and the top of the posts that carry them (clones are added as needed);
      - 'N legs / posts / columns': the plan's post is repeated at the corners of the board it holds up (inset by its own width) until there are N.
    Returns what was done."""
    notes: List[str] = []
    parts = design.get("parts", [])
    if not parts:
        return notes
    for n, noun in quantity_wants(task):
        names = [p["name"] for p in parts]
        like = [p for p in parts if noun in _stem(p["name"])]
        if noun in ("shelf", "tier", "level", "board", "plank", "layer"):
            flats = [p for p in parts if p["size"][2] < 0.2 * max(p["size"][0], p["size"][1])]
            tmpl = (like or flats or [None])[0]
            if tmpl is None:
                continue
            posts = [p for p in parts if p["size"][2] > 3 * max(p["size"][0], p["size"][1])]
            others = [p for p in flats if p not in like and p["at"][2] - p["size"][2] / 2 < 0.1]         # a base plate under the unit: the first shelf stands above it, not inside it
            lo = max((p["at"][2] + p["size"][2] / 2 + 0.12 for p in others), default=min((p["at"][2] - p["size"][2] / 2 for p in flats), default=0.0))
            top = max([p["at"][2] + p["size"][2] / 2 for p in posts] + [max(p["at"][2] + p["size"][2] / 2 for p in flats)])
            if n < 2 or top - lo < 0.15 * (n - 1):
                continue
            zs = [lo + tmpl["size"][2] / 2 + k * (top - lo - tmpl["size"][2]) / (n - 1) for k in range(n)]
            boards = like if len(like) >= 1 else [tmpl]
            for k, z in enumerate(zs):
                if k < len(boards):
                    boards[k]["at"][0], boards[k]["at"][1], boards[k]["at"][2] = tmpl["at"][0], tmpl["at"][1], z            # one stack: every level shares the footprint
                else:
                    c = {**tmpl, "name": f"{noun}{k + 1}", "at": [tmpl["at"][0], tmpl["at"][1], z], "size": list(tmpl["size"]), "rotate": list(tmpl.get("rotate", [0, 0, 0])), "color": list(tmpl.get("color", [0.7, 0.7, 0.7]))}
                    c.pop("on", None)
                    parts.append(c)
            for b in boards[n:]:
                parts.remove(b)
            notes.append(f"{n} {noun} levels spread between {lo:.2f} and {top:.2f} m")
        elif noun in ("leg", "post", "column", "pillar", "pole"):
            posts = [p for p in parts if noun in _stem(p["name"])] or [p for p in parts if p["size"][2] > 3 * max(p["size"][0], p["size"][1])]
            if not posts or len(posts) >= n:
                continue
            tmpl = posts[0]
            holds = [p for p in parts if p not in posts and p["size"][2] < 0.2 * max(p["size"][0], p["size"][1]) and p["at"][2] - p["size"][2] / 2 >= tmpl["at"][2] + tmpl["size"][2] / 2 - 0.1]
            if not holds:
                continue
            b = holds[0]
            inset = max(tmpl["size"][0], tmpl["size"][1])
            xs = [b["at"][0] - b["size"][0] / 2 + inset, b["at"][0] + b["size"][0] / 2 - inset]
            ys = [b["at"][1] - b["size"][1] / 2 + inset, b["at"][1] + b["size"][1] / 2 - inset]
            corners = [(x, y) for x in xs for y in ys] if n <= 4 else [(x, y) for x in xs for y in ys] + [(b["at"][0], ys[0]), (b["at"][0], ys[1])]
            for k, (x, y) in enumerate(corners[:n]):
                if k < len(posts):
                    posts[k]["at"][0], posts[k]["at"][1] = x, y
                else:
                    c = {**tmpl, "name": f"{noun}{k + 1}", "at": [x, y, tmpl["at"][2]], "size": list(tmpl["size"]), "rotate": list(tmpl.get("rotate", [0, 0, 0])), "color": list(tmpl.get("color", [0.7, 0.7, 0.7]))}
                    c.pop("on", None)
                    parts.append(c)
            notes.append(f"{n} {noun}s placed at the corners of '{b['name']}'")
    return notes



BOARD_NOUNS = ("shelf", "tier", "top", "tabletop", "seat", "board", "plank", "panel", "deck", "floor", "wall", "door", "backrest", "headboard", "lid", "tray", "platform", "slab", "roof", "back", "base")
POST_NOUNS = ("leg", "post", "column", "pillar", "pole", "stand", "support", "upright")


def normalize_shapes(design: Dict[str, Any], shapes: Sequence[str]) -> List[str]:
    """A part NAMED like a board (shelf, seat, top, panel ...) is a box (a round top may stay a cylinder), whatever other shape the model picked (a squashed sphere is not a shelf); a part named like a post may be a cylinder or a box. Returns what changed."""
    notes: List[str] = []
    if "cube" not in shapes:
        return notes
    for p in design.get("parts", []):
        nm = _stem(re.sub(r"[\d_\- ]+$", "", p["name"].lower()))
        words = {_stem(w) for w in re.split(r"[_\-\s]+", p["name"].lower()) if w}
        if (nm in BOARD_NOUNS or words & set(BOARD_NOUNS)) and not (words & set(POST_NOUNS)) and p["shape"] not in ("cube", "cylinder") and p["size"][2] < 0.35 * max(p["size"][0], p["size"][1]) + 1e-9:
            notes.append(f"'{p['name']}' is a {p['shape']} but is named like a board: made a box")
            p["shape"] = "cube"
    return notes


def design_parts(brain: Brain, task: str, shapes: Sequence[str], examples: Sequence[Dict[str, Any]] = (), tries: int = 3, extra_problems: Sequence[str] = (), review: bool = True) -> Dict[str, Any]:
    """Ask the CPU model for a part list; check it against the application's own shapes (validate) and against plain geometry (critic); ask again with the problems named. The attempt with the fewest problems wins."""
    problems: List[str] = list(extra_problems)                       # a reviewer's remarks go into the very first prompt
    meta: List[Dict[str, Any]] = []
    best: Tuple[int, Dict[str, Any], List[str]] = (10 ** 6, {"object": "", "parts": []}, ["no answer"])
    for attempt in range(tries):
        obj, r = brain.json(design_prompt(task, shapes, examples, problems), DESIGN_SYSTEM, max_tokens=1100, temperature=0.2 + 0.15 * attempt)
        meta.append({k: r.get(k) for k in ("seconds", "prompt_tokens", "tokens", "error")})
        design, problems = validate_design(obj, shapes)
        if problems and design["parts"] and all(("rests on" in x or "not above" in x or "loop of supports" in x) for x in problems):
            for pt in design["parts"]:                                   # the support claims ('on') are what is wrong, the parts are fine: drop the claims and let the arithmetic repairs (settle) put every part where it stands
                pt.pop("on", None)
            problems = []
        if not problems:
            fixed = normalize_shapes(design, shapes) + fulfill_counts(task, design) + settle(design)          # arithmetic repairs first: the counts the order names, then through / short post / detached
            if fixed:
                meta[-1]["settled"] = fixed
            problems = critic(design) + quantity_problems(task, [p['name'] for p in design['parts']], design)
        if not problems and review:
            ok, why, secs = review_design(brain, task, design)
            meta[-1]["review"] = {"ok": ok, "problem": why, "seconds": secs}
            if not ok:
                problems = [f"a reviewer who read your design said: {why} (parts that hold something up must stand on the ground; what they hold must rest ON them, named in 'on')"]
        meta[-1]["problems"] = len(problems)
        if len(problems) < best[0] or (len(problems) == best[0] and len(design["parts"]) > len(best[1]["parts"])):
            best = (len(problems), design, list(problems))
        if not problems:
            break
    return {"design": best[1], "problems": best[2], "attempts": meta}


# ------------------------------------------------------------------------------------------------------------------------------------------------ pathways
def plain_step(text: str) -> str:
    """A stored chain 'PRECONDITION: a | ACTION: b | EXPECT: c | IF BLOCKED: d' as one readable step: 'b  (in: a)  -> then c'."""
    m = re.match(r"PRECONDITION:\s*(.*?)\s*\|\s*ACTION:\s*(.*?)\s*\|\s*EXPECT:\s*(.*?)\s*\|\s*IF BLOCKED:", text, re.S)
    if not m:
        return text
    pre, act, exp = (re.sub(r"\s+", " ", g) for g in (m.group(1), m.group(2), m.group(3)))
    s = act
    if pre and pre != "any state":
        s += f"  (where: {pre[:60]})"
    if exp and not exp.startswith("the next step"):
        s += f"  -> then: {exp[:70]}"
    return s


def pathways(ret: Any, limit: int = 3) -> List[Dict[str, Any]]:
    """What a retrieval holds for a goal, as readable pathways: the steps of each plan (a control to click, a key to press) and the evidence behind them."""
    out: List[Dict[str, Any]] = []
    try:
        for plan in ret.plans[:limit]:
            steps = []
            for st in plan.steps[:8]:
                a = st.args or {}
                if st.route == "hotkey":
                    steps.append("press " + str(a.get("keys") or a.get("payload") or a.get("label") or "the shortcut"))
                else:
                    steps.append(plain_step(str(a.get("label") or a.get("text") or "")) if (a.get("label") or a.get("text")) else "click the control")
            out.append({"steps": steps, "reliability": round(min([s.reliability for s in plan.steps] or [0.0]), 2), "source": getattr(plan, "source", "")})
    except Exception:
        pass
    return out


def evidence_lines(ret: Any, limit: int = 6) -> List[str]:
    try:
        return [f"{e.kind}: {e.text[:160]}" for e in ret.evidence[:limit]]
    except Exception:
        return []
