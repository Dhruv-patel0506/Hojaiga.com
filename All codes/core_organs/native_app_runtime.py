"""
native_app_runtime.py — Prefer the app's own automation surface over clicking.

Clicking a 3D suite for an hour is not "working smartly". Blender exposes bpy,
Office exposes COM, many IDEs expose a CLI. This module is the efficient path
the task-graph compiler chooses *before* the UIA/vision loop:

    construct intent + 3d_suite + blender on PATH
        -> write a parametric bpy script
        -> launch the GUI with --python so the user can see the work
        -> verify the saved file exists (trust = checked outcome)

Handlers are keyed by *archetype*, never by a one-off app name in control flow.
A new suite (Maya, FreeCAD) is another generator function in NATIVE_HANDLERS.
If the native path cannot run, the caller falls back to DesktopAutonomyLoop.
"""

from __future__ import annotations

import os
import re
import time
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.native_app_runtime")

CapsuleCb = Callable[[str, str], None]


@dataclass
class NativeRunResult:
    ok: bool
    method: str
    evidence: str
    save_path: str = ""
    pid: int = 0

    def as_dict(self) -> dict:
        return {"ok": self.ok, "method": self.method, "evidence": self.evidence,
                "save_path": self.save_path, "pid": self.pid}


# ---------------------------------------------------------------------------
# Parametric mesh recipes (data, not per-task hardcodes)
# A "chair" is a named box-model recipe; unknown nouns fall back to a cube.
# ---------------------------------------------------------------------------

Box = Dict[str, Any]  # {name, loc=(x,y,z), scale=(sx,sy,sz)}

MESH_RECIPES: Dict[str, List[Box]] = {
    "chair": [
        {"name": "Seat", "loc": (0.0, 0.0, 0.45), "scale": (0.42, 0.42, 0.05)},
        {"name": "Back", "loc": (0.0, -0.37, 0.85), "scale": (0.42, 0.05, 0.40)},
        {"name": "LegFL", "loc": (0.32, 0.32, 0.22), "scale": (0.04, 0.04, 0.22)},
        {"name": "LegFR", "loc": (-0.32, 0.32, 0.22), "scale": (0.04, 0.04, 0.22)},
        {"name": "LegBL", "loc": (0.32, -0.32, 0.22), "scale": (0.04, 0.04, 0.22)},
        {"name": "LegBR", "loc": (-0.32, -0.32, 0.22), "scale": (0.04, 0.04, 0.22)},
    ],
    "stool": [
        {"name": "Seat", "loc": (0.0, 0.0, 0.45), "scale": (0.28, 0.28, 0.04)},
        {"name": "LegFL", "loc": (0.18, 0.18, 0.22), "scale": (0.035, 0.035, 0.22)},
        {"name": "LegFR", "loc": (-0.18, 0.18, 0.22), "scale": (0.035, 0.035, 0.22)},
        {"name": "LegBL", "loc": (0.18, -0.18, 0.22), "scale": (0.035, 0.035, 0.22)},
        {"name": "LegBR", "loc": (-0.18, -0.18, 0.22), "scale": (0.035, 0.035, 0.22)},
    ],
    "table": [
        {"name": "Top", "loc": (0.0, 0.0, 0.75), "scale": (0.80, 0.50, 0.04)},
        {"name": "LegFL", "loc": (0.70, 0.40, 0.36), "scale": (0.05, 0.05, 0.36)},
        {"name": "LegFR", "loc": (-0.70, 0.40, 0.36), "scale": (0.05, 0.05, 0.36)},
        {"name": "LegBL", "loc": (0.70, -0.40, 0.36), "scale": (0.05, 0.05, 0.36)},
        {"name": "LegBR", "loc": (-0.70, -0.40, 0.36), "scale": (0.05, 0.05, 0.36)},
    ],
    "cube": [
        {"name": "Cube", "loc": (0.0, 0.0, 0.5), "scale": (0.5, 0.5, 0.5)},
    ],
}

OBJECT_ALIASES = {
    "chair": "chair", "seat": "chair", "armchair": "chair",
    "stool": "stool", "barstool": "stool",
    "table": "table", "desk": "table", "workbench": "table",
    "cube": "cube", "box": "cube", "block": "cube",
}


def infer_object_kind(command: str) -> str:
    text = (command or "").lower()
    for token, kind in OBJECT_ALIASES.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            return kind
    return "cube"


def infer_save_path(command: str, object_kind: str) -> str:
    text = command or ""
    m = re.search(r"(?:save(?:\s+as)?|as)\s+([a-zA-Z0-9_\-]+\.(?:blend|glb|obj|fbx))", text, re.I)
    if not m:
        m = re.search(r"\b([a-zA-Z0-9_\-]+\.(?:blend|glb|obj|fbx))\b", text, re.I)
    filename = m.group(1) if m else f"{object_kind}.blend"
    jobs = os.path.join(os.environ.get("TEMP", "."), "hojaiga_native_jobs")
    os.makedirs(jobs, exist_ok=True)
    return os.path.abspath(os.path.join(jobs, filename))


