"""
app_teaching_automation -- SECTION 1 of HoJaiga: ONE bound engine that understands an application, teaches it, and does the work in it.

    section = AppTeachingAutomationSection()
    section.handle("how do I add a cube in Blender?")                     # -> teach
    section.handle("build a wooden dining table in Blender")              # -> delegate
    section.handle("learn Calculator")                                    # -> understand

onboard (understand) / teach (ask) / delegate (automate) are NOT three programs. They are one state machine over one pipeline:

    resolve   which application (the longest installed-program name in the request) and what is wanted (teach / delegate / understand, from the words)
    recall    ask the 3-domain RAG what it holds for the application: procedures, shortcuts, screen graph, child windows
    learn     only when the RAG is empty or thin for this application (or a window the run opens is new to it): the deep scan + web harvest run NOW, the RAG is updated, and the run goes on
    plan      RAG pathway lookup -> the CPU brain (brain_planner) splits the job into parts / goals -> every part is checked against what the application itself offers
    act       teach: say the Menu -> Tab -> Flyout -> Button + Shortcut pathway and point at the control   |   delegate: do it, step by step, UIA-first
    verify    goal-aware check after every step (the scene measured / the screen read), rollback + one corrected retry when the effect is wrong
    remember  what worked is written back (recipe + procedure) so the next run, in the same file or another, starts from it

The difference between teaching and delegating is only whether `act` points or does. Nothing here names an application: the way in is read from the program (a scripting engine in its --help text, otherwise
its accessibility tree).
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_organs import brain_planner as BP
from core_organs import env_guard as _eg

_orig_pins = _eg.check_runtime_pins                                   # the OmniParser pin check guards a model this section does not load; the training environment (transformers 5) legitimately differs
_eg.check_runtime_pins = lambda *a, **k: _orig_pins(*a, **dict(k, strict=False))

DATA = os.environ.get("HOJAIGA_DATA", r"D:\new_automation\data")
RECIPES = os.path.join(DATA, "recipes")
RUNS = os.path.join(DATA, "mvp_runs")
CWD = os.path.join("D:" + os.sep, "new_automation", "All codes")


# ------------------------------------------------------------------------------------------------------------------------------------------------ the state machine
class Flow:
    """The shared pipeline: every handled request goes through the same named states; each is timed and may add a note."""

    def __init__(self, log: Callable[[str], None] = print):
        self.states: List[Dict[str, Any]] = []
        self.log = log
        self.t0 = time.time()

    def enter(self, name: str, note: str = "") -> "Flow._State":
        return Flow._State(self, name, note)

    class _State:
        def __init__(self, flow: "Flow", name: str, note: str):
            self.flow, self.rec = flow, {"state": name, "note": note, "seconds": 0.0}

        def __enter__(self) -> Dict[str, Any]:
            self.t = time.time()
            self.flow.log(f"[{self.rec['state']}] {self.rec['note']}".rstrip())
            return self.rec

        def __exit__(self, et, ev, tb) -> bool:
            self.rec["seconds"] = round(time.time() - self.t, 2)
            if ev is not None:
                self.rec["error"] = f"{type(ev).__name__}: {str(ev)[:160]}"
            self.flow.states.append(self.rec)
            return False


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40]


def _tokens(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2 and w not in {"the", "and", "for", "with", "build", "make", "create", "please", "this", "that", "from"}}


# ------------------------------------------------------------------------------------------------------------------------------------------------ recipes (what worked, for the next run)
def recall_recipes(app_key: str, task: str, minimum: float = 0.0, limit: int = 3) -> List[Dict[str, Any]]:
    p = os.path.join(RECIPES, app_key + ".jsonl")
    if not os.path.isfile(p):
        return []
    want = _tokens(task)
    out = []
    for line in open(p, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        got = _tokens(r.get("task", ""))
        sim = len(want & got) / max(len(want | got), 1)
        if sim >= minimum:
            out.append(dict(r, similarity=round(sim, 2)))
    return sorted(out, key=lambda r: (-r["similarity"], -r.get("score", 0)))[:limit]


def remember_recipe(app_key: str, task: str, design: Dict[str, Any], score: float) -> None:
    os.makedirs(RECIPES, exist_ok=True)
    with open(os.path.join(RECIPES, app_key + ".jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"task": task, "design": design, "score": score, "when": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")


# ------------------------------------------------------------------------------------------------------------------------------------------------ backends
class ScriptedBackend:
    """An application with an embedded scripting engine (found in its own --help): owned instance + the bridge. Reads the registry; adds things with the application's own commands; measures the document."""
    kind = "scripted"

    def __init__(self, app: str, log: Callable[[str], None] = print, sandbox_root: str = ""):
        self.app, self.log, self.sandbox_root = app, log, sandbox_root
        self.bridge: Any = None
        self.hwnd, self.pid, self.sandbox, self.bg, self.guard = 0, 0, None, None, None
        self.registry_cache: List[Dict[str, Any]] = []
        self.launch_s = 0.0

    @staticmethod
    def capable(app: str) -> bool:
        from core_organs.professor import launcher as LN
        from core_organs.professor.adapters import script_bridge as SB
        t = LN.resolve(app)
        return bool(t.exe) and not t.chromium and bool(SB.scripting_exe(t.exe)[0])

    def start(self) -> "ScriptedBackend":
        from core_organs import background_window as bw, headless_input as hin, owned_guard as OG
        from core_organs.professor import dialogs as DG, launcher as LN, perception_ladder as PL, state_protect as SPT
        from core_organs.professor.adapters import script_bridge as SB
        t0 = time.time()
        hin.ensure_input_desktop()
        tgt = LN.resolve(self.app)
        fam, real = SB.scripting_exe(tgt.exe)
        if not fam:
            raise RuntimeError(f"{self.app} offers no scripting engine")
        self.sandbox = DG.Sandbox(_slug(self.app), time.strftime("%Y%m%d_%H%M%S"), self.sandbox_root)       # a continuation works inside the sandbox its document was saved in
        self.bridge, args = SB.ScriptBridge.prepare(tempfile.mkdtemp(prefix="hojaiga_bridge_"), fam, self.sandbox.root)
        self.guard = SPT.StateGuard(self.app, tgt.appid)
        self.guard.before()
        info = LN.launch_owned(tgt, self.guard, exe=real, args=args)
        self.hwnd = int(info.get("hwnd") or 0)
        if not (info.get("launched") and self.hwnd):
            raise RuntimeError(f"could not start an owned instance: {info.get('notes')}")
        self.pid = PL._pid(self.hwnd)
        with contextlib.suppress(Exception):
            OG.bind(self.pid, self.app)
        self.bg = bw.BackgroundSession(self.hwnd)
        self.bg.__enter__()
        if not self.bridge.alive():
            for _ in range(10):
                time.sleep(2.0)
                if self.bridge.alive():
                    break
        if not self.bridge.alive():
            raise RuntimeError("the application's bridge did not answer")
        self.launch_s = round(time.time() - t0, 1)
        return self

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            if self.bg is not None:
                self.bg.__exit__(None, None, None)
        if self.pid:
            subprocess.run(["taskkill", "/PID", str(self.pid), "/F"], capture_output=True, creationflags=0x08000000)     # the run's own throw-away instance, by its process id
            with contextlib.suppress(Exception):
                from core_organs import owned_guard as OG
                OG.release(self.pid)
        with contextlib.suppress(Exception):
            if self.guard is not None:
                self.guard.after()

    def __enter__(self) -> "ScriptedBackend":
        return self.start()

    def __exit__(self, *exc: Any) -> bool:
        self.stop()
        return False

    # -------------------------------------------------------------------------------------------------- knowledge from the program itself
    def registry(self) -> List[Dict[str, Any]]:
        if not self.registry_cache:
            self.registry_cache = self.bridge.registry()
        return self.registry_cache

    def find_commands(self, goal: str, limit: int = 5) -> List[Dict[str, Any]]:
        """The commands whose label / description / id best match the words of the goal."""
        want = _tokens(goal)
        scored = []
        for it in self.registry():
            have = _tokens(it["label"] + " " + it["id"].replace("_", " ").replace(".", " "))
            hay = have | _tokens(it.get("desc", ""))
            hit = len(want & have) * 2 + len(want & hay)
            if hit:
                scored.append((hit / (1 + 0.15 * len(have)), it))
        return [it for _, it in sorted(scored, key=lambda x: -x[0])[:limit]]

    def pathway_of(self, command_id: str, menus: Optional[Dict[str, Any]] = None, keys: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Menu -> Submenu -> Item for one command, and its shortcut, from the application's own menus and keymaps."""
        from core_organs.professor.adapters import script_bridge as SB
        menus = menus if menus is not None else self.bridge.menus()
        keys = keys if keys is not None else self.bridge.keymap()
        paths = [v for v in SB.menu_verbs(menus, 4) if v.aid == "script:" + command_id]
        paths.sort(key=lambda v: len(v.path))
        pref = ("Object Mode", "3D View", "3D View Generic", "Mesh", "Window", "Screen")
        rank = lambda ck: (pref.index(ck[1]) if ck[1] in pref else 99)                          # noqa: E731
        chords = sorted(keys.get(command_id, []), key=rank)
        opener = ""
        if paths:                                                                    # no key of its own: the key that opens the menu it lives in ('Shift+A' opens Add)
            labels = [p for p in paths[0].path if p]
            for lab in labels:
                for mid, m in menus.items():
                    if m.get("label") == lab and keys.get("menu:" + mid):
                        best = sorted(keys["menu:" + mid], key=rank)[0]
                        chords.append(best)
                        opener = f"{best[0]} opens the {lab} menu"
                        break
                if opener:
                    break
        clean = lambda v: " > ".join([p for p in v.path if p] + [v.label])                  # noqa: E731
        return {"command": command_id, "menu_path": clean(paths[0]) if paths else "", "also_in": [clean(v) for v in paths[1:3]], "opener": opener,
                "shortcuts": [f"{c} ({km})" for c, km in chords[:3]]}

    # -------------------------------------------------------------------------------------------------- the document
    def scene(self) -> Dict[str, Any]:
        return self.bridge.scene()

    def fresh_document(self) -> Dict[str, Any]:
        """Empty the document (the factory scene's own starter objects are not part of the person's job)."""
        before = self.scene()
        r = self.bridge.scene_restore({"objects": []})
        return {"removed": len(before.get("objects", [])), "res": r.get("ok"), "left": len(self.scene().get("objects", [])), "error": r.get("error", "")}

    def outbox_path(self, name: str) -> str:
        return os.path.join(self.sandbox.outbox, name)

    def save(self, name: str) -> Tuple[bool, str]:
        path = self.outbox_path(name)
        ok, note = self.bridge.save_copy(path)
        return ok and os.path.isfile(path), path

    def open_file(self, path: str) -> Tuple[bool, str]:
        return self.bridge.open_file(path)


# ------------------------------------------------------------------------------------------------------------------------------------------------ 3D building (scripted backend)
def _free_offset(prior: Dict[str, Any], design: Dict[str, Any], gap: float = 0.6) -> List[float]:
    """Where to put a new object so it does not touch what the document already holds: to the right of everything there."""
    boxes = [o["bbox"] for o in prior.get("objects", []) if o.get("bbox")]
    if not boxes:
        return [0.0, 0.0, 0.0]
    right = max(b[1][0] for b in boxes)
    mine = [BP.part_box(p) for p in design["parts"]]
    left = min(b[0][0] for b in mine)
    return [round(right + gap - left, 4), 0.0, 0.0]


def build_design(be: ScriptedBackend, design: Dict[str, Any], shapes: Dict[str, str], log: Callable[[str], None] = print, tol: float = 0.04) -> Dict[str, Any]:
    """Make the parts in the application with its own commands. Each part: add the shape, measure what came out, scale it to the asked size, turn it, colour it, then CHECK against the scene (size, place);
    a wrong result is rolled back to the scene before it and made once more with a correction."""
    br = be.bridge
    prior = be.scene()
    off = _free_offset(prior, design)
    lift = -min(BP.part_box(p)[0][2] for p in design["parts"])                    # the lowest point of the whole object sits on the ground (a global shift, parts keep their places)
    steps: List[Dict[str, Any]] = []
    made: List[str] = []
    for p in design["parts"]:
        want_dims = p["size"]
        at = [p["at"][0] + off[0], p["at"][1] + off[1], p["at"][2] + off[2] + lift]
        rec: Dict[str, Any] = {"part": p["name"], "shape": p["shape"], "attempts": [], "ok": False}
        scale_fix = [1.0, 1.0, 1.0]
        for attempt in range(2):
            snap = be.scene()
            t0 = time.time()
            known = {o["name"] for o in snap["objects"]}
            note: List[str] = []
            ok, msg = br.execute(shapes[p["shape"]], {"location": at})
            note.append(msg[:80])
            new = [o for o in be.scene()["objects"] if o["name"] not in known]
            if not ok or len(new) != 1:
                rec["attempts"].append({"ok": False, "why": f"add: {msg[:100]}; new objects {len(new)}", "rolled_back": bool(br.scene_restore(snap).get("ok"))})
                continue
            o = new[0]
            ratio = [(want_dims[i] / o["dims"][i]) * scale_fix[i] if o["dims"][i] > 1e-6 else 1.0 for i in range(3)]
            ok2, m2 = br.execute("transform.resize", {"value": ratio})
            note.append(m2[:60])
            for ax, ang in zip("XYZ", p["rotate"]):
                if abs(ang) > 1e-6:
                    br.execute("transform.rotate", {"value": math.radians(ang), "orient_axis": ax})
            nm = br.paint(o["name"], p["color"] + [1.0], rename=p["name"])
            after = be.scene()
            got = next((x for x in after["objects"] if x["name"] == (nm or o["name"])), None)
            if got is None:
                rec["attempts"].append({"ok": False, "why": "the new object is gone after scaling", "rolled_back": bool(br.scene_restore(snap).get("ok"))})
                continue
            derr = max(abs(got["dims"][i] - want_dims[i]) / max(want_dims[i], 1e-6) for i in range(3))
            cen = [(got["bbox"][0][i] + got["bbox"][1][i]) / 2.0 for i in range(3)]
            lo, hi = BP.part_box({**p, "at": at})
            wcen = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
            perr = max(abs(cen[i] - wcen[i]) for i in range(3))
            good = derr <= tol and perr <= max(0.02, 0.03 * max(want_dims))
            rec["attempts"].append({"ok": good, "dim_err": round(derr, 4), "pos_err_m": round(perr, 4), "seconds": round(time.time() - t0, 2), "name": got["name"]})
            if good:
                rec["ok"], rec["object"] = True, got["name"]
                made.append(got["name"])
                break
            scale_fix = [scale_fix[i] * (want_dims[i] / got["dims"][i]) if got["dims"][i] > 1e-6 else 1.0 for i in range(3)]
            br.scene_restore(snap)                                                     # the wrong effect is undone before the corrected try
            rec["attempts"][-1]["rolled_back"] = True
        steps.append(rec)
        log(f"  part {p['name']:<14} {'ok' if rec['ok'] else 'FAILED'} ({len(rec['attempts'])} attempt(s))")
    return {"steps": steps, "made": made, "offset": off, "lift": round(lift, 4), "prior_objects": [o["name"] for o in prior["objects"]]}


def judge_scene(task: str, design: Dict[str, Any], build: Dict[str, Any], before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Measured quality of what is in the document now - from the document, not from the planner's claim."""
    mine = [o for o in after["objects"] if o["name"] in build["made"]]
    n_want, n_got = len(design["parts"]), len(mine)
    steps = build["steps"]
    perr = [a["pos_err_m"] for s in steps for a in s["attempts"][-1:] if "pos_err_m" in a and s["ok"]]
    derr = [a["dim_err"] for s in steps for a in s["attempts"][-1:] if "dim_err" in a and s["ok"]]
    boxes = [(o["bbox"][0], o["bbox"][1]) for o in mine if o.get("bbox")]
    comps = BP.components(boxes, 0.015) if boxes else []
    biggest = max((len(c) for c in comps), default=0)
    vol = lambda i: max(1e-9, (boxes[i][1][0] - boxes[i][0][0]) * (boxes[i][1][1] - boxes[i][0][1]) * (boxes[i][1][2] - boxes[i][0][2]))     # noqa: E731
    main = max(comps, key=lambda c: (len(c), sum(vol(i) for i in c))) if comps else []
    floating = [mine[i]["name"] for c in comps if c is not main for i in c]
    zmin = min((b[0][2] for b in boxes), default=0.0)
    pierced = BP.piercing(boxes, [o["name"] for o in mine if o.get("bbox")]) if boxes else []
    prior_before = {o["name"]: (o["loc"], o["dims"], o.get("verts")) for o in before["objects"]}
    prior_after = {o["name"]: (o["loc"], o["dims"], o.get("verts")) for o in after["objects"] if o["name"] in prior_before}
    untouched = all(prior_after.get(k) == v for k, v in prior_before.items())
    rolled = sum(1 for s in steps for a in s["attempts"] if a.get("rolled_back"))
    colours = sum(1 for o in mine if o.get("mats"))
    qty = BP.quantity_problems(task, [o["name"] for o in mine], design)
    m = {"quantity_problems": qty, "parts_wanted": n_want, "parts_built": n_got, "completeness": round(n_got / max(n_want, 1), 3), "dim_err_mean": round(sum(derr) / max(len(derr), 1), 4), "pos_err_mean_m": round(sum(perr) / max(len(perr), 1), 4),
         "connected": biggest == n_got and n_got > 0, "floating_parts": floating, "piercing": pierced, "on_ground": abs(zmin) <= 0.02, "lowest_z": round(zmin, 4), "coloured": colours, "rollbacks": rolled,
         "earlier_objects_untouched": untouched, "earlier_objects": len(prior_before), "extent_m": [round(max(b[1][i] for b in boxes) - min(b[0][i] for b in boxes), 3) for i in range(3)] if boxes else None,
         "vertices": sum(o.get("verts", 0) or 0 for o in mine)}
    score = 100.0 * (0.35 * m["completeness"] + 0.15 * (1 - min(m["dim_err_mean"] / 0.05, 1)) + 0.10 * (1 - min(m["pos_err_mean_m"] / 0.05, 1)) + 0.20 * (1.0 if m["connected"] else 0.0)
                     + 0.10 * (1.0 if m["on_ground"] else 0.0) + 0.05 * (colours / max(n_got, 1)) + 0.05 * (1.0 if untouched else 0.0))
    if qty:
        score -= 25.0                                                                  # the order counted things the build does not have
    if pierced:
        score -= min(30.0, 10.0 * len(pierced))                                    # a part through another is not a sound build, however well connected
    m["score"] = round(max(score, 0.0), 1)
    return m


def vlm_look(image: str, task: str, model: str = "qwen2.5vl:3b") -> Dict[str, Any]:
    """A second opinion from a picture-reading model (on the CPU): does the picture show what was asked? Reported next to the measurements, never in place of them."""
    import base64
    import requests
    if not image or not os.path.isfile(image):
        return {"ok": False, "why": "no picture"}
    t0 = time.time()
    try:
        b64 = base64.b64encode(open(image, "rb").read()).decode()
        body = {"model": model, "stream": False, "format": "json", "options": {"num_gpu": 0, "temperature": 0.1, "num_predict": 200, "num_ctx": 3072},
                "prompt": f'This is a 3D viewport. The job was: "{task}". Rate from 1 to 5 how well the picture shows that object (5 = clearly a good model of it, 1 = not recognisable). Reply JSON {{"score": n, "sees": "what you see", "wrong": "what is off"}}.',
                "images": [b64]}
        r = requests.post(BP.OLLAMA + "/api/generate", json=body, timeout=900).json()
        obj = json.loads(r.get("response", "{}"))
        return {"ok": True, "score": obj.get("score"), "sees": str(obj.get("sees", ""))[:200], "wrong": str(obj.get("wrong", ""))[:200], "seconds": round(time.time() - t0, 1), "model": model}
    except Exception as exc:
        return {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:100]}", "seconds": round(time.time() - t0, 1)}


# ------------------------------------------------------------------------------------------------------------------------------------------------ the engine
class AppIntelligenceEngine:
    """What every section of the product shares: the RAG, the CPU brain, the adapter, coverage checks and on-the-fly learning."""

    def __init__(self, rag: Any = None, brain: Optional[BP.Brain] = None, adapter_dir: str = "", log: Callable[[str], None] = print):
        self.rag, self.brain, self.log = rag, brain, log
        self.adapter_dir = adapter_dir
        self._names: List[str] = []

    def get_rag(self) -> Any:
        if self.rag is None:
            from core_organs import rag as R
            self.rag = R.get_rag()
        return self.rag

    def get_brain(self) -> BP.Brain:
        if self.brain is None:
            self.brain = BP.Brain()
        return self.brain

    def installed_names(self) -> List[str]:
        if not self._names:
            from core_organs.harvest import catalogue as C
            self._names = [a["name"] for a in C.installed()]
        return self._names

    def coverage(self, key: str) -> Dict[str, int]:
        rag = self.get_rag()
        cov = {"procedures": 0, "chunks": 0, "hotkeys": 0, "graph_nodes": 0, "graph_edges": 0}
        with contextlib.suppress(Exception):
            ps = rag.proc.stats(key)
            cov["procedures"], cov["chunks"] = int(ps.get("procedures", 0)), int(ps.get("chunks", 0))
        with contextlib.suppress(Exception):
            cov["hotkeys"] = int(rag.fast.count(key))
        with contextlib.suppress(Exception):
            gs = rag.graph.stats(key)
            cov["graph_nodes"], cov["graph_edges"] = int(gs.get("nodes", 0)), int(gs.get("edges", 0))
        return cov

    @staticmethod
    def thin(cov: Dict[str, int]) -> bool:
        """Not enough to teach or act from: no procedures or shortcuts to speak of AND no screen graph."""
        return (cov["chunks"] + cov["hotkeys"] + cov["procedures"] < 8) and cov["graph_nodes"] < 8

    def key_of(self, app: str) -> str:
        from core_organs.rag import domains as DM
        return DM.key_for(DM.DESKTOP, BP.strip_version(app))

    def learn_desktop(self, app: str, minutes: float = 6.0) -> Dict[str, Any]:
        """The deep scan + web harvest, now: the same onboarding the overnight run uses, bounded in time."""
        from core_organs.rag import onboard as OB
        r = OB.onboard(app, explore=True, per_app_min=minutes, max_actions=20, log=self.log)
        out = {"classified": r.get("classified"), "docs": r.get("docs"), "explore": r.get("explore"), "seconds": r.get("seconds"), "error": r.get("error")}
        if not ((r.get("docs") or {}).get("steps")):                       # the plain-HTTP search found nothing (measured on Paint: 0 pages): the engine's own pages and AI summary, read in a real browser
            with contextlib.suppress(Exception):
                from core_organs.harvest import search_browser as SBR
                key = (r.get("classified") or {}).get("key") or self.key_of(app)
                br = SBR.run([BP.strip_version(app)], max_tutorials=2, log=self.log, app_keys={BP.strip_version(app): key})
                out["browser_harvest"] = (br.get("apps") or [{}])[0]
        return out

    def learn_scripted(self, be: ScriptedBackend, key: str, app: str) -> Dict[str, Any]:
        """A program with a scripting engine is read through that engine: its own menus (every command's path) and keymaps (every shortcut) go into the RAG as procedures and shortcuts."""
        from core_organs.harvest import bridge as BR
        from core_organs.professor.adapters import script_bridge as SB
        rag = self.get_rag()
        menus, keys = be.bridge.menus(), be.bridge.keymap()
        verbs = [v for v in SB.menu_verbs(menus, 4) if v.aid.startswith("script:") and v.safety == "safe"]
        n_proc = n_keys = 0
        from core_organs.rag import domains as DM
        DM.register(rag, key, DM.DESKTOP, {"why": "learned through the application's own scripting engine"})
        seen = set()
        for v in verbs[:900]:
            cid = v.aid[7:]
            if v.text_path in seen:
                continue
            seen.add(v.text_path)
            chord = (keys.get(cid) or [("", "")])[0][0]
            steps = [{"text": f"Open the {p} menu" if i < len(v.path) else f"Choose {p}" + (f" (shortcut {chord})" if chord else ""), "target": p, "route_hint": "control_click"} for i, p in enumerate(v.path + [v.label])]
            with contextlib.suppress(Exception):
                r = rag.proc.ingest_procedure(key, f"{app}: {v.text_path}", steps, "app-registry", trust="learned")
                n_proc += r.inserted + r.updated
            if chord:
                with contextlib.suppress(Exception):
                    BR.ingest_hotkeys(rag, [{"app_name": app, "app_key": key, "action": v.text_path, "shortcut": chord, "source": "keymap_file", "url": ""}])
                    n_keys += 1
        return {"menus": len(menus), "verbs": len(verbs), "procedures": n_proc, "shortcuts": n_keys}

    def pathways(self, goal: str, key: str, snapshot: Any = None) -> Dict[str, Any]:
        from core_organs.rag import Query
        ret = None
        rag = self.get_rag()
        with contextlib.suppress(Exception):
            from core_organs.rag import hybrid as HY
            key = HY.resolve_key(rag, key) or key                         # 'vscode' -> 'visual_studio_code': the store's own key
        with contextlib.suppress(Exception):
            ret = rag.retrieve(Query(text=goal, app_key=key, snapshot=snapshot, mode="auto"))
        plans = BP.pathways(ret)
        if not plans:                                                     # nothing under this key: the same task on a similar app / site (marked as such, never presented as this app's own)
            with contextlib.suppress(Exception):
                from core_organs.rag import hybrid as HY
                plans = HY.pathways(rag, goal, key, 3)
        return {"plans": plans, "evidence": BP.evidence_lines(ret)}

    GENERIC = {"how", "what", "where", "when", "why", "can", "does", "would", "should", "could", "there", "some", "need", "want", "help", "show", "tell", "teach", "please", "get", "got", "way", "thing"}

    @staticmethod
    def weak(pathways: Dict[str, Any], goal: str, app: str = "") -> bool:
        """The RAG's answer does not speak about the goal: none of the goal's own words (not the program's name, not question words) appears in any pathway step or evidence line."""
        skip = set(_tokens(app)) | AppIntelligenceEngine.GENERIC
        want = [w for w in _tokens(goal) if w not in skip]
        if not want:
            return False

        def hit(text: str) -> bool:
            have = _tokens(text)
            return any(w == h or (len(w) >= 4 and len(h) >= 4 and (w.startswith(h[:4]) or h.startswith(w[:4]))) for w in want for h in have)
        for pl in pathways.get("plans", []):
            if hit(" ".join(pl.get("steps", []))):
                return False
        for line in pathways.get("evidence", []):
            if hit(line):
                return False
        return True

    def ask_web(self, question: str, app: str, key: str, log: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """The question itself, put to the search engine's own synthesized answer in a real browser (public page, one session, no account): the instruction lines become logic chains in the RAG under this app,
        so the next person asking the same thing is answered from memory."""
        from core_organs.harvest import local_recorder as LR, search_browser as SBR, web_recorder as WR
        from core_organs.professor.adapters.cdp import CdpBrowser, CdpPage
        from core_organs.rag import logic_chains as LC
        import urllib.parse
        t0 = time.time()
        out: Dict[str, Any] = {"found": False, "steps": [], "summary": "", "written": {}}
        query = question if re.search(r"\b" + re.escape(BP.strip_version(app).lower()) + r"\b", question.lower()) else f"{question} in {BP.strip_version(app)}"
        with LR.OwnedApp("Microsoft Edge") as edge:
            b = CdpBrowser((getattr(edge, "info", {}) or {}).get("cdp_port"))
            b.wait(15.0)
            old = {t["id"] for t in b.targets()}
            b.new_tab("about:blank")
            new = [t for t in b.targets() if t["id"] not in old]
            drv = WR.CdpDriver(CdpPage(new[-1]))
            ai = SBR.ai_summary(drv, query)
        if ai.get("found") and len(ai.get("steps") or []) < 3:                  # a summary written as prose: its sentences are the steps
            act = re.compile(r"\b(click|select|choose|open|press|go to|navigate|tap|use|type|enter|drag|hold|check|toggle|set|add|insert|save|export|draw|fill|pick|then)\b", re.I)
            sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", ai.get("text", "")) if 25 <= len(x.strip()) <= 300 and act.search(x) and not re.match(r"(?i)(like|dislike|show more|sources?)\b", x.strip())]
            if len(sents) > len(ai.get("steps") or []):
                ai["steps"] = [{"text": x, "names": [], "keys": [k if isinstance(k, str) else k[0] for k in LC.KEY_RX.findall(x)][:3], "imgs": []} for x in sents[:12]]
        out["found"] = bool(ai.get("found") and len(ai.get("steps") or []) >= 2)             # a summary with fewer than two instruction lines is not a lesson
        if out["found"]:
            steps = ai["steps"]
            out["steps"] = [st["text"] for st in steps]
            out["step_dicts"] = [{"text": st["text"], "names": list(st.get("names") or []), "keys": list(st.get("keys") or [])} for st in steps]
            out["summary"] = (ai.get("text") or "")[:600]
            chains = LC.build_chains(steps, [[] for _ in steps], ai.get("text", ""))
            out["written"] = LC.write(self.get_rag(), key, app, chains, [[] for _ in steps], "bing:ai-summary?q=" + urllib.parse.quote_plus(query), f"AI summary: {query}")
        out["seconds"] = round(time.time() - t0, 1)
        return out

    def grounder(self) -> Callable[..., Any]:
        """The vision model on the GPU, loaded on first use."""
        from core_organs import agent_executor as AE
        holder: Dict[str, Any] = {}
        adapter = self.adapter_dir or newest_adapter()

        def call(image: Any, som: Dict[str, Any], app_key: str, goal: str, controls: Any = None, hint: str = "") -> Any:
            if "g" not in holder:
                from core_organs import vision_ground as VG
                vg = VG.VisionGrounder(self, app_key)
                if vg._in_process():                                          # this Python can hold the model (peft + a new enough transformers): in-process
                    holder["g"], holder["mode"] = AE.AdapterGrounder(adapter[0], prompt_version=adapter[1]), "in"
                else:                                                         # the product's own environment cannot: the model runs in its own process and is asked over a local port
                    holder["g"], holder["mode"] = vg, "server"
            if holder["mode"] == "server":
                return holder["g"]._ask(image, som, goal, list(controls or []), hint)
            return holder["g"](image, som, app_key, goal, controls=controls, hint=hint) if adapter[1] == 3 else holder["g"](image, som, app_key, goal, controls=controls)
        call.holder = holder                                                # type: ignore[attr-defined]
        return call


def newest_adapter() -> Tuple[str, int]:
    """(the directory of the newest trained adapter, the prompt format it was trained on)."""
    import glob
    choice = os.path.join(DATA, "ai_root", "harvest", "training", "runs", "ADAPTER_CHOICE.json")      # written from a MEASURED held-out comparison (core_organs.eval_v3), not from file dates
    with contextlib.suppress(Exception):
        c = json.load(open(choice, encoding="utf-8"))
        if os.path.isdir(c["adapter"]):
            return c["adapter"], int(c["prompt_version"])
    runs = sorted(glob.glob(os.path.join(DATA, "ai_root", "harvest", "training", "runs", "run_*", "adapter")), key=os.path.getmtime)
    if not runs:
        return "", 1
    return runs[-1], (3 if "v3split" in runs[-1] else 2 if "v2split" in runs[-1] else 1)


# ------------------------------------------------------------------------------------------------------------------------------------------------ the section
class AppTeachingAutomationSection:
    name = "app_teaching_automation"
    description = "Understand an application, teach it, or do the work in it - one engine."

    def __init__(self, engine: Optional[AppIntelligenceEngine] = None, log: Callable[[str], None] = print):
        self.log = log
        self.engine = engine or AppIntelligenceEngine(log=log)

    # -------------------------------------------------------------------------------------------------- entry point
    def handle(self, task: str, app: str = "", mode: str = "auto", file: str = "", learn: str = "auto", recall: bool = True, live: bool = False, vlm: bool = True,
               keep_open: bool = False, refine: int = 1, confirm: Optional[Callable[[str, str], bool]] = None, visible_browser: bool = True) -> Dict[str, Any]:
        """One request in, one report out. `mode` auto|understand|teach|delegate; `file` = a document inside a previous run's sandbox to continue in (the 'same file' case) or '' for a new one;
        `learn` auto|always|never (the on-the-fly scan); `recall` = may the run start from a recipe it stored before."""
        E = self.engine
        flow = Flow(self.log)
        rep: Dict[str, Any] = {"task": task, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        os.makedirs(RUNS, exist_ok=True)
        with flow.enter("resolve", task[:90]) as st:
            intent = BP.classify_intent(task, E.get_brain())
            rep["intent"] = intent
            mode_ = intent["mode"] if mode == "auto" else mode
            app_ = app or BP.detect_app(task, E.installed_names())
            host = "" if app_ else web_host_in(task)
            st["note"] = f"mode={mode_} ({intent['how']}), app={app_ or host or '?'}"
            rep["mode"], rep["app"] = mode_, app_ or host
            if not app_ and not host and mode_ == "delegate":
                host = "(browser)"                                                      # an order that names no installed program: the browser is where it is done; the first look at the page decides
            if not app_ and not host:
                rep["error"] = "no installed program or web address is named in the request; say which one"
                rep["flow"] = flow.states
                return rep
            if host:                                                                    # a site or web app: the same recall -> learn -> teach / do pipeline, through the web domains of the RAG
                return self._web(task, "" if host == "(browser)" else host, mode_, learn, flow, rep, confirm, visible_browser)
            key = E.key_of(app_)
            rep["app_key"] = key
        with flow.enter("recall", key) as st:
            cov0 = E.coverage(key)
            rep["rag_before"] = cov0
            st["note"] = f"{key}: " + ", ".join(f"{k}={v}" for k, v in cov0.items())
        scripted = False
        with contextlib.suppress(Exception):
            scripted = ScriptedBackend.capable(app_)
        rep["route"] = "scripting-engine" if scripted else "accessibility-tree"
        from core_organs.harvest import universal_scan as US
        fp, reg = "", None
        with contextlib.suppress(Exception):
            fp = US.fingerprint(app_)
            reg = US.known(key, fp)                                                  # scan-once: a known (exe, file version) loads from data/app_registry.json, no scan
        rep["registry"] = {"fingerprint": fp, "known": bool(reg), "controls": (reg or {}).get("n_controls", 0)}
        need_learn = learn == "always" or mode_ == "understand" or (learn == "auto" and E.thin(cov0) and not reg)
        if need_learn and not scripted and learn != "never":
            with flow.enter("learn", f"{app_}: the RAG is thin ({'understand requested' if mode_ == 'understand' else 'under-mapped'}) - scanning now") as st:
                t_scan = time.time()
                rep["learned"] = E.learn_desktop(app_)
                with contextlib.suppress(Exception):
                    US.register(key, fp, [{"name": n, "source": "onboard"} for n in (rep["learned"].get("classified") or {}).get("controls", [])], time.time() - t_scan)
                rep["rag_after_learn"] = E.coverage(key)
                st["note"] += f" -> {rep['rag_after_learn']}"
        try:
            if scripted:
                rep.update(self._scripted(task, app_, key, mode_, flow, need_learn and learn != "never", file, recall, vlm, keep_open, refine))
            else:
                rep.update(self._uia(task, app_, key, mode_, flow, live, vlm, learn_ok=(learn != "never")))
        except Exception as exc:
            rep["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        rep["rag_after"] = E.coverage(key)
        rep["flow"] = flow.states
        rep["seconds"] = round(time.time() - flow.t0, 1)
        with open(os.path.join(RUNS, time.strftime("%Y%m%d_%H%M%S_") + _slug(app_) + "_" + mode_ + ".json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=1, default=str)
        return rep

    def web_delegate(self, task: str, host: str = "", confirm: Optional[Callable[[str, str], bool]] = None, visible: bool = True, max_steps: int = 14, on_login: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
        """Do the order in a browser of our own (visible, its own persistent profile): look -> decide -> gate -> act -> check, until done, staged at a send / post control, waiting for a sign-in, or out of steps."""
        from core_organs import web_delegate as WD
        out: Dict[str, Any] = {}
        with WD.OwnedBrowser(visible=visible) as br:
            drv = br.driver()
            agent = WD.WebAgent(self.engine.get_brain(), drv, log=self.log, confirm=confirm, max_steps=max_steps, on_login=on_login, growth=self.growth())
            proof: Dict[str, str] = {}
            if host:
                with contextlib.suppress(Exception):
                    drv.navigate("https://" + host)
                    time.sleep(2.5)
                    if self.proof_dir:
                        os.makedirs(self.proof_dir, exist_ok=True)
                        proof["before"] = os.path.join(self.proof_dir, f"before_{_slug(host)[:30]}.png")
                        drv.screenshot().save(proof["before"])
            out = agent.run(task, "")
            with contextlib.suppress(Exception):
                shot = os.path.join(RUNS, time.strftime("%Y%m%d_%H%M%S_") + "web_final.png")
                drv.screenshot().save(shot)
                out["picture"] = shot
                if self.proof_dir:
                    proof["after"] = os.path.join(self.proof_dir, f"after_{_slug(host or 'web')[:30]}.png")
                    drv.screenshot().save(proof["after"])
            out["proof"] = proof
        out["route"] = "web-delegate"
        return out

    def _web(self, task: str, host: str, mode: str, learn: str, flow: Flow, rep: Dict[str, Any], confirm: Optional[Callable[[str, str], bool]] = None, visible: bool = True) -> Dict[str, Any]:
        """A website / web app. Teach: what the RAG holds for the site, and - when that does not speak to the question - the question put to the search engine's summary. Understand: onboarding of the address.
        Delegate is not built for the web in this MVP and says so."""
        from core_organs.rag import domains as DM
        E = self.engine
        url = "https://" + host
        c = DM.classify(url) if mode != "teach" or learn == "always" else {"domain": DM.WEBSITE, "key": DM.key_for(DM.WEBSITE, url)}
        key = c.get("key") or DM.key_for(DM.WEBSITE, url)
        rep["app_key"], rep["route"], rep["domain"] = key, "web", c.get("domain")
        with flow.enter("recall", key) as st:
            rep["rag_before"] = E.coverage(key)
            st["note"] = str(rep["rag_before"])
        if mode == "delegate":
            with flow.enter("act", f"doing it in the browser ({host or 'wherever the order leads'})") as st:
                out = self.web_delegate(task, host, confirm=confirm, visible=visible)
                rep.update(out)
                st["note"] = f"{out.get('status')}: {out.get('done_steps', 0)}/{len(out.get('steps', []))} steps worked"
        elif mode == "understand":
            with flow.enter("learn", f"onboarding {host}") as st:
                from core_organs.rag import onboard as OB
                rep["learned"] = {k: v for k, v in OB.onboard(host, explore=True, max_actions=12, log=self.log).items() if k in ("classified", "docs", "explore", "seconds", "error")}
                st["note"] = str(rep["learned"])[:160]
        else:
            with flow.enter("plan", "RAG pathway lookup") as st:
                teach = {"rag": E.pathways(task, key)}
                st["note"] = f"{len(teach['rag']['plans'])} pathway(s)"
            if learn != "never" and E.weak(teach["rag"], task, host):
                with flow.enter("learn", "the question itself, to the engine's AI summary in a browser") as st:
                    web = E.ask_web(task, host, key)
                    teach["web"] = web
                    rep["learned_from_question"] = web.get("written")
                    st["note"] = f"found={web['found']} steps={len(web['steps'])}"
                    if web["found"]:
                        teach["rag"] = E.pathways(task, key)
            rep["teach"] = teach
            with flow.enter("act", "say it") as st:
                rep["say"] = say_pathway(task, teach, E.get_brain())
                st["note"] = rep["say"][:120]
        rep["rag_after"] = E.coverage(key)
        rep["flow"] = flow.states
        rep["seconds"] = round(time.time() - flow.t0, 1)
        return rep

    # -------------------------------------------------------------------------------------------------- scripted route (Blender and any program with a scripting engine)
    def _scripted(self, task: str, app: str, key: str, mode: str, flow: Flow, learn: bool, file: str, recall: bool, vlm: bool, keep_open: bool, refine: int = 1) -> Dict[str, Any]:
        E = self.engine
        out: Dict[str, Any] = {}
        sbx = ""
        if file:                                                                      # <sandbox>/outbox/<file>: the folder two levels up is the sandbox the document belongs to
            cand = os.path.dirname(os.path.dirname(os.path.abspath(file)))
            sbx = cand if os.path.basename(os.path.dirname(os.path.abspath(file))) == "outbox" else ""
        with ScriptedBackend(app, self.log, sbx) as be:
            out["launch_s"] = be.launch_s
            if learn:
                with flow.enter("learn", "reading the application's own menus and keymaps") as st:
                    out["learned"] = E.learn_scripted(be, key, app)
                    out["rag_after_learn"] = E.coverage(key)
                    st["note"] = str(out["learned"])
            if mode in ("understand",):
                return out
            if file:
                with flow.enter("plan", f"open the document from the earlier run: {os.path.basename(file)}") as st:
                    ok, msg = be.open_file(file)
                    st["note"] += f" -> {ok}"
                    sc0 = be.scene()
                    out["opened_file"] = {"ok": ok, "msg": msg[:100], "objects": [o["name"] for o in sc0["objects"]], "file": sc0.get("file", "")}
                    if not ok:                                                    # a continuation that did not continue is an error, never a silent fresh start
                        out["error"] = f"could not open the earlier document: {msg[:120]}"
                        return out
            if mode == "teach":
                with flow.enter("plan", "RAG pathway + the application's own menus") as st:
                    cands = be.find_commands(task, 4)
                    menus, keys = be.bridge.menus(), be.bridge.keymap()
                    ways = [be.pathway_of(c["id"], menus, keys) | {"label": c["label"], "what": c.get("desc", "")} for c in cands]
                    ret = E.pathways(task, key)
                    out["teach"] = {"pathways": ways, "rag": ret}
                    st["note"] = f"{len(ways)} commands found"
                with flow.enter("act", "say it") as st:
                    out["say"] = say_pathway(task, out["teach"], E.get_brain())
                    st["note"] = out["say"][:120]
                return out
            # delegate: build a 3D object from parts
            shapes = BP.shapes_of(be.registry())
            out["shapes"] = sorted(shapes)
            if not shapes:
                out["error"] = "the application offers no add-a-shape commands in its registry: nothing this section can build with"
                return out
            from core_organs import house_builder as HB
            if HB.is_building(task) and "cube" in shapes:
                return self._house(be, task, key, shapes["cube"], flow, recall, file, out)
            with flow.enter("plan", "RAG recipes -> CPU brain -> parts") as st:
                recipes = recall_recipes(key, task, 0.0, 3) if recall else []
                out["recipes_seen"] = [{"task": r["task"], "similarity": r["similarity"], "score": r.get("score")} for r in recipes]
                exact = next((r for r in recipes if r["similarity"] >= 0.85 and r.get("score", 0) >= 75 and not BP.critic(r["design"])), None)          # a stored design is reused only if it still passes today's geometry critic
                exact_design = bool(exact)
                if exact:
                    design, probs, planner = exact["design"], [], {"source": "recipe", "attempts": []}
                    st["note"] = "reused a stored recipe (no model call)"
                else:
                    fs = [r["design"] for r in recipes if r.get("score", 0) >= 75 and r["similarity"] < 0.85 and not BP.critic(r["design"])]
                    res = BP.design_parts(E.get_brain(), task, sorted(shapes), fs)
                    design, probs, planner = res["design"], res["problems"], {"source": "brain", "attempts": res["attempts"]}
                    st["note"] = f"{len(design['parts'])} parts, {len(probs)} problem(s) left, {len(planner['attempts'])} attempt(s), {sum(a.get('seconds') or 0 for a in planner['attempts']):.0f}s on the CPU"
                out["design"], out["design_problems"], out["planner"] = design, probs, planner
            if not design["parts"]:
                out["error"] = "the planner produced no usable part"
                return out
            before = be.scene()
            if not file and not before["objects"] == []:
                with flow.enter("plan", "fresh document") as st:
                    out["fresh"] = be.fresh_document()
                before = be.scene()
            def attempt(des: Dict[str, Any], tag: str) -> Dict[str, Any]:
                """Build one design in the document as it is now, measure it, take its picture, ask the picture reader. Returns everything needed to compare attempts."""
                b = build_design(be, des, shapes, self.log)
                aft = be.scene()
                q = judge_scene(task, des, b, before, aft)
                shot = be.outbox_path(_slug(task)[:30] + tag + ".png")
                pic = shot if be.bridge.shot(shot, b["made"]) else ""
                if pic:
                    keep = os.path.join(RUNS, time.strftime("%Y%m%d_%H%M%S_") + _slug(task)[:30] + tag + ".png")
                    with contextlib.suppress(Exception):
                        import shutil
                        shutil.copy(shot, keep)
                        pic = keep
                return {"design": des, "build": b, "quality": q, "picture": pic, "vlm": vlm_look(pic, task) if (vlm and pic) else None}

            with flow.enter("act", f"building {len(design['parts'])} parts with the application's own commands") as st:
                best = attempt(design, "")
                attempts = [best]
                st["note"] = f"{len(best['build']['made'])}/{len(design['parts'])} parts made"
            with flow.enter("verify", "measure the document, look at the picture") as st:
                st["note"] = f"geometry {best['quality']['score']}, picture reader {(best['vlm'] or {}).get('score')}"
            rounds = 0
            while vlm and best["vlm"] and best["vlm"].get("ok") and (best["vlm"].get("score") or 5) <= 3 and rounds < refine and not exact_design:
                rounds += 1
                with flow.enter("plan", f"review round {rounds}: the picture reader said '{best['vlm'].get('wrong', '')[:80]}' - re-plan, roll back, rebuild") as st:
                    note = (f"A reviewer looked at a 3D picture of your previous design and said: sees '{best['vlm'].get('sees', '')}', problem '{best['vlm'].get('wrong', '')}'. "
                            "Rethink what rests on what and where each part is; here is your previous design for reference: " + json.dumps(BP.to_prompt_format(best["design"])))
                    res2 = BP.design_parts(E.get_brain(), task, sorted(shapes), [], extra_problems=[note])
                    if not res2["design"]["parts"]:
                        st["note"] += " -> no usable redesign"
                        break
                    be.bridge.scene_restore(before)                               # the document goes back to how it was before the first build
                    cand = attempt(res2["design"], f"_r{rounds}")
                    attempts.append(cand)
                    better = ((cand["vlm"] or {}).get("score") or 0, cand["quality"]["score"]) > ((best["vlm"] or {}).get("score") or 0, best["quality"]["score"])
                    st["note"] += f" -> picture {(cand['vlm'] or {}).get('score')}, geometry {cand['quality']['score']}: {'kept' if better else 'worse, the earlier design is rebuilt'}"
                    if better:
                        best = cand
                    else:
                        be.bridge.scene_restore(before)
                        best = attempt(best["design"], "_back")
                        break
            design, build = best["design"], best["build"]
            out["design"], out["build"], out["quality"], out["picture"], out["vlm"] = design, build, best["quality"], best["picture"], best["vlm"]
            out["attempts"] = [{"geometry": a["quality"]["score"], "picture": (a["vlm"] or {}).get("score"), "parts": len(a["design"]["parts"])} for a in attempts]
            with flow.enter("verify", "save the document") as st:
                ok, path = be.save(_slug(task)[:30] + ".blend")
                out["saved"] = {"ok": ok, "path": path, "bytes": os.path.getsize(path) if ok else 0}
                pv = (best["vlm"] or {}).get("score")
                out["verdict"] = ("passes both checks" if (best["quality"]["score"] >= 90 and (pv is None or pv >= 4)) else "geometry sound, appearance doubtful" if best["quality"]["score"] >= 90 else "poor")
                st["note"] = f"geometry {best['quality']['score']}, picture {pv}, verdict: {out['verdict']}, saved={ok}"
            with flow.enter("remember", "recipe + procedure") as st:
                if out["quality"]["score"] >= 90 and out["verdict"] == "passes both checks" and not probs:
                    remember_recipe(key, task, design, out["quality"]["score"])
                    st["note"] = "stored"
                else:
                    st["note"] = f"not stored (verdict: {out['verdict']})"
        return out

    def _house(self, be: "ScriptedBackend", task: str, key: str, cube_op: str, flow: Flow, recall: bool, file: str, out: Dict[str, Any]) -> Dict[str, Any]:
        """A whole building: the model plans the rooms (or a stored plan is reused), the compiler lays out floors / walls / roof / stairs / furniture, one batched call builds it, views are taken room by room."""
        from core_organs import house_builder as HB
        E = self.engine
        bkey = key + "_house"
        with flow.enter("plan", "rooms: a stored plan, else the CPU brain (one short call)") as st:
            recs = recall_recipes(bkey, task, 0.0, 1) if recall else []
            if recs and recs[0]["similarity"] >= 0.6:
                rooms, source = recs[0]["design"]["rooms"], "recipe"
                st["note"] = f"reused a stored plan ({len(rooms)} rooms, similarity {recs[0]['similarity']}): no model call"
            else:
                rooms, source, probs = [], "brain", ["no answer"]
                for attempt in range(2):
                    obj, meta = E.get_brain().json(HB.rooms_prompt(task) + ("" if attempt == 0 else " Previous problems: " + "; ".join(probs)), BP.DESIGN_SYSTEM, max_tokens=800)
                    rooms, probs = HB.clean_rooms(obj)
                    out.setdefault("room_plan_seconds", []).append(meta.get("seconds"))
                    if not probs:
                        break
                st["note"] = f"{len(rooms)} rooms from the brain in {sum(x or 0 for x in out['room_plan_seconds']):.0f}s, problems: {probs}"
            if len(rooms) < 4:
                out["error"] = "the planner gave no usable room list"
                return out
            out["rooms"], out["room_source"] = rooms, source
        with flow.enter("plan", "layout and compile (arithmetic)") as st:
            lay = HB.layout(rooms)
            parts = HB.compile_house(lay)
            out["house"] = HB.summarize(lay, parts)
            st["note"] = str(out["house"])
        if not file:
            with flow.enter("plan", "fresh document") as st:
                out["fresh"] = be.fresh_document()
        before = be.scene()
        items = [{"op": cube_op, "props": {"size": 1.0, "location": p["at"], "scale": p["size"], "rotation": [math.radians(a) for a in p["rotate"]]}, "name": p["name"], "rgba": p["color"] + [1.0],
                  "collection": p.get("collection", "")} for p in parts]
        with flow.enter("act", f"{len(items)} parts in a few batched calls") as st:
            t0 = time.time()
            res = be.bridge.batch_add(items)
            out["build"] = {"made": len(res["made"]), "failed": res["failed"][:6], "materials": res["materials"], "seconds": round(time.time() - t0, 1)}
            st["note"] = str(out["build"])
        with flow.enter("verify", "measure the document") as st:
            sc = be.scene()
            boxes = [(o["bbox"][0], o["bbox"][1]) for o in sc["objects"] if o.get("bbox") and o["type"] == "MESH"]
            comps = BP.components(boxes, 0.03)
            ext = [round(max(b[1][i] for b in boxes) - min(b[0][i] for b in boxes), 2) for i in range(3)] if boxes else None
            q = {"parts_planned": len(items), "parts_built": len(res["made"]), "completeness": round(len(res["made"]) / max(len(items), 1), 3), "connected_groups": len(comps),
                 "extent_m": ext, "planned_footprint_m": out["house"]["footprint_m"], "lowest_z": round(min(b[0][2] for b in boxes), 2) if boxes else None, "failed": len(res["failed"]), "earlier_objects": len(before["objects"])}
            ok_ext = bool(ext) and abs(ext[0] - lay["width"]) < 1.5 and abs(ext[1] - lay["length"]) < 1.5
            q["score"] = round(100 * (0.5 * q["completeness"] + 0.3 * (1.0 if len(comps) <= 2 else 0.0) + 0.2 * (1.0 if ok_ext else 0.0)), 1)
            out["quality"] = q
            st["note"] = str(q)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        outdir = os.path.join(RUNS, "house_" + stamp)
        os.makedirs(outdir, exist_ok=True)
        cols = sorted({p.get("collection", "") for p in parts if p.get("collection")})
        floors_ = lay["floors"]

        def on_floor(c: str, f: int) -> bool:
            return c == f"Floor{f}" or c == f"Floor{f}_walls" or c.endswith(f"_F{f}")
        pics: List[Dict[str, str]] = []
        with flow.enter("verify", "views: outside, plan with the roof off, a close-up of each room") as st:
            def shot(name: str, **kw: Any) -> None:
                path = be.outbox_path(f"{name}.png")
                if be.bridge.view_shot(path, **kw):
                    import shutil
                    dst = os.path.join(outdir, f"{name}.png")
                    shutil.copy(path, dst)
                    pics.append({"view": name, "path": dst})
            shot("01_outside", view="iso", frame=list(cols))
            for f in floors_:
                shot(f"02_plan_floor{f}_roof_off", view="top", hide=["Roof"] + [c for c in cols if any(on_floor(c, g) for g in floors_ if g > f)], frame=[c for c in cols if on_floor(c, f)])
            order = sorted([r for r in lay["rooms"] if r["kind"] not in ("stairs", "hall")], key=lambda r: -r["area"])[:6]
            for i, r in enumerate(order):
                rc = f"{r['name'].replace(' ', '_')}_F{r['floor']}"
                shot(f"1{i}_room_{rc}", view="steep", hide=["Roof"] + [c for c in cols if any(on_floor(c, g) for g in floors_ if g > r["floor"])], frame=[rc])
            out["views"] = pics
            st["note"] = f"{len(pics)} pictures in {outdir}"
        with flow.enter("verify", "save the document") as st:
            ok, path = be.save("house.blend")
            if ok:
                import shutil
                shutil.copy(path, os.path.join(outdir, "house.blend"))
            out["saved"] = {"ok": ok, "path": path, "copy": os.path.join(outdir, "house.blend"), "bytes": os.path.getsize(path) if ok else 0}
            out["verdict"] = "built" if q["completeness"] >= 0.98 and q["score"] >= 90 else "incomplete"
            st["note"] = f"{out['verdict']}, saved={ok}"
        with flow.enter("remember", "the room plan") as st:
            if out["verdict"] == "built" and source == "brain":
                remember_recipe(bkey, task, {"rooms": rooms}, q["score"])
                st["note"] = "stored"
            else:
                st["note"] = "not stored"
        return out

    # -------------------------------------------------------------------------------------------------- accessibility-tree route
    _growth_store: Any = None

    def growth(self) -> Any:
        """The self-growing memory shared by every route of this section (rag.self_growth)."""
        if self._growth_store is None:
            from core_organs.rag import self_growth as SG
            self._growth_store = SG.SelfGrowth()
        return self._growth_store

    def heal_goal(self, agent: Any, s: Any, goal: str, key: str) -> Any:
        """Self-healing by ANOTHER PATH: when a goal's first route fails its check, the keyboard alternatives the RAG holds for the same goal are tried one by one (posted to the window, then verified by what appeared on screen).
        A route that works is remembered (rag.self_growth) so the next run starts from it."""
        from core_organs.agent_executor import StepRecord
        from core_organs import agent_executor as AE
        from core_organs.rag import logic_chains as LC
        t0 = time.perf_counter()
        try:
            adv = agent.advise(goal)
            alts = [m for t in (adv.get("alternatives") or []) for m in LC.KEY_RX.findall(t)]
        except Exception:
            alts = []
        for combo in list(dict.fromkeys(alts))[:3]:
            try:
                pre = s.observe_lite()
                s.app.chord(combo.lower().replace(" ", ""))
                time.sleep(0.9)
                post = s.observe_lite()
                worked, effect = AE.default_verify(pre, post, None, None)
            except Exception:
                continue
            if worked:
                with contextlib.suppress(Exception):
                    self.growth().learn(key, [c["name"] for c in pre.get("controls", [])][:60], {"name": goal, "type": "hotkey", "keys": combo}, "hotkey", [c["name"] for c in post.get("controls", [])][:60], None, True)
                return StepRecord(goal, "done", source="heal:rag-hotkey", effect=f"the click path failed its check; the RAG's shortcut {combo} worked: {effect}", ms=round((time.perf_counter() - t0) * 1000, 1))
        return None

    proof_dir = ""                                                     # set by a caller that wants before / after pictures of the window it works in (the gauntlet)

    def proof_shot(self, s: Any, tag: str, which: str) -> str:
        if not self.proof_dir:
            return ""
        with contextlib.suppress(Exception):
            os.makedirs(self.proof_dir, exist_ok=True)
            img, _origin = s.app.grab(popups=True)
            path = os.path.join(self.proof_dir, f"{which}_{_slug(tag)[:40]}.png")
            img.convert("RGB").save(path)
            return path
        return ""

    def _uia(self, task: str, app: str, key: str, mode: str, flow: Flow, live: bool, vlm: bool, session: Any = None, learn_ok: bool = True) -> Dict[str, Any]:
        from core_organs import agent_executor as AE
        E = self.engine
        out: Dict[str, Any] = {}
        t_run = time.time()
        if mode == "understand":
            return out
        if mode == "teach" and not live:
            with flow.enter("plan", "RAG pathway lookup") as st:
                out["teach"] = {"rag": E.pathways(task, key)}
                st["note"] = f"{len(out['teach']['rag']['plans'])} pathway(s), {len(out['teach']['rag']['evidence'])} evidence line(s)"
                if learn_ok and E.weak(out["teach"]["rag"], task, app):
                    st["note"] += "; none speaks about this question"
                    with flow.enter("learn", "the question itself, to the engine's AI summary in a browser") as st2:
                        web = E.ask_web(task, app, key)
                        out["teach"]["web"] = web
                        out["learned_from_question"] = web.get("written")
                        st2["note"] = f"found={web['found']} steps={len(web['steps'])} written={web['written']}"
                        if web["found"]:
                            out["teach"]["rag"] = E.pathways(task, key)
            with flow.enter("act", "say it") as st:
                out["say"] = say_pathway(task, out["teach"], E.get_brain())
                st["note"] = out["say"][:120]
            return out
        from core_organs import canvas_live as CL
        from core_organs import agent_artist as AA
        from core_organs.harvest import local_recorder as _LR
        _LR.OwnedApp.READY_S = 25.0                                    # a packaged (UWP) app shows a splash first: wait for its interface,
        _LR.OwnedApp.VISIBLE_FALLBACK = True                           # and if it never comes up parked, open it visibly once and park it then (measured on Calculator)
        from core_organs.harvest import child_windows as CW
        ground = E.grounder()
        with (contextlib.nullcontext(session) if session is not None else AE.LiveSession(app)) as s:             # a visible window the caller already owns (the tutor) is used as it is
            agent = AE.Agent(key, s.observe_lite, ground, s.act, rag=E.get_rag(), recover=s.recover, uia_first=True, observe_full=s.observe)
            with contextlib.suppress(Exception):
                agent.tools.append(AA.ArtistTools(CL.LivePainter(s), E.get_rag()))
            if mode == "teach":
                with flow.enter("plan", "live: see the screen, find the control") as st:
                    adv = agent.advise(task)
                    out["teach"] = {"rag": E.pathways(task, key), "live": {k: adv[k] for k in ("say", "point", "source", "alternatives", "allowed")}}
                    st["note"] = adv["say"][:100]
                with flow.enter("act", "say it") as st:
                    out["say"] = say_pathway(task, out["teach"], E.get_brain())
                    st["note"] = out["say"][:120]
                return out
            with flow.enter("plan", "split the job into goals the screen can answer") as st:
                obs = s.observe_lite()
                names = [c["name"] for c in obs.get("controls", []) if c.get("name")][:80]
                from core_organs import knowledge_first as KF
                cached = KF.lookup(key, task)                                       # Tier 0: a verified parameterised plan for this intent, parameters bound from this task - no planner call
                if cached:
                    goals, plan_src = cached, "cache"
                else:
                    goals, plan_src = plan_goals(E.get_brain(), task, names, E.pathways(task, key)), "planner"
                out["goals"], out["plan_source"] = goals, plan_src
                st["note"] = f"{len(goals)} goals ({plan_src})"
            recs = []
            out["proof"] = {"before": self.proof_shot(s, key, "before")}
            with flow.enter("act", "run the goals: ground, act, verify, roll back") as st:
                for g in goals:
                    hwnd0 = s.app.hwnd
                    is_type = bool(re.match(r"^\s*type\b", g, re.I))
                    fields_before = set() if is_type else {field_id(c) for c in small_fields(s)}
                    before_w = CW.snapshot(hwnd0)
                    r = direct_type(s, g) or agent.step(g)
                    if r.status in ("no_effect", "wrong_effect") and not re.match(r"^\s*(?:type|press)\b", g, re.I):
                        healed = self.heal_goal(agent, s, g, key)               # the click path did not work: the RAG's other way to the same goal (a keyboard shortcut) is tried and checked
                        if healed is not None:
                            r = healed
                    recs.append(r)
                    if not is_type:                                                  # what this step opened: the fields that were not there before it (a Find / Replace bar), to be filled in order by the next 'type' goals
                        time.sleep(0.8)
                        after_ids = {field_id(c) for c in small_fields(s)}
                        s._new_fields, s._filled_fields = after_ids - fields_before, set()
                        if s._new_fields:
                            self.log(f"[fields] {len(s._new_fields)} text field(s) opened by '{g}': " + ", ".join(sorted(f.split('|')[0] for f in s._new_fields)))
                    kids = CW.new_windows(before_w, hwnd0)
                    for kid in kids:                                              # a window this run opened that the RAG has not seen: learn it now
                        with contextlib.suppress(Exception):
                            det = CW.describe(kid["hwnd"])
                            CW.register(E.get_rag(), key, [CW.entry({"name": g}, kid, det, "left open")])
                            out.setdefault("new_windows_learned", []).append(kid.get("title", ""))
                    if r.status != "done" and r.status != "advised":
                        with contextlib.suppress(Exception):
                            from core_organs.harvest import universal_scan as US
                            US.mark_stale(key, US.fingerprint(app), g)               # a control stopped matching: the next run diff-scans this app instead of trusting the registry
                        break
                st["note"] = f"{sum(1 for r in recs if r.status == 'done')}/{len(goals)} done"
            out["steps"] = [{"goal": r.goal, "status": r.status, "source": r.source, "reason": r.reason, "rolled_back": r.rolled_back, "assisted": r.assisted, "ms": r.ms, "effect": r.effect[:400], "attempts": r.attempts} for r in recs]
            with flow.enter("verify", "read the result back from the screen") as st:
                out["final_text"] = read_back(s)
                out["proof"]["after"] = self.proof_shot(s, key, "after")
                st["note"] = f"{len(out['final_text'])} characters read back"
            with flow.enter("verify", "summary") as st:
                out["verification"] = {"done": sum(1 for r in recs if r.status == "done"), "total": len(goals), "rollbacks": sum(1 for r in recs if r.rolled_back),
                                       "caught": sum(1 for r in recs if r.reason or r.rolled_back), "model_calls": sum(1 for r in recs if r.source == "model") + (1 if out.get("plan_source") == "planner" else 0)}
                st["note"] = str(out["verification"])
                with contextlib.suppress(Exception):
                    from core_organs import knowledge_first as KF
                    v = out["verification"]
                    all_done = bool(goals) and v["done"] == v["total"] and len(recs) == len(goals)
                    KF.store(key, task, goals, all_done, replayed=out.get("plan_source") == "cache", source="planner")   # a verified novel plan becomes Tier 0; a replayed one that failed is demoted
                    KF.record(task[:60], key, time.time() - t_run, v["model_calls"], "T0" if out.get("plan_source") == "cache" else "T3", out.get("plan_source") != "cache", all_done)
        return out


# ------------------------------------------------------------------------------------------------------------------------------------------------ language helpers
def web_host_in(task: str) -> str:
    """The first web address named in a request ('https://x.org/page', 'excalidraw.com', 'on docs.github.com'); '' when none."""
    m = re.search(r"(?:https?://)?((?:[a-z0-9-]+\.)+(?:com|org|net|io|app|dev|co|ai|edu|gov|info|me|tv))\b", task, re.I)
    return m.group(1).lower() if m else ""


def say_pathway(task: str, teach: Dict[str, Any], brain: Optional[BP.Brain] = None) -> str:
    """The answer a tutor gives: Menu -> Submenu -> Item + shortcut, the pointed control, the RAG's route and the fall-back. Plain text from the structure; no model needed for it."""
    lines: List[str] = []
    for w in teach.get("pathways", [])[:2]:
        s = f"{w['label']}: " + (w["menu_path"] or "(not in a menu)")
        if w.get("shortcuts"):
            s += "   shortcut: " + ", ".join(w["shortcuts"][:2])
        if w.get("opener"):
            s += f"   ({w['opener']})"
        lines.append(s)
    web = teach.get("web")
    if web and web.get("found"):
        lines.append("From the web (the search engine's summary, read in a browser):")
        lines += ["  " + str(i + 1) + ". " + t for i, t in enumerate(web["steps"][:8])]
    live = teach.get("live")
    if live and live.get("say"):
        lines.append("On screen: " + live["say"])
    for pl in (teach.get("rag") or {}).get("plans", [])[:2]:
        if pl["steps"]:
            lines.append("From what was learned: " + " -> ".join(pl["steps"]))
    if not lines:
        lines.append("I have nothing learned for that yet; say 'learn <app>' and I will scan it first.")
    return "\n".join(lines)


PLACE_RX = re.compile(r"\b(title|subtitle|heading)\s+(?:of\s+|called\s+|named\s+|saying\s+|as\s+|is\s+)?[\"\u201c']?(.+?)[\"\u201d']?(?=\s*(?:,|;|\band\s+(?:a\s+|the\s+)?(?:sub)?(?:title|heading)\b|$))", re.I)


def placeholder_goals(task: str) -> List[str]:
    """'add a title Roadmap 2027 and a subtitle Q1 plan' -> ['Type "Roadmap 2027" in the title', 'Type "Q1 plan" in the subtitle']: text for a slide's placeholders is read from the words, never planned by a model."""
    if not re.search(r"\b(?:add|insert|set|put|write|create|make|give)\b", task, re.I):
        return []
    if re.match(r"^\s*(?:how|where|what|why|can|could|show|teach|explain|tell)\b", task, re.I):
        return []                                                                  # a question is answered, not typed
    out: List[str] = []
    for m in PLACE_RX.finditer(task):
        where = "subtitle" if m.group(1).lower() == "subtitle" else "title"
        txt = m.group(2).strip(" .\"'")
        if txt and len(txt) < 120 and not re.match(r"^(?:in|on|to|for|at|of)\s", txt, re.I):
            out.append(f'Type "{txt}" in the {where}')
    return out


REPLACE_RXS = (re.compile(r"\b(?:change|swap)\s+(?:every\s+|all\s+|the\s+word\s+)?[\"“']?([^\"”',]+?)[\"”']?\s+(?:to|into)\s+[\"“']?([^\"”',]+?)[\"”']?\s*$", re.I),
               re.compile(r"\breplace\s+(?:every\s+|all\s+|the\s+word\s+)?[\"“']?([^\"”',]+?)[\"”']?\s+(?:with|by)\s+[\"“']?([^\"”',]+?)[\"”']?\s*$", re.I))


class _ReplaceRx:
    @staticmethod
    def search(task: str) -> Any:
        for rx in REPLACE_RXS:
            m = rx.search(task)
            if m and not re.match(r"^(?:to|the|a)\s", m.group(1), re.I):
                return m
        return None


REPLACE_RX = _ReplaceRx()


def replace_goals(task: str, rag_hint: Dict[str, Any]) -> List[str]:
    """'... use Edit Replace to change cat to bird': the way to the replace tool comes from what the RAG learned about THIS program (its menu path), then the two words are typed into the two fields that open, and the replace-all
    control is pressed. Nothing here names a program: the path is read from the stored pathway (Open the X menu / Choose Y)."""
    m = REPLACE_RX.search(task)
    if not m:
        return []
    old, new = m.group(1).strip(), m.group(2).strip()
    path: List[str] = []
    for pl in (rag_hint or {}).get("plans", [])[:3]:
        steps = [str(x) for x in pl.get("steps", [])]
        if not any(re.search(r"\breplace\b", x, re.I) for x in steps):
            continue
        for x in steps:
            ma = re.search(r"([A-Z][A-Za-z]{1,16}(?: [A-Z][A-Za-z]{1,16})?)\s*(?:→|>|›|->)\s*([A-Z][A-Za-z ]{1,24}?)(?:[.)→>]|$)", x)
            if ma and re.search(r"replace", ma.group(2), re.I):                    # 'go to Edit -> Replace': a menu path as written in the stored pathway
                path = [f"Click the {ma.group(1).strip()} button", f"Click the {ma.group(2).strip()} option"]
                break
            mm = re.search(r"(?:open|click)\s+(?:the\s+)?([A-Z][\w ]{1,20}?)\s+menu", x, re.I)
            if mm:
                path.append(f"Click the {mm.group(1).strip()} button")
            mc = re.search(r"(?:choose|click|select)\s+(?:the\s+)?[\"']?([A-Za-z][\w ]{1,24}?)[\"']?(?:\s*[(\-]|\s+option|\s+button|$)", x, re.I)
            if mc and re.search(r"replace", mc.group(1), re.I):
                path.append(f"Click the {mc.group(1).strip()} option")
                break
        if path:
            break
    if not path:
        mt = re.search(r"\b([A-Z][a-z]+)\s*(?:>|→|-)?\s*(Find and Replace|Replace)\b", task)       # the order itself names the menu path ('use Edit Replace ...')
        if mt:
            path = [f"Click the {mt.group(1)} button", f"Click the {mt.group(2)} option"]
    if not path:
        for pl in (rag_hint or {}).get("plans", [])[:3]:                           # else the shortcut the stored pathway gives for it
            for x in pl.get("steps", []):
                mk = re.search(r"((?:Ctrl|Control|Alt|Shift)\s*\+\s*[A-Za-z0-9])\b[^.]{0,40}replace|replace[^.]{0,40}((?:Ctrl|Control|Alt|Shift)\s*\+\s*[A-Za-z0-9])\b", str(x), re.I)
                if mk:
                    path = ["Press " + re.sub(r"\s+", "", (mk.group(1) or mk.group(2)))]
                    break
            if path:
                break
    if not path:
        return []
    return path + [f'Type "{old}"', f'Type "{new}"', "Click the Replace all button"]


def plan_goals(brain: BP.Brain, task: str, control_names: Sequence[str], rag_hint: Dict[str, Any]) -> List[str]:
    """The job as goals a screen can answer one at a time ('Click the Bold button', 'Type "..."'). A drawing job is passed whole (the drawing tools take it). Each goal that names a control names one that exists."""
    if re.search(r"\b(draw|trace|sketch|lightboard|colou?r|shade)\b", task, re.I):
        return [task]
    ph = placeholder_goals(task)
    if ph:
        return ph
    if REPLACE_RX.search(task):
        typed = re.match(r"^(.*?)[,;]?\s+(?:and\s+)?then\s+(.*)$", task, re.I)
        rg = replace_goals(typed.group(2) if typed else task, rag_hint)
        if rg:
            head = re.search(r"\b(?:type|write|enter)\s+(?:the\s+(?:words?|text)\s+)?[\"“']?(.+?)[\"”']?\s*$", typed.group(1), re.I) if typed else None
            return ([f'Type "{head.group(1).strip()}"'] if head else []) + rg
    m = re.search(r"\b(?:type|write|enter)\s+(?:the\s+(?:words?|text|sentence)\s+|a\s+(?:line|sentence)\s+)?[\"\u201c']?(.+?)[\"\u201d']?(?:\s+(?:for me|please|in\s+\w+))*\s*$", task, re.I)
    if m and len(m.group(1)) > 1:                                                  # the task names the text itself: nothing to decompose
        sp = re.split(r"\s*[,;]?\s*(?:and\s+)?then\s+", m.group(1).strip(), maxsplit=1, flags=re.I)
        if len(sp) == 2 and sp[1].strip():                                         # 'type X, then <something else>': X is typed as it is, the rest is planned on the screen's controls
            return ['Type "' + sp[0].strip(" ,;") + '"'] + plan_goals(brain, sp[1].strip(), control_names, rag_hint)
        return ['Type "' + m.group(1).strip() + '"']
    with contextlib.suppress(Exception):                                          # arithmetic is read from the words and mapped to the keys the screen really has: the model never picks a digit (measured: it planned 7 + 8 for 21 + 21)
        from core_organs import goal_planner as GP
        if re.search(r"\d", task) and GP._ARITH_RE.search(task):
            g = GP.expand(task, list(control_names))
            if g and g != [task]:
                return [re.sub(r"^press\s+(.+)$", r"Click the " + chr(92) + "1 button", x, flags=re.I) for x in g]          # the form the screen's own control names answer directly (no model call)
    hints = "; ".join(" -> ".join(p["steps"]) for p in rag_hint.get("plans", [])[:2])
    prompt = (f'Job: "{task}"\nControls visible on the screen now: {", ".join(control_names)}\nWhat was learned about this program: {hints or "nothing"}\n'
              'Split the job into the smallest steps, each ONE action: Click the <control name> button | Type "<text>" | Press <keys>. Use control names from the list when one fits. '
              'Reply JSON {"goals": ["...", "..."]} with at most 12 goals.')
    obj, _ = brain.json(prompt, "You operate a Windows program through its screen. JSON only.", max_tokens=500)
    goals = [str(g).strip() for g in (obj or {}).get("goals", []) if str(g).strip()]
    return goals[:12] or [task]


TYPE_RX = re.compile(r"^\s*(?:type|enter|write)\s+(?:the\s+(?:words?|text)\s+)?[\"\u201c'](.+?)[\"\u201d'](?:\s+(?:in|into|as)\s+the\s+(title|subtitle|heading|body))?\s*$", re.I)


def direct_type(session: Any, goal: str) -> Any:
    """A goal that says exactly which text to type goes straight to the window's text area (no model call), then is CHECKED: the words must be readable on the window afterwards."""
    m = TYPE_RX.match(goal)
    if not m:
        return None
    from core_organs.agent_executor import StepRecord
    text = m.group(1)
    t0 = time.perf_counter()
    where = (m.group(2) or "").lower()
    field = None if where else empty_field(session)
    if field is not None:                                                  # a form field the last step opened (Find / Replace with ...) takes the text, in order, before the document does
        try:
            vp = field.GetValuePattern()
            vp.SetValue(text)
            time.sleep(0.4)
            if text in (vp.Value or ""):
                return StepRecord(goal, "done", source="direct", effect=f"typed into the field '{field.Name}'; its value now holds the words", ms=round((time.perf_counter() - t0) * 1000, 1))
        except Exception:
            pass
    try:
        ok = bool(session.app.type_text(text, where=where)) if where else bool(session.app.type_text(text))
    except TypeError:
        ok = bool(session.app.type_text(text))
    time.sleep(0.6)
    seen = read_back(session).lower()
    words = [w for w in re.findall(r"\w+", text.lower()) if len(w) > 2]
    hit = bool(words) and sum(1 for w in words if w in seen) >= max(1, len(words) // 2)
    if not hit and not where:                                              # the words did not land: take the keyboard focus (click the text area), start the field clean and type once more
        with contextlib.suppress(Exception):
            session.app.focus_editor()
            session.app.clear_text()
            ok = bool(session.app.type_text(text))
            time.sleep(0.6)
            seen = read_back(session).lower()
            hit = bool(words) and sum(1 for w in words if w in seen) >= max(1, len(words) // 2)
    return StepRecord(goal, "done" if (ok and hit) else "no_effect", source="direct", effect="typed into the text area; the words are readable on the window" if hit else "the text could not be read back from the window",
                      reason="" if hit else "no_effect", ms=round((time.perf_counter() - t0) * 1000, 1))


def small_fields(session: Any) -> List[Any]:
    """The small text fields of the window and its flyouts (Find, Replace with, a search box ...), top-to-bottom, left-to-right, one per distinct field; the document's own big text area is not one. Read straight from the
    accessibility tree (text fields are not in the list of pressable controls)."""
    import uiautomation as auto
    out: List[Any] = []
    with contextlib.suppress(Exception):
        from core_organs import headless_input as hin
        ed = None
        with contextlib.suppress(Exception):
            ed = session.app._editor()
        edr = ed.BoundingRectangle if ed is not None else None
        seen = set()
        roots = [session.app.hwnd] + list(hin.popup_windows(session.app.hwnd)[:3])
        for hw in roots:
            try:
                for c, _d in auto.WalkControl(auto.ControlFromHandle(hw), maxDepth=14):
                    if c.ControlTypeName not in ("EditControl", "ComboBoxControl") or c.IsOffscreen:
                        continue
                    r = c.BoundingRectangle
                    if r.width() < 20 or r.height() < 10 or r.height() > 120:
                        continue
                    if edr is not None and r.width() * r.height() >= 0.5 * edr.width() * edr.height():
                        continue
                    key = (c.Name, r.left // 6, r.top // 6)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(c)
            except Exception:
                continue
    return sorted(out, key=lambda c: (round(c.BoundingRectangle.top / 12), c.BoundingRectangle.left))


def field_id(ctl: Any) -> str:
    r = ctl.BoundingRectangle
    return f"{ctl.Name}|{ctl.AutomationId}|{r.left // 6}|{r.top // 6}"


def empty_field(session: Any) -> Any:
    """The text field the LAST step opened, in order: a Find / Replace-with / search field that was not on the window before that step and has not been filled yet takes the text (even when the app pre-filled it with an old
    search); with no such field, the first EMPTY small field; with none, None (the document's text area takes a bare 'type')."""
    with contextlib.suppress(Exception):
        fields = small_fields(session)
        new = getattr(session, "_new_fields", set())
        filled = getattr(session, "_filled_fields", set())
        for c in fields:
            fid = field_id(c)
            if fid in new and fid not in filled:
                session._filled_fields = filled | {fid}
                return c
        for c in fields:
            vp = c.GetValuePattern()
            if vp is not None and not vp.IsReadOnly and not (vp.Value or "").strip() and field_id(c) not in filled and not new:
                return c
    return None


def read_back(session: Any) -> str:
    """What the window shows after the job: the names / values of its controls (UI Automation) and the words OCR reads from a fresh picture of it. The check of the result is made on this, not on the plan."""
    parts: List[str] = []
    img = None
    with contextlib.suppress(Exception):
        img, origin = session.app.grab(popups=True)
        parts += [c["name"] for c in session.app.controls(origin, img.size) if c.get("name")]
        for c in session.app.controls(origin, img.size):
            with contextlib.suppress(Exception):
                v = c["ctl"].GetValuePattern().Value
                if v:
                    parts.append(str(v))
    if img is not None:
        with contextlib.suppress(Exception):
            import pytesseract
            from PIL import ImageOps
            g = img.convert("L")
            parts.append(pytesseract.image_to_string(g, config="--psm 11"))
            big = g.resize((g.width * 2, g.height * 2))                       # small / pale text (a slide's subtitle, a dark theme) needs a second and third look: enlarged, and inverted
            parts.append(pytesseract.image_to_string(big, config="--psm 11"))
            parts.append(pytesseract.image_to_string(ImageOps.invert(big), config="--psm 11"))
    with contextlib.suppress(Exception):                                  # the document's own object model lists ALL its text (every shape of every slide, the whole body, every used cell), selected or not
        from core_organs import office_om as OM
        om_text = OM.text_of(session.app.hwnd)
        if om_text:
            parts.append(om_text)
    with contextlib.suppress(Exception):                                  # a slide's text is not in the UI tree and is small on the canvas: read the slide itself, enlarged
        if re.search(r"powerpoint|impress|slides", str(getattr(session.app, "name", "")), re.I):
            got = session.app.slide_rect()
            if got:
                import pytesseract
                from PIL import ImageOps
                crop = got[1].convert("L")
                big = crop.resize((crop.width * 3, crop.height * 3))
                for psm in ("6", "4"):                                    # the rotate handle under a title can break one reading and not the other
                    parts.append(pytesseract.image_to_string(big, config="--psm " + psm))
                parts.append(pytesseract.image_to_string(ImageOps.invert(big), config="--psm 6"))
    return re.sub(r"\s+", " ", " ".join(parts))[:20000]


def docx_text(path: str) -> str:
    """The words of a .docx / .pptx / .xlsx (read from its XML), to check that a saved deliverable contains what the job asked."""
    try:
        with zipfile.ZipFile(path) as z:
            xml = " ".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith(".xml") and ("word/" in n or "ppt/slides/" in n or "xl/sharedStrings" in n))
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml))
    except Exception:
        return ""
