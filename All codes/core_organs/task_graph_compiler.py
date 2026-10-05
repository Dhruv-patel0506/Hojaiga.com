"""
task_graph_compiler.py — Keep long-horizon planning OUT of the 7B ReAct loop.

The judge is allowed to pick among numbered on-screen elements. It is not
allowed to invent a 100-step Blender chair plan. This compiler is the
structural fix:

    user command
        -> resolve app (organ_40 catalog, not a keyword list)
        -> classify intent (construct / operate / web)
        -> pick mode: native_runtime > recalled skill recipe > desktop_loop
        -> emit ordered micro-goals WITH postconditions

CrewAI execute_task runs this graph directly when skip_react is True.
"""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("hojaiga.task_graph_compiler")

CONSTRUCT_CUES = (
    "3d", "three d", "blender", "from scratch", "model a", "model me",
    "cad", "mesh", "low-poly", "low poly", "sculpt",
)
CANVAS_ARCHETYPES = {"3d_suite", "raster_editor"}
REACT_KEEP = ("calculator", "calc ", " paint", "mspaint", "teaching void", "whiteboard")


@dataclass
class GraphStep:
    goal: str
    expect: Dict[str, Any] = field(default_factory=dict)
    kind: str = "ui"  # ui | native | launch | verify

    def as_dict(self) -> dict:
        return {"goal": self.goal, "expect": dict(self.expect), "kind": self.kind}


@dataclass
class CompiledTaskGraph:
    command: str
    app_hint: str = ""
    archetype: str = "generic_win32"
    mode: str = "react_fallback"  # native_runtime | desktop_loop | react_fallback
    skip_react: bool = False
    vision_tier: int = 2
    object_kind: str = ""
    save_path: str = ""
    launcher_path: str = ""
    steps: List[GraphStep] = field(default_factory=list)
    reason: str = ""
    recipe_prior: str = ""

    def as_dict(self) -> dict:
        return {
            "command": self.command, "app_hint": self.app_hint,
            "archetype": self.archetype, "mode": self.mode,
            "skip_react": self.skip_react, "vision_tier": self.vision_tier,
            "object_kind": self.object_kind, "save_path": self.save_path,
            "launcher_path": self.launcher_path, "reason": self.reason,
            "recipe_prior": (self.recipe_prior or "")[:240],
            "steps": [s.as_dict() for s in self.steps],
        }

    def micro_goals(self) -> List[str]:
        return [s.goal for s in self.steps if s.kind in ("ui", "verify")]

    def expect_map(self) -> Dict[int, Dict[str, Any]]:
        out: Dict[int, Dict[str, Any]] = {}
        ui_i = 0
        for s in self.steps:
            if s.kind in ("ui", "verify"):
                if s.expect:
                    out[ui_i] = s.expect
                ui_i += 1
        return out


def _is_construct(command: str) -> bool:
    t = (command or "").lower()
    return any(c in t for c in CONSTRUCT_CUES)


def _keep_react(command: str) -> bool:
    t = f" {(command or '').lower()} "
    return any(k in t for k in REACT_KEEP)


def _resolve_app(command: str) -> Dict[str, Any]:
    try:
        from core_organs.organ_40_app_launcher import plan_task_app
        return plan_task_app(command) or {}
    except Exception as exc:
        logger.debug("[graph] plan_task_app unavailable: %s", exc)
        return {}


def _pick_3d_suite_from_catalog() -> Dict[str, str]:
    """If the user said 'make a 3D chair' without naming the app, use an
    installed 3D suite from the host catalog. Prefer Blender when present."""
    try:
        from core_organs.organ_40_app_launcher import AppCatalog
        from core_organs.organ_47_app_intelligence import classify_archetype
        cat = AppCatalog()
        cat.ensure_scanned()
        import sqlite3
        rows = []
        with sqlite3.connect(cat.db) as conn:
            rows = list(conn.execute("SELECT name, launcher_path FROM app_catalog"))
        blender = None
        other = None
        for name, path in rows:
            family = classify_archetype(name or "", path or "")
            if family != "3d_suite":
                continue
            rec = {"app_hint": name, "launcher_path": path or ""}
            if "blender" in (name or "").lower():
                blender = rec
                break
            other = other or rec
        return blender or other or {}
    except Exception as exc:
        logger.debug("[graph] 3d catalog probe failed: %s", exc)
        return {}


