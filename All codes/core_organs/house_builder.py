"""
house_builder -- a whole building in minutes: the model plans ROOMS, a compiler builds the rest.

The slow part of building from a model is asking it for hundreds of coordinates. Here it is asked for one short thing - the list of rooms (name, kind, floor, area) - and everything below that is arithmetic:

    plan_rooms     the CPU brain proposes the rooms (a stored layout is reused when the same kind of house was built before: no model call at all)
    layout         rooms are packed into two rows either side of a corridor, the same footprint on every floor, a stair cell at the same place on every floor
    compile_house  floors with the stair opening cut, outer and inner walls with door / window gaps (a gap is built from segments, lintels and glass, never a boolean), a gabled roof, the stairs,
                   furniture for each kind of room
    build          ONE batched call into the application (script_bridge.batch_add): every part is the application's own 'add cube' command with size / place / turn given, named, coloured and filed in a
                   collection per room and per floor - so the outliner zooms in on a room as the viewport zooms in on it
    views          an outside view, a plan with the roof lifted off, and a close-up of every room, taken with the roof hidden

All sizes are metres. Parts are the same dict the object designer uses (name, shape, size, at, rotate, color) plus `collection`.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

WALL_T, WALL_H, SLAB_T = 0.2, 2.8, 0.25
ROW_DEPTH, CORRIDOR = 4.8, 1.7
DOOR_W, DOOR_H, WIN_W, WIN_SILL, WIN_H = 1.0, 2.1, 1.5, 0.95, 1.25
STAIR_W = 2.4
COL = {"wall": [0.93, 0.91, 0.86], "inner": [0.96, 0.95, 0.92], "floor": [0.62, 0.45, 0.30], "slab": [0.72, 0.72, 0.7], "roof": [0.55, 0.2, 0.15], "glass": [0.55, 0.75, 0.9], "stair": [0.55, 0.42, 0.3],
       "found": [0.45, 0.45, 0.45], "wood": [0.5, 0.33, 0.18], "fabric": [0.25, 0.35, 0.55], "white": [0.95, 0.95, 0.95], "dark": [0.15, 0.15, 0.17], "metal": [0.7, 0.72, 0.75], "bed": [0.8, 0.8, 0.9], "tile": [0.8, 0.85, 0.88]}

KIND_WORDS = [("kitchen", "kitchen"), ("dining", "dining"), ("living", "living"), ("lounge", "living"), ("family", "living"), ("bed", "bedroom"), ("master", "bedroom"), ("guest", "bedroom"), ("bath", "bath"),
              ("toilet", "bath"), ("wc", "bath"), ("study", "office"), ("office", "office"), ("library", "office"), ("stair", "stairs"), ("hall", "hall"), ("entry", "hall"), ("garage", "hall"), ("utility", "hall"),
              ("laundry", "hall"), ("pantry", "kitchen"), ("gym", "living"), ("theatre", "living"), ("cinema", "living")]


def kind_of(name: str, kind: str = "") -> str:
    low = (kind or name).lower()
    for w, k in KIND_WORDS:
        if w in low:
            return k
    for w, k in KIND_WORDS:
        if w in name.lower():
            return k
    return "hall"


def is_building(task: str) -> bool:
    return bool(re.search(r"\b(house|home|villa|mansion|bungalow|cottage|apartment|residence|building)\b", task, re.I))


# ------------------------------------------------------------------------------------------------------------------------------------------------ the rooms
def rooms_prompt(task: str) -> str:
    return (f'Job: "{task}".\nPlan the rooms of this building. Reply JSON {{"floors": n, "rooms": [{{"name": "...", "kind": "living|kitchen|dining|bedroom|bath|office|hall", "floor": 0, "area": square metres}}, ...]}}.\n'
            "Rules: a real home - ground floor has the living, dining, kitchen, an entry hall and a bathroom; upper floors have bedrooms (one master, larger) with bathrooms and a study; "
            "12 to 18 rooms in all for a big house; areas between 8 and 45 m2; at most 3 floors. Name every room.")


def clean_rooms(obj: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    probs: List[str] = []
    rooms: List[Dict[str, Any]] = []
    if not isinstance(obj, dict) or not isinstance(obj.get("rooms"), list):
        return [], ["no 'rooms' list"]
    for i, r in enumerate(obj["rooms"][:30]):
        if not isinstance(r, dict):
            continue
        try:
            area = min(max(float(r.get("area", 15)), 6.0), 60.0)
            fl = min(max(int(r.get("floor", 0)), 0), 2)
        except Exception:
            probs.append(f"room {i + 1} has a bad area or floor")
            continue
        nm = str(r.get("name") or f"Room {i + 1}")[:30]
        rooms.append({"name": nm, "kind": kind_of(nm, str(r.get("kind", ""))), "floor": fl, "area": area})
    if len(rooms) < 4:
        probs.append("fewer than 4 usable rooms")
    return rooms, probs


# ------------------------------------------------------------------------------------------------------------------------------------------------ layout
def layout(rooms: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The same footprint on every floor: a south row and a north row of rooms either side of a corridor; a stair cell at the east end of the north row of every floor."""
    floors = sorted({r["floor"] for r in rooms}) or [0]
    # rooms of a floor, largest first, dealt into the two rows so that both stay about equally long
    placed: List[Dict[str, Any]] = []
    rows_len: Dict[Tuple[int, int], float] = {}
    for fl in floors:
        rs = sorted([r for r in rooms if r["floor"] == fl and r["kind"] != "stairs"], key=lambda r: -r["area"])
        row_sum = [0.0, 0.0]
        rows: List[List[Dict[str, Any]]] = [[], []]
        for r in rs:
            i = 0 if row_sum[0] <= row_sum[1] else 1
            rows[i].append(r)
            row_sum[i] += r["area"] / ROW_DEPTH
        rows_len[(fl, 0)], rows_len[(fl, 1)] = row_sum[0], row_sum[1] + STAIR_W
        for ri in (0, 1):
            for r in rows[ri]:
                placed.append(dict(r, row=ri))
    width = max(max(rows_len.values()), 9.0)
    out_rooms: List[Dict[str, Any]] = []
    for fl in floors:
        for ri in (0, 1):
            rs = [r for r in placed if r["floor"] == fl and r["row"] == ri]
            avail = width - (STAIR_W if ri == 1 else 0.0)
            tot = sum(r["area"] for r in rs) or 1.0
            x = 0.0
            y0 = 0.0 if ri == 0 else ROW_DEPTH + CORRIDOR
            for r in rs:
                w = avail * r["area"] / tot
                out_rooms.append(dict(r, x=x, y=y0, w=w, d=ROW_DEPTH, door_side="N" if ri == 0 else "S"))
                x += w
        out_rooms.append({"name": "Stairs", "kind": "stairs", "floor": fl, "row": 1, "x": width - STAIR_W, "y": ROW_DEPTH + CORRIDOR, "w": STAIR_W, "d": ROW_DEPTH, "door_side": "S", "area": STAIR_W * ROW_DEPTH})
    return {"width": width, "length": 2 * ROW_DEPTH + CORRIDOR, "floors": floors, "rooms": out_rooms}


