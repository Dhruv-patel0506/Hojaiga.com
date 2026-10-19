"""
agent_artist -- canvas_artist as a tool of the Executor.

`Agent(..., tools=[ArtistTools(painter, rag)])`: a goal that asks for drawing is not a click on one control, it is a plan of many strokes, so the Agent hands it to the tool instead of grounding it on a
screenshot. Everything is read from the goal text and the live canvas -- nothing is bound to an image or a layout:

    "Draw shapes: rectangle, ellipse, triangle, line"            -> Stage 1, one shape per grid cell of the canvas that was FOUND in the picture
    "Draw a flowchart: Input -> Process -> Output"               -> Stage 2, boxes + arrows + labels from the items given
    "Draw curves"                                                -> Stage 3
    "Trace <image path or a name in data/reference_art>"         -> Stage 4, OpenCV tracing of that image
    "Colour the drawing"                                         -> colouring + shading of the LAST traced image (exact RGB through Edit colours)
    "Make a lightboard page of <image> with labels: a, b, c"     -> traced art in the core zone, numbered call-outs, title, steps

Every run is verified on the picture (completion of the planned strokes, containment, repair of strokes that did not land) and becomes a StepRecord; with a RAG attached the workflow is remembered
(Sub-RAG 3 procedure + Sub-RAG 4 parameterised macro).
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional

from core_organs import canvas_artist as CA

IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
REF_DIR = r"D:\new_automation\data\reference_art"


def find_image(goal: str, ref_dir: str = REF_DIR) -> str:
    """The image a goal names: an existing file path in the text, else a file of `ref_dir` whose stem appears in the goal (case-insensitive), else ''."""
    for m in re.finditer(r"([A-Za-z]:[\\/][^\"'<>|*?\n]+?\.(?:png|jpe?g|bmp|webp))", goal, flags=re.I):
        if os.path.isfile(m.group(1)):
            return m.group(1)
    low = goal.lower()
    if os.path.isdir(ref_dir):
        for f in sorted(os.listdir(ref_dir)):
            stem, ext = os.path.splitext(f)
            if ext.lower() in IMG_EXT and stem.lower() in low:
                return os.path.join(ref_dir, f)
    return ""


def _items(goal: str) -> List[str]:
    """The list after a colon: 'A -> B -> C' or 'A, B, C'."""
    tail = goal.split(":", 1)[1] if ":" in goal else ""
    parts = re.split(r"\s*(?:->|=>|→|,|;)\s*", tail.strip())
    return [p.strip() for p in parts if p.strip()]


class ArtistTools:
    DEFAULT_TRACE = (300, 0.0)                                      # (max strokes, share of the edge length to cover); the gauntlet sets (900, 0.97)

    def __init__(self, painter: Any, rag: Any = None, ref_dir: str = REF_DIR):
        self.p, self.rag, self.ref_dir = painter, rag, ref_dir
        self.last: Dict[str, Any] = {}
        self.trace_max, self.trace_coverage = self.DEFAULT_TRACE                  # 300 strokes by default; a caller asking for detail sets e.g. (900, 0.97): strokes are added, longest first, until that share of the edge length is covered

    # ---------------------------------------------------------------- dispatch
    @staticmethod
    def kind_of(goal: str) -> str:
        g = goal.lower()
        if "lightboard" in g:
            return "lightboard"
        if re.search(r"\b(colou?r|shade|paint in)\b", g) and "trace" not in g:
            return "colour"
        if "trace" in g:
            return "trace"
        if "flowchart" in g or "diagram" in g:
            return "flowchart"
        if re.search(r"\bcurves?\b|free-?form|bezier", g):
            return "curves"
        if re.search(r"\bshapes?\b|rectangle|ellipse|triangle", g):
            return "shapes"
        return ""

    def matches(self, goal: str) -> bool:
        return bool(re.search(r"\b(draw|trace|sketch|colou?r|shade|lightboard)\b", goal, flags=re.I)) and bool(self.kind_of(goal))

    # ---------------------------------------------------------------- planning
    def plan(self, kind: str, goal: str, box: CA.Box) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {"kind": kind}
        if kind == "shapes":
            kinds = [k for k in re.findall(r"[a-z]+", goal.lower()) if k in CA.SHAPES] or list(CA.SHAPES)
            n = len(kinds)
            rows = 1 if n == 1 else 2 if n <= 4 else 3
            cols = -(-n // rows)
            cells = CA.grid_cells(box, rows, cols, 60.0)[:n]
            ctx["strokes"] = CA.plan_shapes(cells, kinds[:len(cells)])
            ctx["groups"] = {s.group: [s] for s in ctx["strokes"]}
        elif kind == "flowchart":
            labels = _items(goal) or ["START", "END"]
            ctx["strokes"], boxes = CA.plan_flowchart(box, labels, [(i, i + 1) for i in range(len(labels) - 1)], cols=min(3, len(labels)), pad=30)
            ctx["groups"] = {f"box{i}": [s] for i, s in enumerate(x for x in ctx["strokes"] if x.kind == "rectangle")}
            ctx["labels"] = labels
        elif kind == "curves":
            ctx["strokes"] = CA.plan_curves(CA.grid_cells(box, 2, 3, 40.0))
            ctx["groups"] = {s.group: [s] for s in ctx["strokes"]}
        elif kind in ("trace", "lightboard"):
            import cv2
            img = find_image(goal, self.ref_dir)
            if not img:
                ctx["error"] = "no image named in the goal and none of the reference images' names appear in it"
                return ctx
            ref = cv2.imread(img)
            if kind == "trace":
                ctx["strokes"], ctx["tstats"] = CA.trace_strokes(ref, box, max_strokes=self.trace_max, coverage=self.trace_coverage)
            else:
                from core_organs import canvas_teach as CT, canvas_stages as ST
                zones = CT.lightboard_zones(box)
                art, tstats = CA.trace_strokes(ref, CA.inset(zones["core"], 8), max_strokes=140)
                side = CT.load_sidecar(img)
                given = _items(goal) if re.search(r"labels?\s*:", goal, flags=re.I) else []
                labels = [g for g in given] or ST._labels_of(side)
                lb, layout = CT.plan_lightboard(box, art, ST._title_of(img, side), labels, ST._steps_of(side, len(art), len(labels)), stats=tstats)
                ctx.update({"strokes": art + lb, "art": art, "layout": layout, "tstats": tstats})
            ctx.update({"image": img, "ref": ref})
            ctx.setdefault("groups", {})
        return ctx

    # ---------------------------------------------------------------- run
    def run(self, goal: str):
        from core_organs.agent_executor import StepRecord
        t0 = time.time()
        kind = self.kind_of(goal)
        try:
            self.p.select("Pencil")
            time.sleep(0.5)
            before = self.p.grab()
            box = self.p.canvas()
            if kind == "colour":
                return self._colour(goal, before, box, t0)
            ctx = self.plan(kind, goal, box)
            if ctx.get("error"):
                return StepRecord(goal, "no_action", source="artist", why=ctx["error"], ms=round((time.time() - t0) * 1000))
            strokes = ctx["strokes"]
            ex = CA.execute(self.p, strokes)
            rep = CA.repair(self.p, strokes, box)
            time.sleep(0.6)
            after = self.p.grab()
            comp, cont = CA.completion(strokes, after, box), CA.containment(strokes, box)
            overlaps = CA.overlap_pairs(ctx["groups"], before.size, 6) if ctx.get("groups") else []
            worked = comp >= 97.0 and cont == 100.0 and not overlaps
            self.last = dict(ctx, box=box, after=after, before=before)
            effect = f"{kind}: {len(strokes)} strokes, completion {comp}%, containment {cont}%, overlapping pairs {len(overlaps)}, repaired {rep['redrawn']}"
            if kind == "trace" and ctx.get("tstats"):
                ec = CA.edge_coverage(ctx["tstats"], after, box)
                self.last["edge_coverage"] = ec
                effect += f", reference edge length covered by the plan {ctx['tstats'].get('length_covered_pct')}%, edge pixels inked on the canvas {ec}%"
            logged = self._remember(kind, goal, ctx) if worked else {}
            return StepRecord(goal, "done" if worked else "wrong_effect", source="artist", effect=effect, learned=bool(logged), ms=round((time.time() - t0) * 1000),
                              evidence=[f"drawn {ex['drawn']}/{len(strokes)}", f"repair passes {rep['passes']}"], why="" if worked else "the drawing did not meet completion >= 97%, containment 100%, zero overlap")
        except Exception as exc:
            return StepRecord(goal, "no_effect", source="artist", why=f"{type(exc).__name__}: {str(exc)[:120]}", ms=round((time.time() - t0) * 1000))

    def _colour(self, goal: str, before: Any, box: CA.Box, t0: float):
        from core_organs.agent_executor import StepRecord
        from core_organs import canvas_colour as CC
        if "strokes" not in self.last or "ref" not in self.last or "tstats" not in self.last:
            return StepRecord(goal, "no_action", source="artist", why="nothing traced yet: colouring needs the traced image's map", ms=round((time.time() - t0) * 1000))
        size = before.size
        outline = CA.raster(self.last["strokes"], size, 3)
        ops, info = CC.plan_colouring(self.last["ref"], self.last["tstats"], size, outline, k=5, max_regions=4, shade_top=1)
        counts = CC.apply_ops(self.p, ops)
        time.sleep(0.8)
        after = self.p.grab()
        met = CC.colour_metrics(before, after, ops, info, box, info.get("masks", {}))
        worked = met["mean_coverage_pct"] >= 60.0 and met["bleed_pct"] <= 5.0
        effect = f"colour: {counts}, mean coverage {met['mean_coverage_pct']}%, bleed {met['bleed_pct']}%"
        logged = {}
        if worked:
            logged = self._remember("colour", goal, {"ops": ops, "info": info})
        return StepRecord(goal, "done" if worked else "wrong_effect", source="artist", effect=effect, learned=bool(logged), ms=round((time.time() - t0) * 1000), why="" if worked else "coverage < 60% or bleed > 5%")

    # ---------------------------------------------------------------- memory
    def _remember(self, kind: str, goal: str, ctx: Dict[str, Any]) -> Dict[str, int]:
        if self.rag is None:
            return {}
        try:
            from core_organs import artist_memory as AM
            if kind == "colour":
                steps, params = AM.colour_recipe_steps(ctx.get("info", {}), ctx.get("ops", []))
            else:
                steps, params = AM.layout_recipe_steps(kind, {}), {"kind": kind}
            return AM.log_workflow(self.rag, f"artist_{kind}", goal[:200], steps, params)
        except Exception:
            return {}