def compile_user_task(command: str) -> CompiledTaskGraph:
    graph = CompiledTaskGraph(command=command or "")
    plan = _resolve_app(command)
    action = (plan.get("action") or "")
    app = (plan.get("target_app") or "").strip()
    launcher = plan.get("launcher_path") or ""

    try:
        from core_organs.organ_47_app_intelligence import classify_archetype
        family = classify_archetype(app, launcher) if app else "generic_win32"
    except Exception:
        family = "generic_win32"

    construct = _is_construct(command)
    if construct and (not app or action in ("browser_web", "not_found", "none")):
        picked = _pick_3d_suite_from_catalog()
        if picked:
            app = picked["app_hint"]
            launcher = picked.get("launcher_path") or launcher
            try:
                from core_organs.organ_47_app_intelligence import classify_archetype
                family = classify_archetype(app, launcher)
            except Exception:
                family = "3d_suite"
            graph.reason = "inferred 3d suite from construct intent + host catalog"
        else:
            graph.reason = "construct intent but no 3d suite installed"
            graph.mode = "react_fallback"
            return graph

    graph.app_hint = app
    graph.archetype = family
    graph.launcher_path = launcher or ""
    graph.vision_tier = 4 if family in CANVAS_ARCHETYPES else 2

    if _keep_react(command) or not app:
        graph.mode = "react_fallback"
        graph.reason = graph.reason or "specialized react path or no desktop app"
        return graph

    recipe = ""
    try:
        from core_organs.desktop_grounding import DesktopAutonomyLoop
        recipe = DesktopAutonomyLoop.recall_recipe(command, app) or ""
        graph.recipe_prior = recipe
    except Exception:
        recipe = ""

    if construct and family == "3d_suite":
        from core_organs.native_app_runtime import infer_object_kind, infer_save_path
        kind = infer_object_kind(command)
        save_path = infer_save_path(command, kind)
        graph.object_kind = kind
        graph.save_path = save_path
        graph.mode = "native_runtime"
        graph.skip_react = True
        graph.steps = [
            GraphStep(f"launch {app}", kind="launch"),
            GraphStep(f"construct {kind} via native api", kind="native",
                      expect={"file_created": save_path, "region_changed": True}),
            GraphStep(f"verify {os.path.basename(save_path)} exists", kind="verify",
                      expect={"file_created": save_path}),
        ]
        # UI fallback micro-goals if native cannot run on this host
        graph.steps += [
            GraphStep("add mesh primitive", {"region_changed": True}),
            GraphStep("save project", {"file_created": save_path}),
        ]
        graph.reason = graph.reason or (
            f"construct {kind} in {app}: native bpy first, UI loop fallback")
        return graph

    # Recalled recipe becomes the plan prior (deterministic split).
    if recipe:
        parts = [p.strip() for p in re.split(r"\s+THEN\s+", recipe) if p.strip()]
        ui_goals = []
        for p in parts:
            m = re.search(r"to achieve:\s*(.+)$", p, re.I)
            ui_goals.append((m.group(1).strip() if m else p)[:80])
        if ui_goals:
            graph.mode = "desktop_loop"
            graph.skip_react = True
            graph.steps = [GraphStep(g) for g in ui_goals[:16]]
            graph.reason = f"replayed {len(graph.steps)} learned recipe steps"
            return graph

    graph.mode = "desktop_loop"
    graph.skip_react = True
    graph.steps = _generic_operate_steps(command, app, family)
    graph.reason = graph.reason or f"desktop_loop on {app} [{family}]"
    return graph


def _generic_operate_steps(command: str, app: str, family: str) -> List[GraphStep]:
    t = (command or "").lower()
    steps: List[GraphStep] = [GraphStep(f"make {app} ready to use")]
    if any(k in t for k in ("type", "write", "jot", "note", "paste")):
        payload = _extract_typed_payload(command)
        if payload:
            steps.append(GraphStep(f"type {payload}", {"region_changed": True}))
    if any(k in t for k in ("save as", "save", "export")):
        steps.append(GraphStep("save project"))
    if len(steps) == 1:
        steps.append(GraphStep(command.strip()[:120] or f"complete the task in {app}",
                               {"region_changed": True}))
    return steps


def _extract_typed_payload(command: str) -> str:
    m = re.search(
        r"(?:type|write|jot(?:\s+down)?|note)\s+(?:that\s+)?(.+)$",
        command or "", re.I)
    if not m:
        return ""
    return m.group(1).strip().strip("'\"")[:200]


