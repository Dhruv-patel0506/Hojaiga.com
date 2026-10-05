"""Topic-neutral scene protocol and local compiler for the Omnitutor Void.

This module deliberately knows no school subject.  A model declares *what* it
wants to render as a compact scene; this module validates and compiles it to
the legacy overlay drawing primitives.  It is also safe to use without a model
for image/video-frame tracing.
"""
from __future__ import annotations

import ast
import json
import math
import time
from collections import deque
import statistics
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # Optional: tracing is unavailable without these.
    cv2 = None
    np = None


SCENE_VERSION = "2.0"
ACTION_KINDS = frozenset({"stroke", "polyline", "bezier", "arrow", "shape", "text", "highlight", "image", "group", "layer", "function_plot", "trace"})
DEFAULT_STYLE = {"color": "#38bdf8", "width": 3, "opacity": 1.0, "z_order": 0}


class SceneValidationError(ValueError):
    """The model requested an unsafe or incomplete scene."""


@dataclass(frozen=True)
class SceneAction:
    id: str
    kind: str
    data: dict[str, Any]
    segment_id: str | None = None
    layer: int = 0
    start_ms: int = 0
    duration_ms: int = 350
    style: dict[str, Any] = field(default_factory=dict)
    z_order: int = 0
    source_ref: str | None = None
    undo_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NarrationSegment:
    id: str
    text: str
    annotation_ids: tuple[str, ...] = ()
    allow_unannotated: bool = False


@dataclass(frozen=True)
class ScenePacket:
    actions: tuple[SceneAction, ...]
    narration: tuple[NarrationSegment, ...] = ()
    title: str = ""
    version: str = SCENE_VERSION


@dataclass(frozen=True)
class CompiledScene:
    drawings: tuple[dict[str, Any], ...]
    narration: tuple[NarrationSegment, ...]
    action_schedule: dict[str, tuple[int, int]]


@dataclass(frozen=True)
class SceneEvent:
    timestamp: float
    event_type: str
    details: dict[str, Any]
    action_id: str | None = None
    segment_id: str | None = None
    latency_ms: float | None = None


class SceneEventLog:
    """Event log for scene actions, rejections, failures, and latency measurements."""
    
    def __init__(self, max_events: int = 1000):
        self.events: deque[SceneEvent] = deque(maxlen=max_events)
        self.start_time = time.time()
    
    def log(self, event_type: str, details: dict[str, Any], action_id: str | None = None, 
            segment_id: str | None = None, latency_ms: float | None = None) -> None:
        """Log a scene event with timestamp and optional identifiers."""
        event = SceneEvent(
            timestamp=time.time() - self.start_time,
            event_type=event_type,
            details=details,
            action_id=action_id,
            segment_id=segment_id,
            latency_ms=latency_ms
        )
        self.events.append(event)
    
    def get_recent(self, event_type: str | None = None, limit: int = 10) -> list[SceneEvent]:
        """Get recent events, optionally filtered by type."""
        if event_type:
            return [e for e in self.events if e.event_type == event_type][-limit:]
        return list(self.events)[-limit:]
    
    def get_latency_stats(self) -> dict[str, float]:
        """Calculate latency statistics from logged events."""
        latencies = [e.latency_ms for e in self.events if e.latency_ms is not None]
        if not latencies:
            return {"count": 0, "avg_ms": 0.0, "max_ms": 0.0, "min_ms": 0.0}
        return {
            "count": len(latencies),
            "avg_ms": statistics.mean(latencies),
            "max_ms": max(latencies),
            "min_ms": min(latencies),
            "p95_ms": statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        }
    
    def clear(self) -> None:
        """Clear all events and reset start time."""
        self.events.clear()
        self.start_time = time.time()


