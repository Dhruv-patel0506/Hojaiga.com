"""
world_designer -- the local model DESIGNS a whole scene; this file only asks, checks, places and writes the result down.

    python -m core_organs.world_designer "a big Minecraft-style world" [--out DIR] [--size 72] [--no-rag]

What is decided by the model (Qwen, CPU):
  1. the plan      - world size, the biomes (where on the map, land or water, their colours), the kinds of things that stand in it
                     (name, how it looks, size) and where they go (which kind, how many, in which part of the map)
  2. the recipes   - for every kind of thing, its parts: box sizes, offsets, colours (one model call per kind, checked and re-asked)
What is decided by code (no model call, listed in the report so nobody mistakes it for intelligence):
  - the checks   : numbers parse, sizes in range, nothing below the ground, nothing floating (touching graph), overall size near what the plan said
  - the map      : biome rectangles -> a grid -> merged ground slabs, land/water cells
  - the scatter  : exact x,y inside the region the model chose, no overlap between things, nothing in water (seeded, repeatable)
  - the packing  : <= 30 parts per scene piece, hidden foundations, the category file the old build pipeline reads
What the knowledge base (RAG) contributes:
  - facts about the target application (Blender) retrieved for the plan prompt
  - the recipe LIBRARY (data/world_library.json): every recipe the model made is kept; a later run that needs the same kind of thing reuses it with NO model call
The build itself is the old pipeline (field_test --jobs -> app_teaching_automation -> Blender's own bridge).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import time
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, "data")
LIBRARY = os.path.join(DATA, "world_library.json")
GENERATED = os.path.join(DATA, "object_knowledge_generated.json")
JOBS_DIR = os.path.join(DATA, "field_jobs")
WORLDS = os.path.join(DATA, "worlds")

G = 14.0                                  # the height of the ground surface; the hidden foundations and the layered ground are measured from 0
MAX_PARTS_PER_RECIPE = 14
MAX_PIECE_PARTS = 30                      # the old pipeline's cap per piece
MAX_PART_SIZE = 48.0                      # the old pipeline clamps a part at 50 m
MAX_INSTANCES = 60
MAX_TOTAL_PARTS = 420
GRID = 12
NATO = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa", "quebec", "romeo", "sierra",
        "tango", "uniform", "victor", "whiskey", "xray", "yankee", "zulu"]

SYSTEM = "You are a careful 3D scene designer who builds a game-style world out of coloured boxes for Blender. You answer with one JSON object and nothing else."

PLAN_FORMAT = """{
 "world_name": "short name",
 "size_m": 72,
 "biomes": [ {"name": "meadow", "kind": "land", "x": [0.0, 0.5], "y": [0.0, 1.0], "top_color": [0.36, 0.65, 0.22], "under_color": [0.45, 0.31, 0.19]},
             {"name": "lake", "kind": "water", "x": [0.5, 0.6], "y": [0.0, 1.0], "top_color": [0.2, 0.4, 0.9], "under_color": [0.2, 0.4, 0.9]} ],
 "objects": [ {"name": "signpost", "look": "a wooden post with a wide board near the top", "size_m": [1.6, 0.3, 2.6]} ],
 "placements": [ {"object": "signpost", "count": 3, "x": [0.1, 0.4], "y": [0.1, 0.9]} ]
}"""

RECIPE_EXAMPLE = '{"parts": [["post", 0.3, 0.3, 2.5, 0, 0, 0, 0.40, 0.27, 0.13], ["board", 1.6, 0.2, 0.8, 0, 0, 1.8, 0.70, 0.50, 0.30]]}'


# ------------------------------------------------------------------------------------------------------------------------------------------------ small helpers
def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def _vec(v: Any, n: int = 3) -> Optional[List[float]]:
    if not isinstance(v, (list, tuple)) or len(v) < n:
        return None
    out = [_num(x) for x in list(v)[:n]]
    return None if any(x is None for x in out) else [float(x) for x in out]


def _rgb(v: Any, default: Sequence[float]) -> List[float]:
    c = _vec(v)
    if not c:
        return list(default)
    if max(c) > 1.0 and max(c) <= 255.0:
        c = [x / 255.0 for x in c]
    return [round(min(max(x, 0.0), 1.0), 3) for x in c]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")[:24] or "thing"


def _words(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z]+", str(s).lower()) if len(w) > 2]


def _span(v: Any, default: Tuple[float, float] = (0.0, 1.0)) -> Tuple[float, float]:
    r = _vec(v, 2)
    if not r:
        return default
    a, b = sorted((min(max(r[0], 0.0), 1.0), min(max(r[1], 0.0), 1.0)))
    return (a, b) if b - a >= 0.02 else (max(0.0, a - 0.02), min(1.0, b + 0.02))


# ------------------------------------------------------------------------------------------------------------------------------------------------ the library (what was learned)
def load_library() -> Dict[str, Any]:
    try:
        return json.load(open(LIBRARY, encoding="utf-8"))
    except Exception:
        return {"recipes": {}}


def save_library(lib: Dict[str, Any]) -> None:
    os.makedirs(DATA, exist_ok=True)
    tmp = LIBRARY + ".tmp"
    json.dump(lib, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, LIBRARY)


def find_recipe(lib: Dict[str, Any], name: str, look: str, size: Sequence[float]) -> Optional[Tuple[str, Dict[str, Any], float]]:
    """A recipe already made for the same kind of thing: the name words overlap (and the size is in the same range). (key, recipe, score) or None."""
    want = set(_words(name))
    best: Optional[Tuple[str, Dict[str, Any], float]] = None
    for key, rec in lib.get("recipes", {}).items():
        have = set(_words(key)) | set(_words(rec.get("name", "")))
        if not want or not have:
            continue
        ov = len(want & have) / max(len(want), len(have))
        if ov < 0.99 and not (ov >= 0.5 and len(want) > 1):
            continue
        s0, s1 = rec.get("size_m") or [1, 1, 1], list(size)
        ratio = max(s1[2] / max(s0[2], 0.1), s0[2] / max(s1[2], 0.1))
        if ratio > 2.2:
            continue
        if best is None or ov > best[2]:
            best = (key, rec, ov)
    return best


# ------------------------------------------------------------------------------------------------------------------------------------------------ the knowledge base (RAG)
def app_facts(app: str = "blender", question: str = "add a box, set its size and colour, place it, group parts into a scene", k: int = 4) -> List[str]:
    """A few facts about the target application from the RAG. Empty when the knowledge base is not reachable (the report says so)."""
    try:
        from core_organs import rag as R
        from core_organs.mind import app_qa
        rag = R.get_rag()
        names = app_qa.app_names(rag)
        keys = sorted({v for v in names.values() if app in v.lower() and not v.startswith(("web:", "webapp:"))})[:4]
        rows = app_qa.evidence(rag, keys, question, k=k) if keys else []
        return [re.sub(r"\s+", " ", str(r.get("text", "")))[:220] for r in rows[:k] if r.get("text")]
    except Exception:
        return []


# ------------------------------------------------------------------------------------------------------------------------------------------------ 1. the plan (model)
def plan_prompt(request: str, known: Sequence[str], facts: Sequence[str], problems: Sequence[str], size_hint: int = 0) -> str:
    lines = [f"A person asked for: \"{request}\".",
             "Design the world yourself. Decide the size of the world in metres (between 48 and 96" + (f"; the person wants about {size_hint}" if size_hint else "") + "), the biomes and where each lies on the map, "
             "which kinds of things stand in it, what each looks like, how big it is and where the things are placed. Make it varied, rich and believable: several different regions, each with its own character.",
             "Map: x runs left to right, y runs bottom (south) to top (north); every x and y range is a fraction between 0 and 1 of the world. Biomes should cover the whole map together; 'water' biomes (rivers, lakes) take no objects. "
             "Use 4 to 6 biomes, 8 to 12 kinds of things, and at most 60 things in total (sum of counts). A kind of thing must be useful for the world (trees, buildings, rocks, crops, landmarks, ...). Sizes in metres [width, depth, height]; "
             "things are blocky game objects, trees 6 to 12 m high, houses 8 to 14 m wide, mountains 20 to 40 m.",
             "Answer with exactly this JSON shape (this example is only the SHAPE, invent your own content):", PLAN_FORMAT]
    if known:
        lines.append("You already know how to build these kinds of things (reusing them costs nothing; use the same names when you want them again): " + ", ".join(known[:40]) + ".")
    if facts:
        lines.append("Facts about the application the world is built in (from the knowledge base): " + " | ".join(facts))
    if problems:
        lines.append("Your last answer had these problems, fix them: " + "; ".join(problems))
    return "\n".join(lines)


def check_plan(raw: Any) -> Tuple[Dict[str, Any], List[str]]:
    problems: List[str] = []
    if not isinstance(raw, dict):
        return {}, ["the answer is not a JSON object"]
    size = _num(raw.get("size_m")) or 72.0
    size = min(max(size, 48.0), 96.0)
    biomes: List[Dict[str, Any]] = []
    for b in (raw.get("biomes") or [])[:8]:
        if not isinstance(b, dict):
            continue
        kind = "water" if str(b.get("kind", "land")).lower().startswith("w") else "land"
        top = _rgb(b.get("top_color"), (0.36, 0.65, 0.22) if kind == "land" else (0.2, 0.4, 0.9))
        under = _rgb(b.get("under_color"), (0.45, 0.31, 0.19) if kind == "land" else top)
        biomes.append({"name": str(b.get("name") or f"biome{len(biomes) + 1}")[:30], "kind": kind, "x": _span(b.get("x")), "y": _span(b.get("y")), "top_color": top, "under_color": under})
    if len(biomes) < 2:
        problems.append("give at least 2 biomes, each with name, kind, x range, y range, top_color and under_color")
    if not any(b["kind"] == "land" for b in biomes):
        problems.append("at least one biome must be land")
    objs: Dict[str, Dict[str, Any]] = {}
    for o in (raw.get("objects") or [])[:16]:
        if not isinstance(o, dict) or not o.get("name"):
            continue
        sz = _vec(o.get("size_m")) or [3.0, 3.0, 3.0]
        sz = [min(max(x, 0.4), 44.0) for x in sz]
        objs[str(o["name"]).lower().strip()[:30]] = {"name": str(o["name"]).lower().strip()[:30], "look": str(o.get("look") or "")[:200], "size_m": sz}
    if len(objs) < 3:
        problems.append("give at least 3 kinds of things in 'objects' (name, look, size_m)")
    places: List[Dict[str, Any]] = []
    for p in (raw.get("placements") or [])[:40]:
        if not isinstance(p, dict):
            continue
        nm = str(p.get("object", "")).lower().strip()
        if nm not in objs:
            near = [k for k in objs if nm and (nm in k or k in nm)]
            nm = near[0] if near else ""
        if not nm:
            problems.append(f"placement of '{p.get('object')}' names a kind that is not in 'objects'")
            continue
        cnt = int(min(max(_num(p.get("count")) or 1, 1), 30))
        places.append({"object": nm, "count": cnt, "x": _span(p.get("x")), "y": _span(p.get("y"))})
    if not places:
        problems.append("give 'placements': object, count, x range, y range")
    used = {p["object"] for p in places}
    for nm in list(objs):
        if nm not in used:
            del objs[nm]                                                                    # a kind nobody places is not built
    return {"world_name": str(raw.get("world_name") or "world")[:40], "size_m": size, "biomes": biomes, "objects": list(objs.values()), "placements": places}, problems


def make_plan(brain: Any, request: str, known: Sequence[str], facts: Sequence[str], size_hint: int, log: List[Dict[str, Any]], tries: int = 3) -> Tuple[Dict[str, Any], List[str]]:
    best: Tuple[int, Dict[str, Any], List[str]] = (10 ** 6, {}, ["no answer"])
    problems: List[str] = []
    for attempt in range(tries):
        raw, r = brain.json(plan_prompt(request, known, facts, problems, size_hint), SYSTEM, max_tokens=1700, temperature=0.5 + 0.15 * attempt, timeout=1500.0)
        plan, problems = check_plan(raw)
        log.append({"stage": "plan", "attempt": attempt + 1, "seconds": r.get("seconds"), "tokens": r.get("tokens"), "problems": list(problems)})
        if len(problems) < best[0]:
            best = (len(problems), plan, list(problems))
        if not problems:
            break
    return best[1], best[2]


# ------------------------------------------------------------------------------------------------------------------------------------------------ 2. the recipes (model)
def recipe_prompt(world: str, obj: Dict[str, Any], problems: Sequence[str]) -> str:
    w, d, h = obj["size_m"]
    lines = [f"World: {world}. Build the object \"{obj['name']}\": {obj['look']}. It should be about {w:g} m wide (x), {d:g} m deep (y) and {h:g} m high (z).",
             "Build it from boxes, in a chunky blocky game style, with flat colours. Each box is one list: [name, width_x, depth_y, height_z, dx, dy, dz, r, g, b] where "
             "(dx, dy) is the middle of the box seen from above, measured from the middle of the object, and dz is the height of the box's BOTTOM above the ground (the ground is z = 0, nothing goes below it). "
             "Sizes are in metres; r, g, b are colours between 0 and 1.",
             f"Rules: {3 if h > 1.5 else 1} to {MAX_PARTS_PER_RECIPE} boxes; at least one box stands on the ground (dz = 0); every box touches or overlaps another box, nothing floats; "
             "put real structure in it (a tree has a trunk and stacked leaf blocks, a house has walls, a roof, a door and windows) and use several colours.",
             f"Example of the format only (a different object): {RECIPE_EXAMPLE}",
             'Answer with JSON: {"parts": [ ...boxes... ]}']
    if problems:
        lines.append("Your last answer had these problems, fix them: " + "; ".join(problems))
    return "\n".join(lines)


def _rows(raw: Any) -> List[Any]:
    if isinstance(raw, dict):
        for k in ("parts", "boxes", "blocks"):
            if isinstance(raw.get(k), list):
                return raw[k]
    return raw if isinstance(raw, list) else []


def check_recipe(raw: Any, want: Sequence[float]) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """(parts, problems the model must fix, repairs the code made). A part: name, size[3], off[3] (centre dx, dy; dz = bottom above the ground), color."""
    problems: List[str] = []
    repairs: List[str] = []
    parts: List[Dict[str, Any]] = []
    rows = _rows(raw)
    if not rows:
        return [], ["the answer has no 'parts' list of boxes"], repairs
    for i, r in enumerate(rows[:MAX_PARTS_PER_RECIPE]):
        nm, size, off, col = f"part{i + 1}", None, None, None
        if isinstance(r, (list, tuple)) and len(r) >= 10 and isinstance(r[0], str):
            nm, size, off, col = r[0], _vec(r[1:4]), _vec(r[4:7]), _vec(r[7:10])
        elif isinstance(r, dict):
            nm = str(r.get("name") or nm)
            size, off, col = _vec(r.get("size")), _vec(r.get("offset") or r.get("at") or r.get("pos")), _vec(r.get("color"))
        if not size or not off:
            problems.append(f"box {i + 1} is not [name, w, d, h, dx, dy, dz, r, g, b]")
            continue
        if min(size) < 0.08 or max(size) > 40:
            problems.append(f"box '{nm}': every size must be between 0.1 and 40 metres")
            continue
        if off[2] < -0.01:
            problems.append(f"box '{nm}' is below the ground (dz {off[2]:g}); dz is the height of its bottom above the ground and cannot be negative")
            continue
        parts.append({"name": _slug(nm) or f"part{i + 1}", "size": size, "off": off, "color": _rgb(col, (0.6, 0.6, 0.6))})
    if len(rows) > MAX_PARTS_PER_RECIPE:
        repairs.append(f"kept the first {MAX_PARTS_PER_RECIPE} of {len(rows)} boxes")
    if not parts:
        return [], problems or ["no usable box"], repairs
    from core_organs import brain_planner as BP
    boxes = [BP.part_box({"size": p["size"], "at": [p["off"][0], p["off"][1], p["off"][2] + p["size"][2] / 2.0], "rotate": [0, 0, 0]}) for p in parts]
    if not any(p["off"][2] <= 0.05 for p in parts):
        problems.append("no box stands on the ground: the lowest box must have dz = 0")
    comps = BP.components(boxes, gap=0.05)
    if len(comps) > 1:
        ground = [c for c in comps if any(parts[i]["off"][2] <= 0.05 for i in c)]
        keep = max(ground or comps, key=lambda c: sum(parts[i]["size"][0] * parts[i]["size"][1] * parts[i]["size"][2] for i in c))
        lost = [parts[i]["name"] for c in comps if c is not keep for i in c]
        problems.append(f"these boxes do not touch the rest (they float): {', '.join(lost[:6])}; make every box touch or overlap another one")
        repairs_if_kept = f"dropped {len(lost)} floating box(es): {', '.join(lost[:6])}"
        parts_kept = [parts[i] for i in sorted(keep)]
    else:
        repairs_if_kept, parts_kept = "", parts
    lo = [min(b[0][k] for b in boxes) for k in range(3)]
    hi = [max(b[1][k] for b in boxes) for k in range(3)]
    dims = [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]]
    if want and want[2] > 0 and (dims[2] > 2.6 * want[2] or dims[2] < 0.38 * want[2]):
        problems.append(f"the object is {dims[2]:.1f} m high but it should be about {want[2]:g} m")
    if want and max(want[0], want[1]) > 0 and (max(dims[0], dims[1]) > 2.8 * max(want[0], want[1]) or max(dims[0], dims[1]) < 0.3 * max(want[0], want[1])):
        problems.append(f"the object is {max(dims[0], dims[1]):.1f} m wide but it should be about {max(want[0], want[1]):g} m")
    if repairs_if_kept:
        repairs.append(repairs_if_kept)
    return parts_kept, problems, repairs


def make_recipe(brain: Any, world: str, obj: Dict[str, Any], log: List[Dict[str, Any]], tries: int = 3) -> Dict[str, Any]:
    best: Optional[Tuple[int, List[Dict[str, Any]], List[str], List[str]]] = None
    problems: List[str] = []
    for attempt in range(tries):
        raw, r = brain.json(recipe_prompt(world, obj, problems), SYSTEM, max_tokens=900, temperature=0.35 + 0.15 * attempt, timeout=1200.0)
        parts, problems, repairs = check_recipe(raw, obj["size_m"])
        log.append({"stage": "recipe", "object": obj["name"], "attempt": attempt + 1, "seconds": r.get("seconds"), "tokens": r.get("tokens"), "parts": len(parts), "problems": list(problems), "repairs": repairs})
        if parts and (best is None or len(problems) < best[0]):
            best = (len(problems), parts, list(problems), repairs)
        if parts and not problems:
            break
    if best is None:
        return {"ok": False, "name": obj["name"], "why": "no usable answer"}
    return {"ok": True, "name": obj["name"], "look": obj["look"], "size_m": obj["size_m"], "parts": best[1], "left_over_problems": best[2], "code_repairs": best[3], "attempts": len([x for x in log if x.get("object") == obj["name"]])}


# ------------------------------------------------------------------------------------------------------------------------------------------------ 3. the map and the scatter (code)
def biome_grid(plan: Dict[str, Any]) -> Tuple[List[List[int]], float]:
    """grid[j][i] = index of the biome that owns the cell (the last biome whose rectangle contains the cell's middle; none: the nearest). Second value: the fraction of cells no rectangle covered."""
    bs = plan["biomes"]
    grid = [[-1] * GRID for _ in range(GRID)]
    uncovered = 0
    for j in range(GRID):
        for i in range(GRID):
            fx, fy = (i + 0.5) / GRID, (j + 0.5) / GRID
            owner = -1
            for k, b in enumerate(bs):
                if b["x"][0] <= fx <= b["x"][1] and b["y"][0] <= fy <= b["y"][1]:
                    owner = k
            if owner < 0:
                uncovered += 1
                owner = min(range(len(bs)), key=lambda k: math.hypot(fx - (bs[k]["x"][0] + bs[k]["x"][1]) / 2, fy - (bs[k]["y"][0] + bs[k]["y"][1]) / 2))
            grid[j][i] = owner
    return grid, uncovered / float(GRID * GRID)


def merged_rects(grid: List[List[int]]) -> List[Tuple[int, int, int, int, int]]:
    """(biome, i0, i1, j0, j1) rectangles, inclusive, covering the grid exactly once: runs along x, then equal runs in consecutive rows merged."""
    runs: Dict[Tuple[int, int, int], List[int]] = {}
    out: List[Tuple[int, int, int, int, int]] = []
    open_: Dict[Tuple[int, int, int], int] = {}
    for j in range(GRID):
        now: Dict[Tuple[int, int, int], int] = {}
        i = 0
        while i < GRID:
            k = grid[j][i]
            e = i
            while e + 1 < GRID and grid[j][e + 1] == k:
                e += 1
            key = (k, i, e)
            now[key] = open_.get(key, j)
            i = e + 1
        for key, j0 in open_.items():
            if key not in now:
                out.append((key[0], key[1], key[2], j0, j - 1))
        open_ = now
    for key, j0 in open_.items():
        out.append((key[0], key[1], key[2], j0, GRID - 1))
    return out


def ground_parts(plan: Dict[str, Any], grid: List[List[int]]) -> List[Dict[str, Any]]:
    S = plan["size_m"]
    c = S / GRID
    parts: List[Dict[str, Any]] = []
    tiles = max(1, math.ceil(S / MAX_PART_SIZE))
    tw = S / tiles
    for a in range(tiles):                                                                 # the stone under everything, in tiles the build pipeline accepts
        for b in range(tiles):
            parts.append({"name": f"stone_{a}_{b}", "size": [tw, tw, 8.0], "at": [-S / 2 + tw * (a + 0.5), -S / 2 + tw * (b + 0.5), G - 10.0], "color": [0.5, 0.5, 0.52]})
    for n, (k, i0, i1, j0, j1) in enumerate(merged_rects(grid)):
        bm = plan["biomes"][k]
        x0, x1, y0, y1 = -S / 2 + i0 * c, -S / 2 + (i1 + 1) * c, -S / 2 + j0 * c, -S / 2 + (j1 + 1) * c
        nx, ny = max(1, math.ceil((x1 - x0) / MAX_PART_SIZE)), max(1, math.ceil((y1 - y0) / MAX_PART_SIZE))
        for a in range(nx):
            for b in range(ny):
                w, d = (x1 - x0) / nx, (y1 - y0) / ny
                cx, cy = x0 + w * (a + 0.5), y0 + d * (b + 0.5)
                tag = f"{_slug(bm['name'])}_{n}_{a}{b}"
                if bm["kind"] == "water":
                    parts.append({"name": f"water_{tag}", "size": [w, d, 4.8], "at": [cx, cy, G - 3.6], "color": bm["top_color"]})
                else:
                    parts.append({"name": f"under_{tag}", "size": [w, d, 4.0], "at": [cx, cy, G - 4.0], "color": bm["under_color"]})
                    parts.append({"name": f"top_{tag}", "size": [w, d, 2.0], "at": [cx, cy, G - 1.0], "color": bm["top_color"]})
    return parts


def scatter(plan: Dict[str, Any], grid: List[List[int]], recipes: Dict[str, Dict[str, Any]], seed: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Exact positions inside the regions the model chose. Skips water, keeps a gap between things. Returns (instances, notes)."""
    rng = random.Random(seed)
    S = plan["size_m"]
    notes: List[str] = []
    placed: List[Dict[str, Any]] = []
    total = 0
    for pl in plan["placements"]:
        rec = recipes.get(pl["object"])
        if not rec or not rec.get("ok"):
            notes.append(f"'{pl['object']}' has no recipe, its {pl['count']} placement(s) were skipped")
            continue
        xs = [p["off"][0] - p["size"][0] / 2 for p in rec["parts"]] + [p["off"][0] + p["size"][0] / 2 for p in rec["parts"]]
        ys = [p["off"][1] - p["size"][1] / 2 for p in rec["parts"]] + [p["off"][1] + p["size"][1] / 2 for p in rec["parts"]]
        fx, fy = max(xs) - min(xs), max(ys) - min(ys)
        cx0, cy0 = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        rad = max(fx, fy) / 2 + 0.8
        got = 0
        for _ in range(pl["count"]):
            if total >= MAX_INSTANCES:
                notes.append(f"stopped at {MAX_INSTANCES} things in total")
                break
            for _try in range(300):
                u = pl["x"][0] + rng.random() * (pl["x"][1] - pl["x"][0])
                v = pl["y"][0] + rng.random() * (pl["y"][1] - pl["y"][0])
                x, y = (u - 0.5) * S, (v - 0.5) * S
                if abs(x) + rad > S / 2 or abs(y) + rad > S / 2:
                    continue
                cells = {(min(GRID - 1, max(0, int((x + dx + S / 2) / S * GRID))), min(GRID - 1, max(0, int((y + dy + S / 2) / S * GRID)))) for dx in (-fx / 2, 0, fx / 2) for dy in (-fy / 2, 0, fy / 2)}
                if any(plan["biomes"][grid[j][i]]["kind"] == "water" for i, j in cells):
                    continue
                if any(math.hypot(x - q["x"], y - q["y"]) < rad + q["rad"] for q in placed):
                    continue
                placed.append({"object": pl["object"], "x": x - cx0, "y": y - cy0, "cx": x, "cy": y, "rad": rad, "fx": fx, "fy": fy, "foot": (cx0, cy0),
                               "biome": plan["biomes"][grid[min(GRID - 1, max(0, int((y + S / 2) / S * GRID)))][min(GRID - 1, max(0, int((x + S / 2) / S * GRID)))]]})
                got += 1
                total += 1
                break
        if got < pl["count"]:
            notes.append(f"'{pl['object']}': placed {got} of {pl['count']} (no free dry spot in its region for the rest)")
    return placed, notes


# ------------------------------------------------------------------------------------------------------------------------------------------------ 4. pieces for the old pipeline (code)
def instance_parts(inst: Dict[str, Any], rec: Dict[str, Any], n: int) -> List[Dict[str, Any]]:
    tag = f"{_slug(inst['object'])}{n}"
    out: List[Dict[str, Any]] = []
    fw, fd = min(max(inst["fx"], 0.6), MAX_PART_SIZE), min(max(inst["fy"], 0.6), MAX_PART_SIZE)
    out.append({"name": f"{tag}_found", "size": [fw, fd, G], "at": [inst["cx"], inst["cy"], G / 2.0], "color": inst["biome"]["top_color"]})        # hidden inside the ground, keeps the thing standing at ground height
    for p in rec["parts"]:
        out.append({"name": f"{tag}_{p['name']}", "size": [round(x, 3) for x in p["size"]],
                    "at": [round(inst["x"] + p["off"][0], 3), round(inst["y"] + p["off"][1], 3), round(G + p["off"][2] + p["size"][2] / 2.0, 3)], "color": p["color"]})
    seen: Dict[str, int] = {}
    for p in out:                                                                           # one name per part, always
        seen[p["name"]] = seen.get(p["name"], 0) + 1
        if seen[p["name"]] > 1:
            p["name"] = f"{p['name']}{seen[p['name']]}"
    return out


def pack(groups: Sequence[List[Dict[str, Any]]]) -> List[List[Dict[str, Any]]]:
    pieces: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    for g in groups:
        if len(cur) + len(g) > MAX_PIECE_PARTS and cur:
            pieces.append(cur)
            cur = []
        cur += g
    if cur:
        pieces.append(cur)
    return pieces


def to_category(key: str, parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"keywords": [key], "dims": {"W": [4, 200, 48], "D": [4, 200, 48], "H": [3, 80, 26]}, "params": {},
            "parts": [{"name": p["name"], "shape": "cube", "size": [repr(round(float(x), 3)) for x in p["size"]], "at": [repr(round(float(x), 3)) for x in p["at"]], "color": p["color"]} for p in parts],
            "scene": True, "made_by": "world_designer"}


def compile_world(plan: Dict[str, Any], recipes: Dict[str, Dict[str, Any]], seed: int, tag: str) -> Dict[str, Any]:
    grid, uncovered = biome_grid(plan)
    ground = ground_parts(plan, grid)
    insts, notes = scatter(plan, grid, recipes, seed)
    groups_ground = pack([[p] for p in ground])
    groups_inst = []
    counts: Dict[str, int] = {}
    for inst in insts:
        counts[inst["object"]] = counts.get(inst["object"], 0) + 1
        groups_inst.append(instance_parts(inst, recipes[inst["object"]], counts[inst["object"]]))
    total = 0
    kept: List[List[Dict[str, Any]]] = []
    for g in groups_inst:
        if total + len(g) > MAX_TOTAL_PARTS:
            notes.append(f"parts budget {MAX_TOTAL_PARTS} reached, the rest of the things were left out")
            break
        kept.append(g)
        total += len(g)
    pieces = [(f"ground", p) for p in groups_ground] + [("things", p) for p in pack(kept)]
    cats: Dict[str, Any] = {}
    jobs: List[Dict[str, Any]] = []
    prev = ""
    for n, (kind, parts) in enumerate(pieces):
        word = NATO[n] if n < len(NATO) else f"{NATO[n % len(NATO)]}x{n}"
        key = f"genworld {word}"
        cats[key] = to_category(key, parts)
        label = f"gw_{tag}_{word}"
        job = {"task": ("build " if not prev else "add ") + f"{key} in Blender", "label": label, "app": "Blender", "recall": False, "vlm": False}
        if prev:
            job["file"] = f"@saved:{prev}"
        jobs.append(job)
        prev = label
    return {"categories": cats, "jobs": jobs, "instances": len(insts), "parts": sum(len(p) for _, p in pieces), "pieces": len(pieces), "notes": notes, "uncovered_fraction": round(uncovered, 3),
            "cells": {plan["biomes"][k]["name"]: sum(row.count(k) for row in grid) for k in range(len(plan["biomes"]))}}


# ------------------------------------------------------------------------------------------------------------------------------------------------ the whole thing
def design(request: str, out_dir: str = "", size_hint: int = 0, use_rag: bool = True, brain: Any = None, say: Any = print) -> Dict[str, Any]:
    from core_organs import brain_planner as BP
    t0 = time.time()
    brain = brain or BP.Brain()
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = out_dir or os.path.join(WORLDS, ts)
    os.makedirs(out_dir, exist_ok=True)
    log: List[Dict[str, Any]] = []
    rep: Dict[str, Any] = {"request": request, "started": ts, "model": brain.model, "out_dir": out_dir}
    if not brain.alive():
        rep["error"] = f"the model {brain.model} is not reachable"
        return rep
    lib = load_library()
    known = sorted({r.get("name", k) for k, r in lib.get("recipes", {}).items()})
    facts = app_facts() if use_rag else []
    rep["rag_facts"] = facts
    rep["library_before"] = len(lib.get("recipes", {}))
    say(f"[plan] asking {brain.model}; {len(facts)} fact(s) from the knowledge base, {len(known)} recipe(s) already known")
    plan, problems = make_plan(brain, request, known, facts, size_hint, log)
    rep["plan"], rep["plan_problems"] = plan, problems
    json.dump(plan, open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8"), indent=1)
    if not plan or not plan.get("objects"):
        rep["error"] = "the model gave no usable plan: " + "; ".join(problems)
        return rep
    say(f"[plan] {plan['world_name']}: {plan['size_m']:g} m, {len(plan['biomes'])} biomes, {len(plan['objects'])} kinds of things, {sum(p['count'] for p in plan['placements'])} placements ({time.time() - t0:.0f}s)")
    recipes: Dict[str, Dict[str, Any]] = {}
    reused, made = [], []
    for obj in plan["objects"]:
        hit = find_recipe(lib, obj["name"], obj["look"], obj["size_m"])
        if hit:
            recipes[obj["name"]] = {"ok": True, "name": obj["name"], "parts": hit[1]["parts"], "size_m": hit[1].get("size_m"), "from_library": hit[0]}
            reused.append(obj["name"])
            say(f"[recipe] {obj['name']}: reused '{hit[0]}' from the library (no model call)")
            continue
        say(f"[recipe] {obj['name']}: asking the model ...")
        rec = make_recipe(brain, plan["world_name"], obj, log)
        recipes[obj["name"]] = rec
        made.append(obj["name"])
        if rec["ok"]:
            lib.setdefault("recipes", {})[obj["name"]] = {"name": obj["name"], "look": obj["look"], "size_m": obj["size_m"], "parts": rec["parts"], "made_by": brain.model, "made": ts, "attempts": rec["attempts"],
                                                          "left_over_problems": rec["left_over_problems"]}
            save_library(lib)
        say(f"[recipe] {obj['name']}: {'%d boxes' % len(rec['parts']) if rec['ok'] else 'FAILED'}; {len(rec.get('left_over_problems', []))} problem(s) left; total {time.time() - t0:.0f}s")
    rep["recipes"] = {k: {kk: vv for kk, vv in v.items() if kk != "parts"} | {"boxes": len(v.get("parts", []))} for k, v in recipes.items()}
    json.dump({k: v for k, v in recipes.items()}, open(os.path.join(out_dir, "recipes.json"), "w", encoding="utf-8"), indent=1)
    seed = zlib.crc32((request + json.dumps(plan, sort_keys=True)).encode("utf-8"))
    comp = compile_world(plan, recipes, seed, ts[-6:])
    gen = {"categories": {}}
    try:
        gen = json.load(open(GENERATED, encoding="utf-8"))
    except Exception:
        pass
    gen["categories"] = {k: v for k, v in gen.get("categories", {}).items() if not k.startswith("genworld ")}       # one generated world at a time (the piece names are shared)
    gen["categories"].update(comp["categories"])
    json.dump(gen, open(GENERATED, "w", encoding="utf-8"), indent=1)
    os.makedirs(JOBS_DIR, exist_ok=True)
    jobs_path = os.path.join(JOBS_DIR, f"genworld_{ts}.json")
    json.dump(comp["jobs"], open(jobs_path, "w", encoding="utf-8"), indent=1)
    rep.update({"jobs_file": jobs_path, "pieces": comp["pieces"], "parts": comp["parts"], "instances": comp["instances"], "compile_notes": comp["notes"], "uncovered_fraction": comp["uncovered_fraction"],
                "cells": comp["cells"], "recipes_reused": reused, "recipes_made": made})
    calls = brain.calls
    rep["model_calls"] = {"count": len(calls), "seconds": round(sum(c.get("seconds") or 0 for c in calls), 1), "tokens": sum(c.get("tokens") or 0 for c in calls), "failed": sum(1 for c in calls if not c.get("ok"))}
    rep["log"] = log
    rep["seconds"] = round(time.time() - t0, 1)
    json.dump(rep, open(os.path.join(out_dir, "design_report.json"), "w", encoding="utf-8"), indent=1, default=str)
    say(f"[done] {comp['pieces']} pieces, {comp['parts']} parts, {comp['instances']} things; {len(calls)} model calls ({rep['model_calls']['seconds']}s); jobs: {jobs_path}")
    return rep


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="let the local model design a world")
    ap.add_argument("request", nargs="?", default="a big Minecraft-style world")
    ap.add_argument("--out", default="")
    ap.add_argument("--size", type=int, default=0)
    ap.add_argument("--no-rag", action="store_true")
    a = ap.parse_args(argv)
    r = design(a.request, a.out, a.size, not a.no_rag)
    print(json.dumps({k: v for k, v in r.items() if k not in ("plan", "log", "recipes")}, indent=1, default=str)[:3000])
    return 0 if not r.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