def execute_compiled_graph(graph: CompiledTaskGraph, task_id: str = "",
                           capsule_cb: Optional[Callable[[str, str], None]] = None,
                           cursor_cb: Optional[Callable[[float, float], None]] = None
                           ) -> Dict[str, Any]:
    """Run native constructor and/or the desktop autonomy loop. No ReAct."""
    cap = capsule_cb
    if cap is None:
        def cap(state: str, text: str):
            logger.info("[GRAPH-CAPSULE] %s: %s", state, text)
            try:
                from core_organs.visual_cursor import get_cursor
                if state in ("working", "input_needed"):
                    get_cursor().set_label(text[:28], state)
            except Exception:
                pass

    try:
        from core_organs.visual_cursor import get_cursor
        get_cursor().show()
    except Exception:
        pass

    cap("working", f"{graph.app_hint}: {graph.mode}")
    native_note = ""
    native_ok = False

    if graph.mode == "native_runtime":
        try:
            from core_organs.native_app_runtime import run_native_construct
            nr = run_native_construct(
                graph.app_hint, graph.command,
                launcher_path=graph.launcher_path,
                object_kind=graph.object_kind,
                save_path=graph.save_path,
                capsule_cb=cap)
            native_ok = bool(nr.ok)
            native_note = f"{nr.method}: {nr.evidence}"
            if native_ok:
                try:
                    from core_organs.desktop_grounding import DesktopAutonomyLoop, StepTrace
                    loop = DesktopAutonomyLoop(session_id=task_id or None,
                                               capsule_cb=cap, cursor_cb=cursor_cb)
                    loop.trace.append(StepTrace(
                        goal=f"construct {graph.object_kind}",
                        element="native-api", verb="native",
                        verdict="PASS", method=nr.method, evidence=nr.evidence))
                    loop.distill_recipe(graph.command, graph.app_hint)
                except Exception:
                    pass
                cap("working", f"Done: {os.path.basename(graph.save_path)}")
                return {
                    "task_id": task_id,
                    "status": "SUCCESS",
                    "crew_output": (
                        f"NATIVE CONSTRUCT [{graph.app_hint}] built "
                        f"{graph.object_kind} and verified {graph.save_path}. "
                        f"{native_note}"
                    ),
                    "attempts": 1,
                    "failure_history": None,
                    "session_actions": [
                        f"NATIVE_{graph.archetype}:{graph.object_kind}"
                    ],
                    "engine": "task_graph",
                    "graph": graph.as_dict(),
                    "native": nr.as_dict(),
                }
            logger.warning("[graph] native path failed, falling back to UI loop: %s",
                           native_note)
        except Exception as exc:
            native_note = f"native-exception: {exc}"
            logger.exception("[graph] native construct crashed")

    # UI perceive->act->verify loop (canvas apps escalate to OmniParser)
    try:
        from core_organs.desktop_grounding import get_loop
        from core_organs.organ_40_app_launcher import resolve_and_launch
        loop = get_loop(capsule_cb=cap, cursor_cb=cursor_cb)
        if graph.app_hint and not loop.grounding.find_window(graph.app_hint):
            cap("working", f"Launching {graph.app_hint}")
            resolve_and_launch(graph.app_hint)
            time_sleep_quiet(1.5)
        goals = graph.micro_goals() or [graph.command]
        result = loop.run(
            goals, graph.app_hint,
            max_steps_per_goal=5,
            expect_map=graph.expect_map(),
            max_tier=graph.vision_tier)
        if result.get("completed"):
            try:
                loop.distill_recipe(graph.command, graph.app_hint)
            except Exception:
                pass
        status = "SUCCESS" if result.get("completed") else "FAILED"
        if result.get("awaiting_human"):
            status = "NEEDS_INPUT"
        lines = []
        for t in result.get("trace", [])[-12:]:
            lines.append(f"  {t.get('verb')} '{str(t.get('element',''))[:28]}' -> {t.get('verdict')}")
        return {
            "task_id": task_id,
            "status": status,
            "crew_output": (
                f"TASK GRAPH [{graph.app_hint}] {status}. native={native_note or 'n/a'}\n"
                + "\n".join(lines)
            ),
            "attempts": 1,
            "failure_history": None if status == "SUCCESS" else native_note,
            "session_actions": [f"GRAPH_{graph.mode}:{graph.app_hint}"],
            "engine": "task_graph",
            "graph": graph.as_dict(),
            "loop": {k: result.get(k) for k in ("completed", "steps", "awaiting_human", "blocked_at_goal")},
        }
    except Exception as exc:
        logger.exception("[graph] desktop loop fallback failed")
        return {
            "task_id": task_id,
            "status": "FAILED",
            "crew_output": f"Task graph could not execute: {exc}",
            "attempts": 1,
            "failure_history": str(exc),
            "session_actions": [],
            "engine": "task_graph",
            "graph": graph.as_dict(),
        }


def time_sleep_quiet(seconds: float) -> None:
    import time
    time.sleep(seconds)