def _finite(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise SceneValidationError(f"{field_name} must be a number") from error
    if not math.isfinite(number):
        raise SceneValidationError(f"{field_name} must be finite")
    return number


def _normal(value: Any, field_name: str) -> float:
    number = _finite(value, field_name)
    if not -0.25 <= number <= 1.25:
        raise SceneValidationError(f"{field_name} must be a normalized coordinate")
    return number


class SceneValidator:
    """Strictly validates a small, declarative scene contract.

    Coordinates are normalized to the current canvas (0..1).  That prevents a
    model response from depending on a hard-coded monitor resolution.
    """

    max_actions = 80
    max_points_per_stroke = 1200

    def validate(self, raw: Any) -> ScenePacket:
        if not isinstance(raw, dict):
            raise SceneValidationError("scene response must be an object")
        raw_actions = raw.get("scene", raw.get("actions", []))
        if not isinstance(raw_actions, list):
            raise SceneValidationError("scene must be a list")
        if len(raw_actions) > self.max_actions:
            raise SceneValidationError("scene has too many actions")
        actions = tuple(self._action(item, index) for index, item in enumerate(raw_actions))
        raw_segments = raw.get("narration_segments", [])
        if not isinstance(raw_segments, list):
            raise SceneValidationError("narration_segments must be a list")
        segments = tuple(self._segment(item, index) for index, item in enumerate(raw_segments))
        action_ids = {action.id for action in actions}
        segment_ids = {segment.id for segment in segments}
        for action in actions:
            if action.segment_id and action.segment_id not in segment_ids:
                raise SceneValidationError(f"action {action.id} names an unknown narration segment")
        for segment in segments:
            if not segment.allow_unannotated and not segment.annotation_ids:
                raise SceneValidationError(f"segment {segment.id} has no linked annotation")
            unknown = set(segment.annotation_ids) - action_ids
            if unknown:
                raise SceneValidationError(f"segment {segment.id} names missing actions: {sorted(unknown)}")
        return ScenePacket(actions, segments, str(raw.get("title", ""))[:160])

    def validate_best_effort(self, raw: Any) -> tuple[ScenePacket, list[str]]:
        """Preserve valid model actions when another action is malformed.

        This remains strict per action: malformed geometry is never rendered.
        Only the broken action (and narration segments pointing to it) is removed.
        """
        if not isinstance(raw, dict):
            raise SceneValidationError("scene response must be an object")
        raw_actions = raw.get("scene", raw.get("actions", []))
        if not isinstance(raw_actions, list):
            raise SceneValidationError("scene must be a list")
        warnings: list[str] = []
        clean_actions: list[dict[str, Any]] = []
        for index, item in enumerate(raw_actions[:self.max_actions]):
            try:
                parsed = self._action(item, index)
            except SceneValidationError as error:
                warnings.append(f"action {index + 1}: {error}")
                continue
            clean_item = dict(item)
            clean_item["id"] = parsed.id
            clean_actions.append(clean_item)
        if len(raw_actions) > self.max_actions:
            warnings.append(f"discarded actions after {self.max_actions}")
        if not clean_actions:
            raise SceneValidationError("scene contains no valid actions")

        action_ids = {str(item["id"]) for item in clean_actions}
        clean_segments: list[dict[str, Any]] = []
        raw_segments = raw.get("narration_segments", [])
        if isinstance(raw_segments, list):
            for index, item in enumerate(raw_segments):
                try:
                    parsed = self._segment(item, index)
                except SceneValidationError as error:
                    warnings.append(f"narration segment {index + 1}: {error}")
                    continue
                if not parsed.allow_unannotated and (not parsed.annotation_ids or not set(parsed.annotation_ids).issubset(action_ids)):
                    warnings.append(f"narration segment {parsed.id}: missing valid annotations")
                    continue
                clean_item = dict(item)
                clean_item["id"] = parsed.id
                clean_segments.append(clean_item)
        elif raw_segments:
            warnings.append("discarded malformed narration_segments")

        segment_ids = {str(item["id"]) for item in clean_segments}
        for item in clean_actions:
            if item.get("segment_id") and str(item["segment_id"]) not in segment_ids:
                warnings.append(f"action {item['id']}: detached unknown narration segment")
                item.pop("segment_id", None)
        cleaned = dict(raw)
        cleaned["scene"] = clean_actions
        cleaned["narration_segments"] = clean_segments
        return self.validate(cleaned), warnings

    def _action(self, item: Any, index: int) -> SceneAction:
        if not isinstance(item, dict):
            raise SceneValidationError("each scene action must be an object")
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in ACTION_KINDS:
            raise SceneValidationError(f"unsupported scene action: {kind or 'missing kind'}")
        data = item.get("data", {})
        if not isinstance(data, dict):
            raise SceneValidationError("action data must be an object")
        self._validate_geometry(kind, data)
        style = dict(DEFAULT_STYLE)
        if isinstance(item.get("style"), dict):
            style.update({key: value for key, value in item["style"].items() if key in {"color", "width", "opacity", "dash"}})
        style["width"] = max(1.0, min(24.0, _finite(style.get("width", 3), "style.width")))
        style["opacity"] = max(0.05, min(1.0, _finite(style.get("opacity", 1), "style.opacity")))
        action_id = str(item.get("id") or f"a{index + 1}")[:64]
        return SceneAction(
            id=action_id,
            kind=kind,
            data=data,
            segment_id=str(item["segment_id"])[:64] if item.get("segment_id") else None,
            layer=max(-10, min(10, int(item.get("layer", 0)))),
            start_ms=max(0, min(120000, int(item.get("start_ms", 0)))),
            duration_ms=max(0, min(30000, int(item.get("duration_ms", 350)))),
            style=style,
        )

    def _segment(self, item: Any, index: int) -> NarrationSegment:
        if not isinstance(item, dict):
            raise SceneValidationError("each narration segment must be an object")
        text = str(item.get("text", "")).strip()
        if not text:
            raise SceneValidationError("narration segment text is required")
        links = item.get("annotation_ids", [])
        if not isinstance(links, list):
            raise SceneValidationError("annotation_ids must be a list")
        return NarrationSegment(str(item.get("id") or f"s{index + 1}")[:64], text[:800], tuple(str(link)[:64] for link in links[:40]), bool(item.get("allow_unannotated", False)))

    def _validate_geometry(self, kind: str, data: dict[str, Any]) -> None:
        if kind in {"stroke", "trace", "polyline"}:
            points = data.get("points")
            if not isinstance(points, list) or not 2 <= len(points) <= self.max_points_per_stroke:
                raise SceneValidationError(f"{kind} requires 2..1200 points")
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    raise SceneValidationError("every point must be [x, y]")
                _normal(point[0], "point.x"); _normal(point[1], "point.y")
        elif kind == "bezier":
            # Cubic bezier: start, control1, control2, end
            points = data.get("points")
            if not isinstance(points, list) or len(points) != 4:
                raise SceneValidationError("bezier requires exactly 4 points (start, control1, control2, end)")
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    raise SceneValidationError("every bezier point must be [x, y]")
                _normal(point[0], "point.x"); _normal(point[1], "point.y")
        elif kind == "arrow":
            for key in ("x1", "y1", "x2", "y2"):
                _normal(data.get(key), key)
        elif kind in {"shape", "highlight"}:
            for key in ("x", "y", "width", "height"):
                _normal(data.get(key), key)
            if kind == "shape" and str(data.get("shape", "rectangle")) not in {"rectangle", "ellipse", "circle", "triangle", "diamond", "polygon", "star", "hexagon"}:
                raise SceneValidationError("unsupported shape")
        elif kind == "text":
            _normal(data.get("x"), "x"); _normal(data.get("y"), "y")
            if not str(data.get("text", "")).strip():
                raise SceneValidationError("text action needs text")
        elif kind == "image":
            _normal(data.get("x"), "x"); _normal(data.get("y"), "y")
            _normal(data.get("width"), "width"); _normal(data.get("height"), "height")
            if not str(data.get("src", "")).strip():
                raise SceneValidationError("image action needs src (data URI or path)")
        elif kind == "group":
            children = data.get("children")
            if not isinstance(children, list) or not children:
                raise SceneValidationError("group requires non-empty children list")
            # Children will be validated recursively
        elif kind == "layer":
            layer_id = data.get("layer_id")
            if not str(layer_id).strip():
                raise SceneValidationError("layer action needs layer_id")
            _normal(data.get("opacity", 1.0), "opacity")
        elif kind == "function_plot":
            if not str(data.get("expression", "")).strip():
                raise SceneValidationError("function_plot needs expression")
            domain = data.get("domain", [-10, 10])
            if not isinstance(domain, list) or len(domain) != 2 or _finite(domain[0], "domain[0]") >= _finite(domain[1], "domain[1]"):
                raise SceneValidationError("function_plot domain must increase")
            panel = data.get("panel")
            if panel is not None:
                if not isinstance(panel, list) or len(panel) != 4:
                    raise SceneValidationError("function_plot panel must be [x, y, width, height]")
                px, py, pw, ph = (_normal(value, f"panel[{index}]") for index, value in enumerate(panel))
                if pw <= 0 or ph <= 0 or px + pw > 1.001 or py + ph > 1.001:
                    raise SceneValidationError("function_plot panel must fit the normalized canvas")


class SafeExpression:
    """Restricted numeric expression evaluator for function plots, never SymPy eval."""
    _functions: dict[str, Callable[..., float]] = {
        "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log,
        "ln": math.log, "exp": math.exp, "sqrt": math.sqrt, "abs": abs,
        "cot": lambda x: 1.0 / math.tan(x), "sec": lambda x: 1.0 / math.cos(x),
        "csc": lambda x: 1.0 / math.sin(x),
    }
    _names = {"x", "pi", "e"}
    _nodes = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.Constant, ast.Name, ast.Call, ast.Load)

    def __init__(self, expression: str) -> None:
        normalized = expression.strip().replace("^", "**")
        try:
            tree = ast.parse(normalized, mode="eval")
        except SyntaxError as error:
            raise SceneValidationError("function expression is invalid") from error
        for node in ast.walk(tree):
            if not isinstance(node, self._nodes):
                raise SceneValidationError("function expression contains a forbidden operation")
            if isinstance(node, ast.Name) and node.id not in self._names and node.id not in self._functions:
                raise SceneValidationError(f"unknown function symbol: {node.id}")
            if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in self._functions):
                raise SceneValidationError("only supported math functions may be called")
        self._code = compile(tree, "<scene-expression>", "eval")

    def evaluate(self, x: float) -> float:
        values = {"x": x, "pi": math.pi, "e": math.e, **self._functions}
        value = eval(self._code, {"__builtins__": {}}, values)  # AST is restricted above.
        return float(value)