# ------------------------------------------------------------------------------------------------------------------------------------------------ parts
def box(name: str, cx: float, cy: float, z0: float, w: float, d: float, h: float, color: Sequence[float], coll: str, rot: Sequence[float] = (0, 0, 0)) -> Dict[str, Any]:
    return {"name": name, "shape": "cube", "size": [round(w, 4), round(d, 4), round(h, 4)], "at": [round(cx, 4), round(cy, 4), round(z0 + h / 2.0, 4)], "rotate": list(rot), "color": list(color), "collection": coll}


def wall_parts(orient: str, fixed: float, a: float, b: float, z0: float, openings: Sequence[Tuple[float, float, float, float, str]], coll: str, color: Sequence[float], tag: str) -> List[Dict[str, Any]]:
    """One straight wall from a to b along `orient` ('x' runs along x at y=fixed, 'y' runs along y at x=fixed). `openings` = (centre, width, sill, height, kind). A gap is built from the wall pieces
    beside it, the piece under the sill, the lintel above, and a pane of glass for a window."""
    parts: List[Dict[str, Any]] = []
    ops = sorted(openings, key=lambda o: o[0])
    cur, n = a, 0

    def seg(s: float, e: float, zb: float, hh: float, col: Sequence[float], nm: str) -> None:
        if e - s < 0.02 or hh < 0.02:
            return
        mid, ln = (s + e) / 2.0, e - s
        parts.append(box(nm, mid, fixed, zb, ln, WALL_T, hh, col, coll) if orient == "x" else box(nm, fixed, mid, zb, WALL_T, ln, hh, col, coll))
    for (c, w, sill, hh, kind) in ops:
        s, e = c - w / 2.0, c + w / 2.0
        seg(cur, s, z0, WALL_H, color, f"{tag}_wall{n}")
        n += 1
        seg(s, e, z0, sill, color, f"{tag}_sill{n}")
        seg(s, e, z0 + sill + hh, WALL_H - sill - hh, color, f"{tag}_lintel{n}")
        if kind == "window":
            mid = (s + e) / 2.0
            parts.append(box(f"{tag}_glass{n}", mid, fixed, z0 + sill, e - s, 0.05, hh, COL["glass"], coll) if orient == "x" else box(f"{tag}_glass{n}", fixed, mid, z0 + sill, 0.05, e - s, hh, COL["glass"], coll))
        cur = e
    seg(cur, b, z0, WALL_H, color, f"{tag}_wall{n}")
    return parts