def generate_blender_bpy(object_kind: str, save_path: str) -> str:
    """Pure function: bpy source that box-models `object_kind` and saves it."""
    boxes = MESH_RECIPES.get(object_kind) or MESH_RECIPES["cube"]
    abs_save = os.path.abspath(save_path).replace("\\", "/")
    lines = [
        "import bpy",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete(use_global=False)",
    ]
    for box in boxes:
        loc = box["loc"]
        scale = box["scale"]
        name = re.sub(r"[^A-Za-z0-9_]", "", str(box["name"])) or "Part"
        lines += [
            "bpy.ops.mesh.primitive_cube_add(size=2, location="
            f"({loc[0]}, {loc[1]}, {loc[2]}))",
            "obj = bpy.context.active_object",
            f"obj.name = {name!r}",
            f"obj.scale = ({scale[0]}, {scale[1]}, {scale[2]})",
            "bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)",
        ]
    lines += [
        "bpy.ops.object.select_all(action='SELECT')",
        f"bpy.ops.wm.save_as_mainfile(filepath={abs_save!r})",
        f"print('HOJAIGA_NATIVE_SAVED', {abs_save!r})",
    ]
    return "\n".join(lines) + "\n"


def _looks_like_blender(app_hint: str, launcher_path: str = "") -> bool:
    hay = f"{app_hint} {os.path.basename(launcher_path or '')}".lower()
    return "blender" in hay


def resolve_blender_exe(launcher_path: str = "") -> Optional[str]:
    candidates = []
    if launcher_path and launcher_path.lower().endswith(".exe"):
        candidates.append(launcher_path)
    # Catalog may point at a .lnk; still try common install trees.
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for root in (pf, pf86):
        foundation = os.path.join(root, "Blender Foundation")
        if os.path.isdir(foundation):
            try:
                for name in sorted(os.listdir(foundation), reverse=True):
                    exe = os.path.join(foundation, name, "blender.exe")
                    if os.path.isfile(exe):
                        candidates.append(exe)
            except Exception:
                pass
    seen = set()
    for c in candidates:
        p = os.path.abspath(c)
        if p.lower() not in seen and os.path.isfile(p):
            return p
        seen.add(p.lower())
    return None


def run_blender_construct(object_kind: str, save_path: str, launcher_path: str = "",
                          capsule_cb: Optional[CapsuleCb] = None,
                          timeout_s: float = 180.0) -> NativeRunResult:
    cap = capsule_cb or (lambda _s, _t: None)
    exe = resolve_blender_exe(launcher_path)
    if not exe:
        return NativeRunResult(False, "blender-missing",
                               "Blender executable not found on this host")

    script_dir = os.path.join(os.environ.get("TEMP", "."), "hojaiga_native_jobs")
    os.makedirs(script_dir, exist_ok=True)
    script_path = os.path.join(script_dir, f"build_{object_kind}.py")
    source = generate_blender_bpy(object_kind, save_path)
    with open(script_path, "w", encoding="utf-8") as fh:
        fh.write(source)

    if os.path.exists(save_path):
        try:
            os.remove(save_path)
        except Exception:
            pass

    cap("working", f"Blender: modeling {object_kind} (native bpy)")
    try:
        proc = subprocess.Popen(
            [exe, "--python", script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return NativeRunResult(False, "blender-launch-failed", str(exc))

    deadline = time.time() + timeout_s
    last_digest = 0.0
    while time.time() < deadline:
        if os.path.isfile(save_path) and os.path.getsize(save_path) > 1024:
            cap("working", f"Verified: {os.path.basename(save_path)} written")
            return NativeRunResult(True, "blender-bpy",
                                   f"file-created {save_path} size={os.path.getsize(save_path)}",
                                   save_path=save_path, pid=proc.pid or 0)
        now = time.time()
        if now - last_digest >= 8:
            cap("working", f"Still modeling {object_kind} in Blender")
            last_digest = now
        if proc.poll() is not None and not os.path.isfile(save_path):
            return NativeRunResult(False, "blender-exited-unsaved",
                                   f"blender exited {proc.returncode} before save",
                                   pid=proc.pid or 0)
        time.sleep(0.6)

    return NativeRunResult(False, "blender-timeout",
                           f"no save within {timeout_s:.0f}s",
                           save_path=save_path, pid=proc.pid or 0)


def run_native_construct(app_hint: str, command: str, *,
                         launcher_path: str = "",
                         object_kind: str = "",
                         save_path: str = "",
                         capsule_cb: Optional[CapsuleCb] = None) -> NativeRunResult:
    kind = object_kind or infer_object_kind(command)
    path = save_path or infer_save_path(command, kind)
    if _looks_like_blender(app_hint, launcher_path):
        return run_blender_construct(kind, path, launcher_path, capsule_cb)
    return NativeRunResult(False, "no-native-handler",
                           f"no native constructor for app='{app_hint}'")