class SceneCompiler:
    """Compiles topic-neutral actions into the overlay's current drawing format."""
    
    def __init__(self, event_log: SceneEventLog | None = None):
        self.event_log = event_log or SceneEventLog()
    
    def compile(self, packet: ScenePacket, viewport: tuple[int, int]) -> CompiledScene:
        start_time = time.time()
        width, height = max(1, int(viewport[0])), max(1, int(viewport[1]))
        drawings: list[dict[str, Any]] = []
        schedule: dict[str, tuple[int, int]] = {}
        
        for action in sorted(packet.actions, key=lambda entry: (entry.layer, entry.start_ms, entry.z_order)):
            schedule[action.id] = (action.start_ms, action.duration_ms)
            try:
                compiled = self._compile_action(action, width, height)
                drawings.extend(compiled)
                self.event_log.log("action_compiled", {"kind": action.kind, "drawing_count": len(compiled)}, 
                                 action_id=action.id, latency_ms=(time.time() - start_time) * 1000)
            except Exception as error:
                self.event_log.log("action_failed", {"kind": action.kind, "error": str(error)}, 
                                 action_id=action.id)
        
        # Renderer validator: ensure visible marks exist
        if not drawings:
            self.event_log.log("render_validation_failed", {"reason": "no_visible_marks"})
            raise SceneValidationError("scene produced no visible marks - cannot complete visual task")
        
        self.event_log.log("scene_compiled", {"action_count": len(packet.actions), "drawing_count": len(drawings)},
                         latency_ms=(time.time() - start_time) * 1000)
        
        return CompiledScene(tuple(drawings), packet.narration, schedule)

    def _p(self, value: float, extent: int) -> float:
        return round(value * extent, 2)

    def _compile_action(self, action: SceneAction, width: int, height: int) -> list[dict[str, Any]]:
        d, style = action.data, action.style
        color = str(style["color"])
        line_width = float(style.get("width", 3))
        opacity = float(style.get("opacity", 1.0))
        z_order = int(action.z_order)
        
        # Base metadata for all drawings
        base_meta = {
            "_scene_action": action.id,
            "_segment_id": action.segment_id,
            "_start_ms": action.start_ms,
            "_duration_ms": action.duration_ms,
            "_z_order": z_order,
            "_opacity": opacity,
            "_source_ref": action.source_ref,
            "_undo_metadata": action.undo_metadata
        }
        
        if action.kind in {"stroke", "trace", "polyline"}:
            points = [[self._p(x, width), self._p(y, height)] for x, y in d["points"]]
            return [{
                "type": "freehand" if action.kind in {"stroke", "trace"} else "polyline",
                "points": points,
                "color": color,
                "width": line_width,
                **base_meta
            }]
        
        if action.kind == "bezier":
            # Cubic bezier curve
            p0, p1, p2, p3 = d["points"]
            bezier_points = self._generate_bezier_points(
                [self._p(p0[0], width), self._p(p0[1], height)],
                [self._p(p1[0], width), self._p(p1[1], height)],
                [self._p(p2[0], width), self._p(p2[1], height)],
                [self._p(p3[0], width), self._p(p3[1], height)],
                d.get("segments", 50)
            )
            return [{
                "type": "bezier",
                "points": bezier_points,
                "color": color,
                "width": line_width,
                **base_meta
            }]
        
        if action.kind == "arrow":
            return [{
                "type": "arrow",
                "from_x": self._p(d["x1"], width),
                "from_y": self._p(d["y1"], height),
                "to_x": self._p(d["x2"], width),
                "to_y": self._p(d["y2"], height),
                "color": color,
                "width": line_width,
                **base_meta
            }]
        
        if action.kind in {"shape", "highlight"}:
            shape = "box" if action.kind == "highlight" else str(d.get("shape", "rectangle"))
            legacy_shape = {
                "rectangle": "box", "ellipse": "ellipse", "circle": "circle",
                "diamond": "triangle", "polygon": "polygon", "star": "star", "hexagon": "hexagon"
            }.get(shape, shape)
            return [{
                "type": "shape",
                "shape_type": legacy_shape,
                "x": self._p(d["x"], width),
                "y": self._p(d["y"], height),
                "w": self._p(d["width"], width),
                "h": self._p(d["height"], height),
                "color": color,
                "fill": d.get("fill", False),
                **base_meta
            }]
        
        if action.kind == "text":
            return [{
                "type": "text",
                "content": str(d["text"])[:600],
                "x": self._p(d["x"], width),
                "y": self._p(d["y"], height),
                "color": color,
                "font_size": d.get("font_size", 14),
                **base_meta
            }]
        
        if action.kind == "image":
            return [{
                "type": "image",
                "src": str(d["src"]),
                "x": self._p(d["x"], width),
                "y": self._p(d["y"], height),
                "w": self._p(d["width"], width),
                "h": self._p(d["height"], height),
                "opacity": opacity,
                **base_meta
            }]
        
        if action.kind == "group":
            # Recursively compile children
            group_drawings = []
            for child_data in d.get("children", []):
                child_action = SceneAction(
                    id=f"{action.id}_child_{len(group_drawings)}",
                    kind=child_data.get("kind", "stroke"),
                    data=child_data.get("data", {}),
                    segment_id=action.segment_id,
                    layer=action.layer,
                    start_ms=action.start_ms,
                    duration_ms=action.duration_ms,
                    style=child_data.get("style", style),
                    z_order=z_order,
                    source_ref=action.source_ref,
                    undo_metadata=action.undo_metadata
                )
                group_drawings.extend(self._compile_action(child_action, width, height))
            return group_drawings
        
        if action.kind == "layer":
            # Layer control - return metadata for layer management
            return [{
                "type": "layer_control",
                "layer_id": str(d.get("layer_id", action.layer)),
                "opacity": opacity,
                "visible": d.get("visible", True),
                **base_meta
            }]
        
        if action.kind == "function_plot":
            return self._function_plot(action, width, height)
        
        return []
    
    def _generate_bezier_points(self, p0: list[float], p1: list[float], p2: list[float], p3: list[float], segments: int = 50) -> list[list[float]]:
        """Generate points along a cubic bezier curve."""
        points = []
        for i in range(segments + 1):
            t = i / segments
            # Cubic bezier formula: (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            points.append([x, y])
        return points

    def _function_plot(self, action: SceneAction, width: int, height: int) -> list[dict[str, Any]]:
        d, color = action.data, str(action.style["color"])
        evaluate = SafeExpression(str(d["expression"])).evaluate
        low, high = map(float, d.get("domain", [-10, 10]))
        sample_count = max(80, min(900, int(d.get("samples", 360))))
        samples: list[tuple[float, float]] = []
        for index in range(sample_count):
            x = low + (high - low) * index / (sample_count - 1)
            try:
                y = evaluate(x)
                if math.isfinite(y): samples.append((x, y))
            except (ArithmeticError, ValueError, OverflowError):
                pass
        if not samples: raise SceneValidationError("function plot has no drawable values")
        requested_range = d.get("range")
        if isinstance(requested_range, list) and len(requested_range) == 2 and float(requested_range[0]) < float(requested_range[1]):
            y_low, y_high = float(requested_range[0]), float(requested_range[1])
        else:
            values = sorted(value for _, value in samples)
            lo_i, hi_i = max(0, int(len(values) * .03)), min(len(values) - 1, int(len(values) * .97))
            y_low, y_high = values[lo_i], values[hi_i]
            if abs(y_high - y_low) < 1e-7: y_low, y_high = y_low - 1, y_high + 1
            margin = (y_high - y_low) * .12
            y_low, y_high = y_low - margin, y_high + margin
        panel = d.get("panel", [0.0, 0.0, 1.0, 1.0])
        panel_x, panel_y, panel_w, panel_h = map(float, panel)
        left = width * (panel_x + panel_w * .12)
        right = width * (panel_x + panel_w * .88)
        top = height * (panel_y + panel_h * .28)
        bottom = height * (panel_y + panel_h * .80)
        x_axis_y = min(bottom, max(top, bottom - (0 - y_low) / (y_high - y_low) * (bottom - top)))
        y_axis_x = min(right, max(left, left + (0 - low) / (high - low) * (right - left)))
        result = [
            {"type": "arrow", "from_x": left, "from_y": x_axis_y, "to_x": right, "to_y": x_axis_y, "color": "#e2e8f0", "_scene_action": action.id, "_start_ms": action.start_ms, "_duration_ms": action.duration_ms},
            {"type": "arrow", "from_x": y_axis_x, "from_y": bottom, "to_x": y_axis_x, "to_y": top, "color": "#e2e8f0", "_scene_action": action.id, "_start_ms": action.start_ms, "_duration_ms": action.duration_ms},
        ]
        path: list[list[float]] = []
        previous: tuple[float, float] | None = None
        for x, y in samples:
            if y < y_low or y > y_high:
                if len(path) > 1: result.append({"type": "freehand", "points": path, "color": color, "_scene_action": action.id, "_start_ms": action.start_ms, "_duration_ms": action.duration_ms})
                path = []
                continue
            px = left + (x - low) / (high - low) * (right - left)
            py = bottom - (y - y_low) / (y_high - y_low) * (bottom - top)
            if path and abs(py - path[-1][1]) > (bottom - top) * .28:
                if len(path) > 1: result.append({"type": "freehand", "points": path, "color": color, "_scene_action": action.id, "_start_ms": action.start_ms, "_duration_ms": action.duration_ms})
                path = []
            path.append([round(px, 2), round(py, 2)])
        if len(path) > 1: result.append({"type": "freehand", "points": path, "color": color, "_scene_action": action.id, "_start_ms": action.start_ms, "_duration_ms": action.duration_ms})
        return result


