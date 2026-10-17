"""
artist_memory -- everything the artist and the tutor do on the canvas is remembered, in the five sub-RAGs and in the vision model's training data.

    Sub-RAG 1 (icons)        the picture of every toolbar control that was pressed, with its name (`icons.learn`): the icon vault learns what the Brushes / Fill / Eraser / Shapes icons look like
    Sub-RAG 2 (UI graph)     every verified UI Automation action becomes a transition between two screen states (the before / after control sets), through `rag.observe`: flyouts and dialogs (Brushes, Shapes,
                             Size, Edit colours, Text) appear as states and edges
    Sub-RAG 3 (procedures)   each workflow (a flowchart layout, a lightboard page, a trace, a colouring pass with its custom RGB values, brushes and sizes) is a procedure with grounded steps
    Sub-RAG 4 (fast paths)   the same workflow as a parameterised macro (kind "script", sandbox "uia_macro", params schema for RGB / brush / size)
    training pairs           each verified UIA action is written as a v2 pair (full picture + dense-strip zoom crops + control names) to the training JSONL, for the next QLoRA pass

`PaintLogger.hook` is the callback `canvas_live.LivePainter` calls after every UI Automation action.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

APP = "ms_paint"


def uia_snapshot(controls: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """A screen as the state key reads a UIA tree: nodes with a type and a name (the structural controls identify the state)."""
    return {"nodes": [{"name": c.get("name", ""), "ctype": str(c.get("type", "")).replace("Control", "").lower(), "offscreen": False} for c in controls], "role": "main"}


def _command(app_key: str, name: str) -> str:
    from core_organs.rag.lexicon import command_id
    return command_id(app_key, name)


class PaintLogger:
    """Collects the hook events of a LivePainter and writes them to the RAG and the dataset."""

    def __init__(self, rag: Any, jsonl: str = "", root: str = "", som_fn: Optional[Callable[..., Dict[str, Any]]] = None, app_key: str = APP, run_id: str = "", write_pairs: bool = True):
        self.rag, self.app_key = rag, app_key
        self.run_id = run_id or f"artist-{int(time.time())}"
        self.som_fn = som_fn
        self.root, self.jsonl, self.write_pairs = root, jsonl, write_pairs
        self.events: List[Dict[str, Any]] = []
        self.counts = {"icons": 0, "edges": 0, "pairs": 0}

    # ---------------------------------------------------------------- the hook
    def hook(self, ev: Dict[str, Any]) -> None:
        self.events.append({k: ev[k] for k in ("kind", "name", "type", "box")})
        self._icon(ev)
        self._graph(ev)
        if self.write_pairs and self.som_fn is not None and self.jsonl:
            self._pair(ev)

    def _icon(self, ev: Dict[str, Any]) -> None:
        if self.rag is None:
            return
        try:
            x, y, w, h = ev["box"]
            crop = ev["pre"].crop((int(x), int(y), int(x + w), int(y + h)))
            if crop.size[0] >= 8 and crop.size[1] >= 8 and self.rag.icons is not None and self.rag.icons.learn(ev["name"], "uia", crop=crop, app_key=self.app_key):
                self.counts["icons"] += 1
        except Exception:
            pass

    def _graph(self, ev: Dict[str, Any]) -> None:
        if self.rag is None:
            return
        try:
            from core_organs.rag import Outcome, PlanStep
            pre_s, post_s = uia_snapshot(ev["controls"]), None
            from core_organs.harvest.local_recorder import changed
            moved = bool(changed(ev["pre"], ev["post"])[0])
            src = self.rag.localize(self.app_key, pre_s).state_id
            cid = _command(self.app_key, ev["name"])
            self.rag.lex.add_command(self.app_key, ev["name"], source="executor", trust="learned")
            post_controls = ev.get("post_controls")
            post_snap = uia_snapshot(post_controls) if post_controls else pre_s
            self.rag.observe(Outcome(self.run_id, self.app_key, PlanStep(cid, "uia_invoke", {"label": ev["name"], "kind": ev["kind"]}, None, "", 0.5, "allow"), src_state=src, observed_snapshot=post_snap,
                                     ok=moved, effect="the screen changed" if moved else "no_effect", latency_ms=0.0, failure_code="" if moved else "no_effect"))
            self.counts["edges"] += 1
        except Exception:
            pass

    def _pair(self, ev: Dict[str, Any]) -> None:
        """One verified UIA action -> one v2 training pair: pre picture (+ strips), element list, control names, the goal and the click on the element inside the control."""
        try:
            from core_organs.harvest import local_recorder as LR, prompt_v2 as P2, video_explain as VE
            som = self.som_fn(ev["pre"])
            gt = LR.element_at(som, ev["box"])
            if gt is None:
                return
            goal = LR.goal_for(ev["name"], ev["type"])
            names = P2.name_elements(som["elements"], ev["controls"])
            os.makedirs(os.path.join(self.root, "frames", "artist"), exist_ok=True)
            stamp = hashlib.sha1(f"{ev['name']}{time.time()}".encode()).hexdigest()[:10]
            full = os.path.join(self.root, "frames", "artist", f"{stamp}_pre.jpg")
            ev["pre"].save(full, "JPEG", quality=90)
            content, info = P2.user_content(ev["pre"], som, self.app_key, goal, names=names, image_ref=os.path.relpath(full, self.root).replace("\\", "/"))
            crops = P2.strip_crops(ev["pre"], info["strips"])
            refs = []
            for i, c in enumerate(crops):
                p = os.path.join(self.root, "frames", "artist", f"{stamp}_strip{i}.jpg")
                c.save(p, "JPEG", quality=90)
                refs.append(os.path.relpath(p, self.root).replace("\\", "/"))
            content, info = P2.user_content(ev["pre"], som, self.app_key, goal, names=names, image_ref=os.path.relpath(full, self.root).replace("\\", "/"), crop_refs=refs)
            action = [{"step": 1, "action": "click", "target_id": gt["id"], "hotkey": None, "text": None, "verify_expectation": "the screen changes"}]
            row = {"messages": [{"role": "system", "content": [{"type": "text", "text": VE._SYSTEM_HINT}]}, {"role": "user", "content": content},
                                {"role": "assistant", "content": [{"type": "text", "text": json.dumps(action, ensure_ascii=False)}]}],
                   "meta": {"pair_id": hashlib.sha1(f"{self.app_key}|{goal}|{stamp}".encode()).hexdigest()[:16], "app_key": self.app_key, "video_id": "local_artist", "t": 0.0,
                            "pre": os.path.relpath(full, self.root).replace("\\", "/"), "post": "", "grounded": True, "ui_frames": True, "source": "local_uia", "source_ref": f"artist@{stamp}",
                            "uia_name": ev["name"], "uia_type": ev["type"], "prompt_version": 2, "strips": info["n_crops"], "names": info["n_names"], "som_elements": len(som["elements"]), "workflow": ev["kind"]}}
            with open(self.jsonl, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.counts["pairs"] += 1
        except Exception:
            pass


# ------------------------------------------------------------------------------------------------------------------------------------ workflows -> procedures + macros
def log_workflow(rag: Any, name: str, goal: str, steps: Sequence[Dict[str, Any]], params: Optional[Dict[str, Any]] = None, source_ref: str = "canvas_artist", verified: bool = True,
                 app_key: str = APP) -> Dict[str, int]:
    """One artistic / teaching workflow -> Sub-RAG 3 (a procedure with its steps) and Sub-RAG 4 (a parameterised UIA macro). `steps` are {text, target?, route_hint?, params?}."""
    n = {"procedures": 0, "fast_paths": 0}
    r = rag.proc.ingest_procedure(app_key, goal, steps, source_ref, trust="verified" if verified else "learned")
    n["procedures"] += r.inserted + r.updated
    schema = {k: {"type": type(v).__name__, "example": v} for k, v in (params or {}).items()}
    macro = {"app_key": app_key, "kind": "script", "payload": json.dumps({"workflow": name, "steps": [{k: s[k] for k in ("text", "target", "route_hint") if k in s} for s in steps]}, sort_keys=True),
             "task_pattern": goal[:160], "command_id": _command(app_key, name), "source": "skill" if verified else "probe", "trust": "verified" if verified else "learned", "verified": bool(verified),
             "sandbox": "uia_macro", "params_schema_json": schema}
    r2 = rag.ingest("fast", [macro])
    n["fast_paths"] += r2.inserted + r2.updated
    return n


def colour_recipe_steps(info: Dict[str, Any], ops: Sequence[Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """The colouring pass as grounded steps: Edit colours with the exact RGB, Brushes -> the brush, Size -> the size, Fill with colour / strokes, per region and band."""
    steps: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {}
    for op in ops:
        a = op.args
        if op.kind == "colour":
            steps.append({"text": f"Open Edit colours and enter R {a['rgb'][0]} G {a['rgb'][1]} B {a['rgb'][2]} for the {a.get('role', 'base')} tone", "target": "Edit colours", "route_hint": "uia_invoke", "params": {"rgb": list(a["rgb"])}})
            params.setdefault("rgb", list(a["rgb"]))
        elif op.kind == "brush":
            steps.append({"text": f"Open Brushes and choose {a['name']}, then set the Size to {a['size']}", "target": "Brushes", "route_hint": "uia_invoke", "params": {"brush": a["name"], "size": a["size"]}})
            params.setdefault("brush", a["name"])
            params.setdefault("size", a["size"])
        elif op.kind == "fill":
            steps.append({"text": "Choose Fill with colour and click inside the closed outline", "target": "Fill", "route_hint": "control_click"})
    dedup, seen = [], set()
    for s in steps:
        k = s["text"]
        if k not in seen:
            seen.add(k)
            dedup.append(s)
    return dedup[:40], params


def layout_recipe_steps(kind: str, zones: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The lightboard layout as steps (zones as fractions of the canvas, so the recipe is size-independent)."""
    return [{"text": "Show the toolbar and choose Pencil", "target": "Pencil", "route_hint": "uia_invoke"},
            {"text": "Find the white canvas and split it into a header, a left and a right call-out lane, a core zone and a footer", "route_hint": "layout"},
            {"text": "Trace the artwork into the core zone, keeping its aspect ratio", "route_hint": "trace"},
            {"text": "For each label: draw a box in its lane and a leader from the box to a point ON the part it names; leaders must not cross", "route_hint": "stroke"},
            {"text": "Write the numbered summary in the footer and frame the core zone", "route_hint": "stroke"}]