def furniture(room: Dict[str, Any], z0: float, coll: str) -> List[Dict[str, Any]]:
    """Furniture by kind, placed against the walls away from the door. Local helper: `at(u, v)` puts a point u metres along the far wall (from its left) and v metres out from it."""
    k, x, y, w, d = room["kind"], room["x"], room["y"], room["w"], room["d"]
    far_north = room["door_side"] == "S"                                     # door on the south side -> the far wall is the north one
    def P(u: float, v: float) -> Tuple[float, float]:
        return (x + u, (y + d - 0.15 - v) if far_north else (y + 0.15 + v))
    out: List[Dict[str, Any]] = []
    t = room["name"].replace(" ", "")[:10]

    def add(nm: str, u: float, v: float, zz: float, ww: float, dd: float, hh: float, col: Sequence[float]) -> None:
        cx, cy = P(u, v)
        out.append(box(f"{t}_{nm}", cx, cy, z0 + zz, ww, dd, hh, col, coll))
    mid = w / 2.0
    if k == "bedroom" and w > 3.0:
        add("bedframe", mid, 1.05, 0.0, 1.7, 2.1, 0.35, COL["wood"]); add("mattress", mid, 1.05, 0.35, 1.6, 2.0, 0.22, COL["bed"])
        add("headboard", mid, 0.05, 0.0, 1.8, 0.1, 1.0, COL["wood"]); add("pillow1", mid - 0.45, 0.4, 0.57, 0.55, 0.35, 0.12, COL["white"]); add("pillow2", mid + 0.45, 0.4, 0.57, 0.55, 0.35, 0.12, COL["white"])
        add("night1", mid - 1.2, 0.3, 0.0, 0.45, 0.4, 0.5, COL["wood"]); add("night2", mid + 1.2, 0.3, 0.0, 0.45, 0.4, 0.5, COL["wood"])
        add("wardrobe", w - 0.5, 0.35, 0.0, 0.9, 0.6, 2.1, COL["wood"]) if w > 4.5 else None
    elif k == "living" and w > 3.5:
        add("sofaseat", mid, 2.4, 0.0, 2.3, 0.95, 0.45, COL["fabric"]); add("sofaback", mid, 2.85, 0.45, 2.3, 0.2, 0.5, COL["fabric"])
        add("sofaarmL", mid - 1.1, 2.4, 0.0, 0.2, 0.95, 0.65, COL["fabric"]); add("sofaarmR", mid + 1.1, 2.4, 0.0, 0.2, 0.95, 0.65, COL["fabric"])
        add("coffeetop", mid, 1.2, 0.4, 1.1, 0.6, 0.05, COL["wood"])
        for i, (dx, dv) in enumerate(((-0.45, -0.22), (0.45, -0.22), (-0.45, 0.22), (0.45, 0.22))):
            add(f"coffeeleg{i}", mid + dx, 1.2 + dv, 0.0, 0.05, 0.05, 0.4, COL["wood"])
        add("tvunit", mid, 0.25, 0.0, 1.8, 0.4, 0.5, COL["dark"]); add("tv", mid, 0.25, 0.5, 1.2, 0.06, 0.7, COL["dark"])
    elif k == "kitchen" and w > 3.0:
        add("counter", mid, 0.3, 0.0, w - 1.4, 0.6, 0.9, COL["white"]); add("worktop", mid, 0.3, 0.9, w - 1.4, 0.64, 0.04, COL["dark"]); add("cabinets", mid, 0.18, 1.5, w - 1.4, 0.36, 0.7, COL["wood"])
        add("fridge", w - 0.55, 0.4, 0.0, 0.7, 0.7, 1.8, COL["metal"])
        if d > 3.6:
            add("island", mid, 2.2, 0.0, min(2.2, w - 1.2), 0.9, 0.9, COL["white"]); add("islandtop", mid, 2.2, 0.9, min(2.3, w - 1.1), 1.0, 0.05, COL["dark"])
    elif k == "dining" and w > 3.2:
        add("tabletop", mid, 1.9, 0.72, 1.9, 0.95, 0.05, COL["wood"])
        for i, (dx, dv) in enumerate(((-0.8, -0.4), (0.8, -0.4), (-0.8, 0.4), (0.8, 0.4))):
            add(f"tableleg{i}", mid + dx, 1.9 + dv, 0.0, 0.07, 0.07, 0.72, COL["wood"])
        for i, (dx, dv) in enumerate(((-0.6, -0.85), (0.0, -0.85), (0.6, -0.85), (-0.6, 0.85), (0.0, 0.85), (0.6, 0.85))):
            add(f"chairseat{i}", mid + dx, 1.9 + dv, 0.43, 0.45, 0.45, 0.05, COL["fabric"]); add(f"chairback{i}", mid + dx, 1.9 + dv + (0.2 if dv < 0 else -0.2), 0.48, 0.45, 0.05, 0.45, COL["fabric"])
            add(f"chairlegs{i}", mid + dx, 1.9 + dv, 0.0, 0.38, 0.38, 0.43, COL["wood"])
    elif k == "bath" and w > 2.2:
        add("tub", w - 0.95, 0.4, 0.0, 1.7, 0.75, 0.55, COL["white"]); add("toilet", 0.6, 0.4, 0.0, 0.4, 0.6, 0.4, COL["white"]); add("cistern", 0.6, 0.1, 0.4, 0.4, 0.2, 0.4, COL["white"])
        add("vanity", mid, 0.3, 0.0, 0.9, 0.5, 0.85, COL["wood"]) if w > 3.6 else None
    elif k == "office" and w > 2.8:
        add("desktop", mid, 0.4, 0.72, 1.6, 0.75, 0.04, COL["wood"]); add("deskL", mid - 0.75, 0.4, 0.0, 0.05, 0.7, 0.72, COL["wood"]); add("deskR", mid + 0.75, 0.4, 0.0, 0.05, 0.7, 0.72, COL["wood"])
        add("chair", mid, 1.2, 0.0, 0.5, 0.5, 0.5, COL["dark"]); add("shelf", w - 0.4, 0.2, 0.0, 1.2, 0.3, 2.0, COL["wood"])
    return [p for p in out if p]