class FrameTracer:
    """Local contour-to-vector tracer for selected images or decoded video frames."""
    def trace_bgr(self, frame: Any, max_paths: int = 24) -> list[dict[str, Any]]:
        if cv2 is None or np is None or frame is None:
            raise RuntimeError("OpenCV and NumPy are required for local tracing")
        if len(frame.shape) == 2: gray = frame
        else: gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]
        if width < 2 or height < 2: return []
        edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 45, 130)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        candidates = sorted(contours, key=cv2.contourArea, reverse=True)
        output: list[dict[str, Any]] = []
        for contour in candidates:
            if len(output) >= max(1, min(80, max_paths)) or cv2.contourArea(contour) < max(20, width * height * .00012): continue
            epsilon = max(1.0, cv2.arcLength(contour, False) * .006)
            curve = cv2.approxPolyDP(contour, epsilon, False).reshape(-1, 2)
            if len(curve) < 2: continue
            output.append({"id": f"trace-{uuid.uuid4().hex[:8]}", "kind": "trace", "data": {"points": [[round(float(x) / width, 5), round(float(y) / height, 5)] for x, y in curve]}, "style": {"color": "#fbbf24", "width": 2.5, "opacity": .95}})
        return output


class RealtimeSceneBridge:
    """Transport-neutral function-call bridge for a streaming voice model.

    A WebRTC/WebSocket client forwards its completed `emit_scene` tool
    arguments here. The bridge neither owns credentials nor sends audio; it
    makes the safety and rendering contract identical for local and realtime
    tutors.
    """
    tool_definition = {
        "type": "function",
        "name": "emit_scene",
        "description": "Emit a validated, normalized canvas scene linked to spoken narration segments.",
        "parameters": {"type": "object", "additionalProperties": True},
    }

    def __init__(self, engine: "OmniSketchEngine") -> None:
        self.engine = engine

    def ingest_function_call(self, name: str, arguments: str | dict[str, Any], viewport: tuple[int, int]) -> CompiledScene:
        if name != "emit_scene":
            raise SceneValidationError(f"unsupported realtime tool: {name}")
        if isinstance(arguments, str):
            try:
                payload = json.loads(arguments)
            except json.JSONDecodeError as error:
                raise SceneValidationError("realtime scene arguments are not JSON") from error
        elif isinstance(arguments, dict):
            payload = arguments
        else:
            raise SceneValidationError("realtime scene arguments must be an object")
        return self.engine.compile_payload(payload, viewport)


class OmniSketchEngine:
    """Single entry point used by the existing tutor and future Realtime adapters."""
    def __init__(self) -> None:
        self.validator = SceneValidator()
        self.compiler = SceneCompiler()
        self.tracer = FrameTracer()
        self.viewport: tuple[int, int] = (1, 1)
        self._events: deque[SceneEvent] = deque(maxlen=512)

    def update_viewport(self, width: int, height: int) -> None:
        self.viewport = (max(1, int(width)), max(1, int(height)))
        self._record('viewport_changed', width=self.viewport[0], height=self.viewport[1])

    def _record(self, event_type: str, **details: Any) -> None:
        self._events.append(SceneEvent(time.time(), event_type, details))

    def events(self) -> tuple[SceneEvent, ...]:
        return tuple(self._events)

    def record_render_failure(self, reason: str) -> None:
        self._record('render_failed', reason=str(reason)[:300])

    def compile_payload(self, payload: dict[str, Any], viewport: tuple[int, int] | None = None) -> CompiledScene:
        started = time.perf_counter()
        target_viewport = viewport or self.viewport
        try:
            try:
                packet = self.validator.validate(payload)
            except SceneValidationError as primary_error:
                packet, warnings = self.validator.validate_best_effort(payload)
                self._record('scene_repaired', reason=str(primary_error)[:300], discarded=warnings[:12])
            compiled = self.compiler.compile(packet, target_viewport)
        except Exception as error:
            self._record('scene_rejected', reason=str(error)[:300], latency_ms=round((time.perf_counter() - started) * 1000, 3))
            raise
        self._record('scene_accepted', actions=len(packet.actions), drawings=len(compiled.drawings), latency_ms=round((time.perf_counter() - started) * 1000, 3))
        return compiled
        self._record('scene_accepted', actions=len(packet.actions), drawings=len(compiled.drawings), latency_ms=round((time.perf_counter() - started) * 1000, 3))
        return compiled

    def trace_frame_to_scene(self, frame: Any, title: str = "Traced reference") -> ScenePacket:
        started = time.perf_counter()
        actions = tuple(self.validator._action(item, index) for index, item in enumerate(self.tracer.trace_bgr(frame)))
        self._record('trace_completed', actions=len(actions), latency_ms=round((time.perf_counter() - started) * 1000, 3))
        return ScenePacket(actions=actions, title=title)

    def trace_media_file(self, path: str, timestamp_seconds: float = 0.0) -> ScenePacket:
        """Trace an image or a selected local-video frame without any cloud upload."""
        if cv2 is None:
            raise RuntimeError("OpenCV is required for file/video tracing")
        frame = cv2.imread(path)
        title = "Traced image"
        if frame is None:
            capture = cv2.VideoCapture(path)
            try:
                if not capture.isOpened():
                    raise RuntimeError("the selected reference could not be opened")
                capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(timestamp_seconds)) * 1000.0)
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise RuntimeError("the selected video frame could not be read")
                title = "Traced video frame"
            finally:
                capture.release()
        return self.trace_frame_to_scene(frame, title=title)

    def realtime_bridge(self) -> RealtimeSceneBridge:
        return RealtimeSceneBridge(self)