def compile_house(lay: Dict[str, Any], name: str = "house") -> List[Dict[str, Any]]:
    W, L, floors, rooms = lay["width"], lay["length"], lay["floors"], lay["rooms"]
    parts: List[Dict[str, Any]] = []
    stair = next((r for r in rooms if r["kind"] == "stairs"), None)
    parts.append(box("foundation", W / 2.0, L / 2.0, -0.4, W + 0.6, L + 0.6, 0.4, COL["found"], "Site"))
    for fi, fl in enumerate(floors):
        z0 = fi * (WALL_H + SLAB_T)
        cf = f"Floor{fl}"
        # slab: the whole footprint, with the stair cell left open on every floor above the first
        if fi == 0 or stair is None:
            parts.append(box(f"slab{fl}", W / 2.0, L / 2.0, z0 - SLAB_T, W, L, SLAB_T, COL["slab"], cf))
        else:
            sx0, sy0, sx1 = stair["x"], stair["y"], stair["x"] + stair["w"]
            parts.append(box(f"slab{fl}_A", W / 2.0, sy0 / 2.0, z0 - SLAB_T, W, sy0, SLAB_T, COL["slab"], cf))
            parts.append(box(f"slab{fl}_B", sx0 / 2.0, (sy0 + L) / 2.0, z0 - SLAB_T, sx0, L - sy0, SLAB_T, COL["slab"], cf))
            if W - sx1 > 0.05:
                parts.append(box(f"slab{fl}_C", (sx1 + W) / 2.0, (sy0 + L) / 2.0, z0 - SLAB_T, W - sx1, L - sy0, SLAB_T, COL["slab"], cf))
        # walls: every room edge once; the corridor ends close the building
        edges: Dict[Tuple[str, float, float, float], Dict[str, Any]] = {}

        def edge(orient: str, fixed: float, a: float, b: float, room: Optional[Dict[str, Any]], door: bool = False, window: bool = False) -> None:
            key = (orient, round(fixed, 2), round(a, 2), round(b, 2))
            e = edges.setdefault(key, {"orient": orient, "fixed": fixed, "a": a, "b": b, "ops": [], "exterior": False, "room": room})
            c = (a + b) / 2.0
            if door and not any(o[4] == "door" for o in e["ops"]):
                e["ops"].append((c, DOOR_W, 0.0, DOOR_H, "door"))
            if window and (b - a) >= 2.4 and not any(o[4] == "window" for o in e["ops"]):
                e["ops"].append((c, WIN_W, WIN_SILL, WIN_H, "window"))
            if orient == "x" and (abs(fixed) < 0.01 or abs(fixed - L) < 0.01) or orient == "y" and (abs(fixed) < 0.01 or abs(fixed - W) < 0.01):
                e["exterior"] = True
        for r in [q for q in rooms if q["floor"] == fl]:
            x, y, w, d = r["x"], r["y"], r["w"], r["d"]
            south_face = r["door_side"] == "N"                                              # south-row rooms open to the north (corridor)
            edge("x", y, x, x + w, r, door=(r["door_side"] == "S"), window=(abs(y) < 0.01))
            edge("x", y + d, x, x + w, r, door=(r["door_side"] == "N"), window=(abs(y + d - L) < 0.01))
            edge("y", x, y, y + d, r, window=(abs(x) < 0.01))
            edge("y", x + w, y, y + d, r, window=(abs(x + w - W) < 0.01))
        edge("y", 0.0, ROW_DEPTH, ROW_DEPTH + CORRIDOR, None, window=False)
        edge("y", W, ROW_DEPTH, ROW_DEPTH + CORRIDOR, None, window=False)
        for k2, e in edges.items():
            if fi == 0 and e["exterior"] and e["orient"] == "x" and abs(e["fixed"]) < 0.01 and e["room"] is not None and e["room"]["kind"] in ("hall", "living") and not any(o[4] == "door" for o in e["ops"]):
                e["ops"] = [(( e["a"] + e["b"]) / 2.0, DOOR_W + 0.2, 0.0, DOOR_H + 0.1, "door")]        # the front door: on the first hall / living room that fronts the street
                break
        for e in edges.values():
            col = COL["wall"] if e["exterior"] else COL["inner"]
            rn = (e["room"]["name"].replace(" ", "")[:8] if e["room"] else "corr")
            parts += wall_parts(e["orient"], e["fixed"], e["a"], e["b"], z0, e["ops"], f"{cf}_walls", col, f"f{fl}_{rn}_{e['orient']}{int(e['fixed'] * 10)}_{int(e['a'] * 10)}")
        # room floors (a thin finish) + furniture, one collection per room
        for r in [q for q in rooms if q["floor"] == fl]:
            rc = f"{r['name'].replace(' ', '_')}_F{fl}"
            if r["kind"] == "stairs":
                if fi < len(floors) - 1:
                    n = 14
                    rise, run = (WALL_H + SLAB_T) / n, (r["d"] - 0.6) / n
                    for s in range(n):
                        parts.append(box(f"stair{fl}_{s}", r["x"] + r["w"] / 2.0, r["y"] + 0.3 + run * s + run / 2.0, z0, 1.2, run, rise * (s + 1), COL["stair"], rc))
                continue
            parts.append(box(f"floorfinish_{rc}", r["x"] + r["w"] / 2.0, r["y"] + r["d"] / 2.0, z0, r["w"] - WALL_T, r["d"] - WALL_T, 0.03, COL["floor"] if r["kind"] != "bath" else COL["tile"], rc))
            parts += furniture(r, z0 + 0.03, rc)
        if fi == 0:
            parts.append(box("corridorfloor", W / 2.0, ROW_DEPTH + CORRIDOR / 2.0, z0, W - WALL_T, CORRIDOR - WALL_T, 0.03, COL["floor"], f"Floor{fl}"))
        else:
            parts.append(box(f"corridorfloor{fl}", W / 2.0, ROW_DEPTH + CORRIDOR / 2.0, z0, W - WALL_T, CORRIDOR - WALL_T, 0.03, COL["floor"], f"Floor{fl}"))
    # roof: a gable along the long side, two sloped slabs with the end triangles filled in steps
    top = (len(floors) - 1) * (WALL_H + SLAB_T) + WALL_H
    theta = math.radians(28)
    half = L / 2.0
    rise = half * math.tan(theta)
    slope_len = half / math.cos(theta) + 0.5
    for sgn, ycen in ((1, half / 2.0), (-1, L - half / 2.0)):
        zc = top + rise / 2.0 + 0.09
        parts.append(box(f"roof{'S' if sgn > 0 else 'N'}", W / 2.0, ycen, zc - 0.09, W + 0.8, slope_len, 0.18, COL["roof"], "Roof", rot=(sgn * math.degrees(theta), 0, 0)))
    steps = 7
    for s in range(steps):
        hh = rise / steps
        span = L * (1.0 - (s + 0.5) / steps)
        for xx, nm in ((0.0, "W"), (W, "E")):
            parts.append(box(f"gable{nm}{s}", xx, L / 2.0, top + s * hh, WALL_T, span, hh, COL["wall"], "Roof"))
    return parts


def summarize(lay: Dict[str, Any], parts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    cols: Dict[str, int] = {}
    for p in parts:
        cols[p.get("collection", "")] = cols.get(p.get("collection", ""), 0) + 1
    return {"footprint_m": [round(lay["width"], 1), round(lay["length"], 1)], "floors": len(lay["floors"]), "rooms": len([r for r in lay["rooms"] if r["kind"] != "stairs"]), "parts": len(parts),
            "collections": len(cols), "area_m2": round(lay["width"] * lay["length"] * len(lay["floors"]), 1)}
