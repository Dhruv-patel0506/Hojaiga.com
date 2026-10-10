"""
professor.apprun -- RUN AN APPLICATION'S USER GUIDE against the real application, one application at a time, until it is finished.

    launch an OWNED instance (hidden / minimized, parked off-screen, never the user's own window; its saved state protected) -> read it (accessibility tree to full depth, the vision model's
    scan, every flyout opened and read - drawn as annotated pictures) -> harvest its catalog and decide what kind of software it is -> turn the indexed guide into PROCEDURES -> perform each
    procedure through the Executor (hotkeys over pixels, every step verified by a before/after delta and optionally by the vision model), the virtual mouse gliding to each control (database
    trace) -> when a procedure fails, say WHY, apply the remedy that fits that reason, and run it again -> every attempt is a row in the history database (transitions, guide_runs, pointer
    traces) and every row trains the ML models.

An application is FINISHED when every procedure the guide describes for it has either passed, been blocked on purpose (a step that needs a human yes: Save, Delete, Send, a gesture a toolkit
cannot take headlessly ...), been skipped WITH a reason (it names no control this application has), or been diagnosed with a concrete cause that remedies could not remove (the LEDGER).

NOTHING HERE IS SPECIFIC TO AN APPLICATION. Which applications to run and what part of the guide a scenario favours is data (data/apprun_apps.json); launching, state protection, the DevTools route
for Chromium-family windows, opening flyouts, safety and every remedy are derived from the application itself (professor.launcher, state_protect, menus, adapters, safety).

Safety, always: input goes only to a window THIS run launched (Effector owned=True), headless (window messages / UI Automation / DevTools), the user's foreground window is handed back, documents
are never saved, and applications that hold the user's accounts (messengers) run in `navigate` mode - viewing only.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import time
import traceback
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import config as CFG
from . import safety
from . import runui
from .schema import fold

OUT_DIR = os.path.join(CFG.DATA_DIR, "apprun")
APPS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "apprun_apps.json")

# verbs that must never be performed without a human: they write files, leave the machine or touch the user's account
DENY_RX = re.compile(r"\b(save|save as|save all|export|print|publish|share|send|email|upload|sign in|log ?in|sign out|log ?out|uninstall|delete|erase|format (?:the )?(?:drive|disk|partition|volume|card)|restore defaults|reset)\b", re.I)
DENY_WORDS = ["save", "save as", "save all", "export", "print", "publish", "share", "send", "email", "upload", "sign in", "log ?in", "sign out", "log ?out", "uninstall", "delete", "erase", r"format (?:the )?(?:drive|disk|partition|volume|card)",
              "restore defaults", "reset"]


ALWAYS_DENY = [r"auto ?save"]          # continuous saving to the person's cloud storage: never part of a sandboxed run


def deny_rx(sandbox_files: bool, doc_editor: bool) -> "re.Pattern":
    """What is never done without a human. With a file sandbox (professor.dialogs) saving and exporting are safe - the dialog is forced into the sandbox; in a throw-away editor document deleting /
    erasing a selection harms nothing. Printing, publishing, sharing, sending, uploading and sign-in stay human."""
    drop = set()
    if sandbox_files:
        drop |= {"save", "save as", "save all", "export"}
    if doc_editor:
        drop |= {"delete", "erase"}
    return re.compile(r"\b(" + "|".join([w for w in DENY_WORDS if w not in drop] + ALWAYS_DENY) + r")\b", re.I)


# in an application that holds the user's own account or data (navigate mode) anything that changes or sends something
NAV_FORBID_RX = re.compile(r"\b(send|reply|forward|delete|remove|clear|erase|block|report|leave|exit|quit|log ?out|sign ?out|deactivate|unlink|archive|mute|pin|star|unstar|mark|call|video|voice|record|attach|upload|"
                           r"camera|share|post|publish|invite|join|create|add|new (chat|group|message|community)|edit|rename|change|save|submit|confirm|purchase|buy|pay|subscribe|follow|unfollow|react|emoji|gif|sticker)\b", re.I)
REVEAL_RX = re.compile(r"^(?:show|expand|unhide|pin|open)\s+(?:the\s+)?(?:toolbar|tool bar|ribbon|tools|command bar|side ?bar|panel|properties|options bar)\b", re.I)
ACCOUNT_RX = re.compile(r"\b(microsoft account|google account|sign(?:ed)? in|log(?:ged)? in|subscription|ai credits|credits|copilot\+? pc|requires? (?:an )?account|premium)\b", re.I)


def safety_blocked(label: str) -> bool:
    return safety.classify(label) in ("unsafe", "sensitive")


class RevealTainted(Exception):
    """Exploring the options left the application in a state that could not be proved to be its starting state."""


@dataclass
class AppSpec:
    key: str                       # the run's name / registry key (also the guide key unless guide_key says otherwise)
    name: str                      # what the system calls it (Start menu entry, program name)
    tier: int = 0
    mode: str = "full"             # full | navigate (an application that holds the user's account: viewing only)
    vision_verify: bool = False    # ask the vision model after each step whether the expected result is visible
    max_tasks: int = 30
    guide_key: str = ""            # the guide to read when it differs from `key` (one guide, two scenarios)
    focus: str = ""                # a scenario's interest: procedures whose goal / citation match come first
    scenario: str = ""
    notes: str = ""


def load_specs(path: str = APPS_JSON) -> Dict[str, AppSpec]:
    with open(path, "r", encoding="utf-8") as fh:
        rows = json.load(fh).get("apps", [])
    out: Dict[str, AppSpec] = {}
    for r in rows:
        r = {k: v for k, v in r.items() if k in AppSpec.__dataclass_fields__}
        out[r["key"]] = AppSpec(**r)
    return out


SPECS: Dict[str, AppSpec] = load_specs()
TIERS: Dict[int, List[str]] = {}
for _s in SPECS.values():
    TIERS.setdefault(_s.tier, []).append(_s.key)


def spec_for(name: str, mode: str = "full") -> AppSpec:
    """ANY application, by key or by name. A listed one keeps its plan (tier, scenario, focus); anything else gets a spec made from what the name is: the guide corpus catalog maps a process / product name
    to its guide key, otherwise the name itself is the key - the launcher then resolves it from the machine (Start menu, packages, install folders) and the guide finder looks for its guide."""
    n = (name or "").strip()
    if n in SPECS:
        return SPECS[n]
    low = n.lower()
    for s in SPECS.values():
        if low in (s.name.lower(), s.key.lower()):
            return s
    key, display, tier = re.sub(r"[^a-z0-9]+", "", low) or "app", n, 0
    try:
        from .knowledge import guide_corpus as GCP
        for a in GCP.load_catalog():
            procs = [p.lower().rsplit(".", 1)[0] for p in a.get("processes", [])]
            if low in (a["key"].lower(), a["name"].lower()) or low in procs:
                key, display, tier = a["key"], a["name"], int(a.get("tier", 0) or 0)
                break
    except Exception:
        pass
    if key in SPECS:
        return SPECS[key]
    return AppSpec(key=key, name=display, tier=tier, mode=mode, vision_verify=True, notes="made from the name (not in the test plan)")


class _Visible:
    """Stands in for BackgroundSession when the window is deliberately left on screen (a demonstration with the virtual cursor shown)."""
    mode = "visible"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def lay_out(self, settle_s: float = 1.2) -> bool:
        return False


# ------------------------------------------------------------------------------------------------------------------ the run
@dataclass
class Attempt:
    n: int
    status: str                  # ok | blocked | ungrounded | no_effect | refused | failed | error
    why: str = ""
    remedy: str = ""
    steps: int = 0
    done: int = 0
    seconds: float = 0.0
    by: str = ""
    results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TaskResult:
    goal: str
    cite: str
    source: str
    steps_in_guide: int
    grounded: float
    attempts: List[Attempt] = field(default_factory=list)
    final: str = "pending"       # ok | blocked | failed | skipped

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AppRun:
    def __init__(self, spec: AppSpec, *, history: Any = None, skills: Any = None, index: Any = None, learner: Any = None, log: Optional[Callable[[str], None]] = None,
                 max_attempts: int = 3, vision: bool = True, overlay_visible: bool = False, settle_s: float = 2.5, phases: Sequence[str] = ("guide",), echo: bool = True,
                 out_dir: Optional[str] = None, visible: bool = False):
        from . import history as HS, skills as SK
        from .knowledge import manual_rag as MR
        from .ml import get_learner
        self.spec = spec
        self.gkey = spec.guide_key or spec.key
        self.adapter: Any = None
        self.history = history or HS.library()
        self.skills = skills or SK.library()
        self.index = index or MR.ManualIndex()
        self.learner = learner or get_learner()
        try:
            self.learner.attach(self.history, catch_up=False)
        except Exception:
            pass
        self.ui = runui.ConsoleUI(spec.key, spec.tier, echo=echo)
        self.log = log or (lambda s: None)
        self.max_attempts = max_attempts
        self.vision = vision
        self.visible = visible                                                 # leave the window on screen (so the virtual cursor can be watched) instead of parking it
        self.overlay_visible = overlay_visible
        self.settle_s = settle_s
        self.phases = tuple(phases)
        self.target: Any = None
        self.guard: Any = None
        self.stamp = time.strftime("%Y%m%d_%H%M%S")
        self.run_dir = out_dir or os.path.join(OUT_DIR, f"{spec.key}_{self.stamp}")             # created when the first picture / report is written
        self._cp_n = 0
        self.hwnd = 0
        self.bg: Any = None
        self.fx: Any = None
        self.ex: Any = None
        self.cat: Any = None
        self.sm: Any = None
        self.arch: Dict[str, Any] = {}
        self.sess: Any = None
        self.profile: Any = None
        self.report: Dict[str, Any] = {"app": spec.key, "name": spec.name, "tier": spec.tier, "mode": spec.mode, "scenario": spec.scenario, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "phases": {}}
        self.tasks: List[TaskResult] = []
        self.ledger: List[Dict[str, Any]] = []
        self._revealed: List[str] = []
        self._popups0: List[int] = []
        self._flyouts = 0
        self._surf = 0
        self._no_reveal = False
        self.sandbox: Any = None
        self.dialogs: Any = None
        self.clip: Any = None
        self._t_run = time.time()

    def say(self, msg: str) -> None:
        self.ui.note(msg)
        self.log(msg)

    # ----------------------------------------------------------------------------------------------- launch
    def start(self) -> bool:
        from core_organs import background_window as bw, headless_input as hin
        from core_organs.atlas import scanner as SC
        from . import launcher as LN, state_protect as SPT
        t0 = time.time()
        self.target = LN.resolve(self.spec.name)
        self.guard = SPT.StateGuard(self.spec.name, self.target.appid)
        self.report["phases"]["target"] = {"display": self.target.display, "id": self.target.appid, "exe": self.target.exe, "packaged": self.target.packaged, "chromium": self.target.chromium}
        self.report["phases"]["state"] = self.guard.before()
        bridge_args: List[str] = []
        self.bridge = None
        try:                                                                   # an application with an embedded scripting engine is started with the Professor's bridge
            import tempfile
            from .adapters import script_bridge as SB
            fam, real = SB.scripting_exe(self.target.exe) if (self.target.exe and not self.target.chromium) else ("", "")
            if fam:
                from . import dialogs as DG0
                if self.sandbox is None:
                    self.sandbox = DG0.Sandbox(self.spec.key, self.stamp)                       # the one folder the application may be told to read from / write to through its own scripting engine
                self.bridge, bridge_args = SB.ScriptBridge.prepare(tempfile.mkdtemp(prefix="hojaiga_bridge_"), fam, self.sandbox.root)
                self._bridge_exe = real
        except Exception as exc:
            self.report["phases"]["bridge"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        info = LN.launch_owned(self.target, self.guard, exe=getattr(self, "_bridge_exe", ""), args=bridge_args) if bridge_args else LN.launch_owned(self.target, self.guard)
        self.report["phases"]["launch"] = {k: v for k, v in info.items() if k != "trace"}
        self.hwnd = int(info.get("hwnd") or 0)
        if not (info.get("launched") and self.hwnd):
            self.ui.phase("launch", self.ui.c("failed", f"could not start an owned instance: {info.get('notes')}"))
            return False
        self.ui.phase("launch", f"owned window {self.hwnd} · {info.get('title', '')[:44]!r} · {info.get('launch_s')}s" + (f" · {self.target.chromium} (DevTools route)" if self.target.chromium else ""))
        if self.visible:
            import ctypes
            u = ctypes.windll.user32
            u.ShowWindow(self.hwnd, 9)                                          # SW_RESTORE
            u.SetWindowPos(self.hwnd, 0, 80, 60, 1180, 780, 0x0010 | 0x0040)      # SWP_NOACTIVATE | SWP_SHOWWINDOW
            self.bg = _Visible()
        else:
            self.bg = bw.BackgroundSession(self.hwnd)
        self.bg.__enter__()
        self.report["phases"]["park"] = getattr(self.bg, "mode", "?")
        self.checkpoint("launched")
        from . import perception_ladder as PL
        hwnd2, nodes, prep = PL.tree_ladder(self.hwnd, self.bg, title_hint=str(info.get("title") or (self.target.display if self.target else "") or ""))
        if hwnd2 and hwnd2 != self.hwnd:                                        # the launcher's window was replaced by the real main window: park that one instead
            with contextlib.suppress(Exception):
                self.bg.__exit__(None, None, None)
            self.hwnd = hwnd2
            self.bg = _Visible() if self.visible else bw.BackgroundSession(self.hwnd)
            self.bg.__enter__()
            self.report["phases"]["park"] = getattr(self.bg, "mode", "?")
        self.report["phases"]["perception"] = prep
        self.report["phases"]["tree"] = {"nodes": len(nodes), "waited_s": prep["attempts"][-1]["s"] if prep["attempts"] else 0.0, "frame_only": prep["used"] == "vision-needed"}
        if prep["used"] != "tree":
            self.ui.phase("tree", f"tree ladder: {prep['used']} after {len(prep['attempts'])} rung(s) - " + "; ".join(f"{a['how']} -> {a['nodes']}" for a in prep["attempts"][-3:]))
        ws = self._open_blank_workspace(nodes)
        if ws:
            self.report["phases"]["workspace"] = ws
            self.ui.phase("workspace", f"start screen -> '{ws.get('chosen')}' ({ws.get('how')}) · {ws.get('nodes_after')} nodes")
        self.report["phases"]["start_s"] = round(time.time() - t0, 1)
        try:
            self._popups0 = list(hin.popup_windows(self.hwnd))
        except Exception:
            self._popups0 = []
        return True

    def _ensure_parked(self) -> str:
        """An application can MINIMIZE its own frame on a state change (measured: PowerPoint after its start screen); a minimized window exposes only its frame to UI Automation. Put it back in
        the parked (laid-out, off-screen, unfocused) state. Returns what was done ('' when nothing was needed)."""
        import ctypes
        from core_organs import background_window as bw
        if self.visible or not self.hwnd or not ctypes.windll.user32.IsIconic(self.hwnd):
            return ""
        with contextlib.suppress(Exception):
            self.bg.__exit__(None, None, None)
        self.bg = bw.BackgroundSession(self.hwnd)
        self.bg.__enter__()
        for _ in range(20):
            time.sleep(0.3)
            if not ctypes.windll.user32.IsIconic(self.hwnd):
                break
        time.sleep(1.0)
        return f"the application minimized itself; parked again ({getattr(self.bg, 'mode', '?')})"

    BLANK_RX = re.compile(r"(?i)^(blank|new blank|empty)\b")

    def _open_blank_workspace(self, nodes: Sequence[Any]) -> Dict[str, Any]:
        """An application that opens on a START screen (templates, recent files) instead of a document: choose its 'Blank ...' entry, so the guide runs on a fresh throw-away document.
        Recognised by wording ('Blank ...', 'New blank ...', 'Empty ...') on an invokable list item / button while no document area exists yet - never by the application's name."""
        from .effectors import Effector
        from core_organs import fast_uia
        if any(n.ctype == "DocumentControl" for n in nodes):
            return {}
        cand = [n for n in nodes if n.name and self.BLANK_RX.match(n.name.strip()) and n.role in ("listitem", "button", "hyperlink") and not n.offscreen and "invoke" in (n.pats or [])]
        if not cand:
            return {}
        from core_organs import universal_scan as us, background_window as bw
        from . import perception_ladder as PL
        pid = PL._pid(self.hwnd)
        before = set(us._top_windows())
        fx = Effector(self.hwnd, allow_input=True, owned=True)
        with fx.focus_watch():
            ok, how = fx.node(cand[0])
        n_after = len(nodes)
        moved = 0
        end = time.time() + 12.0
        while time.time() < end:
            time.sleep(0.15 if not moved else 0.5)                                # polled fast: a new window is parked within a fraction of a second
            # an application may open the new document in a NEW top-level window (the start screen's window closes or stays a stub): follow it and park it AT ONCE
            fresh = [h for h, (wpid, _cls, title) in us._top_windows().items() if h not in before and wpid == pid and title and h != self.hwnd]
            if fresh:
                nh = max(fresh, key=lambda h: (lambda r: (r[2] - r[0]) * (r[3] - r[1]))(bw._rect(h)))
                with contextlib.suppress(Exception):
                    self.bg.__exit__(None, None, None)
                self.hwnd = moved = nh
                self.bg = _Visible() if self.visible else bw.BackgroundSession(self.hwnd)
                self.bg.__enter__()
                with contextlib.suppress(Exception):
                    bw.mark_ours(nh)
                time.sleep(1.0)
            now = fast_uia.snapshot(self.hwnd, timeout_ms=6000) or []
            n_after = len(now)
            if any(n.ctype == "DocumentControl" for n in now) or n_after > len(nodes) * 1.5:
                break
        out = {"chosen": cand[0].name, "ok": ok, "how": how, "nodes_before": len(nodes), "nodes_after": n_after}
        rp = self._ensure_parked()
        if rp:
            out["reparked"] = rp
            out["nodes_after"] = len(fast_uia.snapshot(self.hwnd, timeout_ms=6000) or [])
        if moved:
            out["followed_new_window"] = moved
            self.report["phases"]["park"] = getattr(self.bg, "mode", "?")
        return out

    # ----------------------------------------------------------------------------------------------- pictures
    def _save(self, tag: str, img: Any) -> str:
        try:
            os.makedirs(self.run_dir, exist_ok=True)
            p = os.path.join(self.run_dir, tag + ".png")
            img.save(p)
            return p
        except Exception:
            return ""

    def checkpoint(self, tag: str) -> str:
        """A plain picture of the application (its window plus open pop-ups, as it really looks) at a named point of the run, kept in checkpoints/ with the others. Never raises."""
        try:
            from . import capture as CAP
            from core_organs import headless_input as hin
            if not self.hwnd:
                return ""
            fr = CAP.grab_composite(self.hwnd, hin.popup_windows(self.hwnd)[:6])
            if fr is None:
                return ""
            self._cp_n += 1
            os.makedirs(os.path.join(self.run_dir, "checkpoints"), exist_ok=True)
            name = f"cp_{self._cp_n:02d}_{re.sub(r'[^A-Za-z0-9_.-]+', '_', tag)[:50]}.png"
            fr.image.convert("RGB").save(os.path.join(self.run_dir, "checkpoints", name))
            self.report.setdefault("checkpoints", []).append({"n": self._cp_n, "tag": tag, "file": "checkpoints/" + name, "at_s": round(time.time() - self._t_run, 1)})
            return name
        except Exception:
            return ""

    def shoot_scan(self, tag: str, sm: Any, img: Any) -> None:
        """The annotated scan: boxes by who found each control (tree / text / shape / vision model / memory), red = unnamed."""
        from . import viz
        if img is None or sm is None:
            return
        self._save(tag, viz.with_legend(viz.annotate(img, sm)))

    def shoot_tree(self, tag: str) -> Dict[str, Any]:
        """The accessibility tree drawn level by level (depth histogram below the picture)."""
        from . import capture as CAP, viz
        from core_organs import fast_uia
        try:
            nodes = fast_uia.snapshot(self.hwnd, timeout_ms=6000) or []
            fr = CAP.grab_window(self.hwnd, isolated=True)
            if fr is None or not nodes:
                return {}
            self._save(tag, viz.tree_overlay(fr.image, fr.origin, nodes))
            hist: Dict[int, int] = {}
            roles: Dict[str, int] = {}
            for n in nodes:
                hist[n.depth] = hist.get(n.depth, 0) + 1
                roles[n.role] = roles.get(n.role, 0) + 1
            return {"nodes": len(nodes), "levels": len(hist), "by_depth": dict(sorted(hist.items())), "top_roles": dict(sorted(roles.items(), key=lambda kv: -kv[1])[:8])}
        except Exception:
            return {}

    def on_flyout(self, opener: Any, new_nodes: List[Any]) -> None:
        """A flyout is open: record what it holds. A parked WinUI pop-up paints nothing for any screenshot API, so the picture is DRAWN from the accessibility tree (name, accelerator, rectangle);
        a pop-up that does render is photographed and read with the vision pipeline as well."""
        if self._flyouts >= 24:
            return
        from . import capture as CAP, viz
        from core_organs import headless_input as hin, fast_uia
        from .privacy import looks_private
        if any(looks_private(getattr(n, "name", "") or "") for n in new_nodes):
            self.report.setdefault("privacy", []).append(f"flyout of '{opener.name}' lists the person's open windows: not photographed, its window titles not recorded")
            return
        try:
            pops = hin.popup_windows(self.hwnd)[:6]
            if not pops:
                return
            self._flyouts += 1
            tag = f"flyout_{self._flyouts:02d}_{re.sub(r'[^A-Za-z0-9]+', '_', opener.name)[:24]}"
            self._save(tag, self._popup_picture(pops, f"{opener.name} flyout"))
        except Exception:
            pass

    @staticmethod
    def _popup_picture(pops: Sequence[int], title: str) -> Any:
        """All open pop-up windows of the application in ONE picture (a submenu opens beside its parent flyout, so the picture covers the union of their rectangles)."""
        from . import capture as CAP, viz
        from core_organs import fast_uia
        from .dialogs import is_heavy_dialog
        nodes: List[Any] = []
        boxes = []
        for p in [q for q in pops if not is_heavy_dialog(q)] or list(pops)[:1]:
            nodes += fast_uia.snapshot(p, timeout_ms=3000) or []
            boxes.append(CAP.window_info(p).box)
        x1, y1 = min(b.x1 for b in boxes), min(b.y1 for b in boxes)
        x2, y2 = max(b.x2 for b in boxes), max(b.y2 for b in boxes)
        return viz.render_popup(nodes, (x2 - x1, y2 - y1), title, (int(x1), int(y1)))

    def on_surface(self, kind: str, cand: Any, new_nodes: List[Any]) -> None:
        """A dialog / page / pane opened by a clicked option is OPEN right now. A dialog (a window of its own) is drawn from its tree like a flyout; a page or pane that replaced part of the main
        window gets the annotated scan of the window, so the picture shows what the click revealed."""
        if self._surf >= 24:
            return
        from .privacy import looks_private
        if any(looks_private(getattr(n, "name", "") or "") for n in new_nodes):
            self.report.setdefault("privacy", []).append(f"surface '{cand.label}' shows the person's open windows: not photographed")
            return
        from . import capture as CAP, viz
        from core_organs import headless_input as hin, fast_uia
        self._surf += 1
        tag = f"option_{self._surf:02d}_{kind}_{re.sub(r'[^A-Za-z0-9]+', '_', cand.label)[:24]}"
        try:
            pops = [p for p in hin.popup_windows(self.hwnd)[:6] if p not in self._popups0]
            if kind == "dialog" and pops:
                self._save(tag, self._popup_picture(pops, f"{' > '.join(cand.path + [cand.label])} (dialog)"))
                return
        except Exception:
            pass
        try:
            sm, img, _i = self.sess.look(self.hwnd, mode="quick", force=True)
            self.shoot_scan(tag, sm, img)
        except Exception:
            pass

    # ----------------------------------------------------------------------------------------------- perception
    def perceive(self) -> None:
        """Read the application the way the Professor does: the tree to full depth AND the vision model's scan, side by side, then the catalog and the kind of software."""
        from . import interaction as IA, archetype as AR, harvest as HV
        from .effectors import Effector
        from .executor import Executor, milestone_checker, DOC_EDITOR_ARCHETYPES
        from .session import ProfessorSession
        from .virtual_mouse import VirtualMouse
        t0 = time.time()
        os.environ.setdefault("HOJAIGA_PROF_ML_OBSERVE", "1")
        os.environ.setdefault("HOJAIGA_PROF_YOLO_DEFAULT", "1")
        rp = self._ensure_parked()
        if rp:
            self.ui.note(rp)
        ds = IA.deep_scan(self.hwnd, budget_s=20.0)
        self.profile = ds.profile
        self.report["phases"]["deep_scan"] = ds.to_dict()
        self.ui.phase("tree", f"{ds.profile.family} · {ds.nodes} nodes · {ds.interactive} interactive · depth {ds.depth} · {ds.state}" + (f" · {ds.native_menu_items} native menu items" if ds.native_menu_items else ""))
        self.sess = ProfessorSession(mute=True, overlay="recording", find_guide=False, interactive=False, upgrade=False, watch_state=False)
        blind = (self.report["phases"].get("perception") or {}).get("used") == "vision-needed" or ds.nodes < 8
        self._blind = blind
        vision_up = bool((self.vision or blind) and self.sess.vlm.available())
        t1 = time.time()
        sm, img, info = self.sess.look(self.hwnd, mode="standard" if vision_up else "quick", force=True)
        if blind and not sm.elements:                                          # a blind window that could not even be captured parked: lay it out once and look again
            with contextlib.suppress(Exception):
                self.bg.lay_out(settle_s=1.0)
            sm, img, info = self.sess.look(self.hwnd, mode="standard" if vision_up else "quick", force=True)
        if blind:
            per = self.report["phases"].setdefault("perception", {"attempts": []})
            per["used"] = "vision" if sm.elements else "none"
            per["vision_elements"] = len(sm.elements)
            self.ui.phase("perception", f"accessibility tree blind -> {'vision: ' + str(len(sm.elements)) + ' controls from OCR / icon detector / vision model' if sm.elements else 'vision found nothing either'}")
        self.sm = sm
        named = sm.named() if hasattr(sm, "named") else []
        by_src: Dict[str, int] = {}
        for e in sm.elements:
            for s in set(e.sources or []):
                by_src[s] = by_src.get(s, 0) + 1
        self.report["phases"]["vision_scan"] = {"vision_model": vision_up, "seconds": round(time.time() - t1, 1), "elements": len(sm.elements), "named": len(named), "by_source": by_src, "regions": len(sm.regions),
                                                "path": info.get("path")}
        self.shoot_scan("scan_1_first", sm, img)
        self.ui.phase("scan", f"{'vision + tree' if vision_up else 'tree only'} · {len(sm.elements)} controls ({len(named)} named) · by {by_src} · {round(time.time() - t1, 1)}s")
        cat = HV.harvest_model(sm, self.hwnd, owned=True)
        if len(cat.verbs) < 4:                                             # the scan found nothing nameable: the plain tree harvest is the floor
            cat2 = HV.harvest_tree(self.hwnd, self.spec.key, sm.window_title, sm.process)
            if len(cat2.verbs) > len(cat.verbs):
                cat = cat2
        cat.app_key = self.spec.key
        carried = getattr(self, "_carry", None) or []
        if carried:                                                            # what the first (thrown-away) instance revealed: dialogs, ribbon, menus
            have = {(tuple(v.path), v.label.lower()) for v in cat.verbs}
            cat.verbs += [v for v in carried if (tuple(v.path), v.label.lower()) not in have]
            self.report["phases"]["carried_from_first_instance"] = len(carried)
        self.cat = cat
        try:                                                                   # an application family that publishes its whole command list: catalogued headless, checked against THIS build
            from . import vendor_commands as VC
            if self.target is not None and self.target.exe:
                vrep = VC.merge_into(cat, self.spec.key, self.target.exe)
                if vrep.get("vendor_verbs"):
                    self.report["phases"]["vendor_manifest"] = {k: vrep.get(k) for k in ("family", "progid", "build", "kept", "not_in_this_version", "by_area", "added", "cached", "exe_version")}
                    self.ui.phase("manifest", f"{vrep.get('vendor_verbs')} documented commands verified against build {vrep.get('build') or vrep.get('exe_version')} ({vrep.get('added')} new to the catalog"
                                  + (", cached" if vrep.get("cached") else "") + ")")
        except Exception as exc:
            self.report["phases"]["vendor_manifest"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        self.arch = AR.classify(sm, cat, self.sess.brain)
        cat.archetype = {k: self.arch.get(k) for k in ("id", "name", "confidence", "by")}
        self.report["phases"]["catalog"] = cat.summary()
        self.ui.phase("catalog", f"{len(cat.verbs)} verbs · {cat.summary()['with_shortcut']} with shortcuts · looks like: {self.arch.get('id')} ({self.arch.get('confidence')})")
        self._vision_up = vision_up
        self._make_executor(cat, sm)
        port = int((self.report["phases"].get("launch") or {}).get("cdp_port") or 0)
        if port:
            self._attach_devtools(port)
        try:
            shown = self.reveal_ui()
            if shown:
                self.report["phases"]["revealed"] = shown
                self.ui.phase("reveal", f"collapsed UI shown: {shown} · catalog now {len(self.cat.verbs)} verbs")
        except Exception as exc:
            self.say("reveal failed: " + type(exc).__name__)
        # a RIBBON (recognised by its structure, not by tab names): every tab selected, every group read, every opener of every tab opened and read to depth 3
        rib = None
        ribbon_read: List[Dict[str, Any]] = []
        try:
            from . import ribbon as RB
            allnodes = self.ex._all_nodes()
            if RB.detect(allnodes[: self.ex._main_n] if self.ex._main_n else allnodes) is not None:
                wid = self._widen_parked()                                       # a narrow ribbon folds whole groups into one drop-down: lay the parked (invisible) window out wide first
                if wid:
                    self.report["phases"]["widened"] = wid
                    allnodes = self.ex._all_nodes()
            rib = RB.detect(allnodes[: self.ex._main_n] if self.ex._main_n else allnodes)
            if rib is not None and self.adapter is None and any("ribbon" in (v.sources or []) for v in (getattr(self, "_carry", None) or [])):
                self.ui.phase("ribbon", f"{rib.why} · read by the first instance of this run: carried over, not walked again")
                rib_seen = True
            elif rib is not None and self.adapter is None:
                rr = RB.walk(self.fx, self.ex._all_nodes, cat, rib, budget_s=float(os.environ.get("HOJAIGA_RIBBON_BUDGET", "300")), history=self.history, toolkit=ds.profile.family,
                             on_items=self.on_flyout, log=self.say)
                ribbon_read = rr.pop("read", [])
                self.report["phases"]["ribbon"] = rr
                self.ui.phase("ribbon", f"{rib.why} · structure confirmed by switching tabs: {rr.get('confirmed')} · {len(rr['tabs'])} tabs read · {rr['groups']} groups · {rr['controls']} controls · "
                              f"{rr['opened']}/{rr['openers']} openers opened ({rr['items']} items, {rr['submenus']} submenus) · {rr['seconds']}s")
        except Exception as exc:
            self.report["phases"]["ribbon"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}", "trace": traceback.format_exc()[-600:]}
            self.say("ribbon walk failed: " + self.report["phases"]["ribbon"]["error"])
        # the deep tree: open every opener once (owned window), read its items, close it - a guide speaks in menu paths the tree alone cannot show
        try:
            from . import menus as MN
            mrep = MN.expand_menus(self.fx, self.hwnd, cat, self.ex._all_nodes, budget_s=(8.0 if self.adapter else 120.0), history=self.history, toolkit=ds.profile.family, restore_popups=self._popups0,
                                   on_items=self.on_flyout, ribbon=(False if rib is None else None),
                                   # the ribbon is read by its own walk; the caption row ABOVE its tab strip holds the window's own things (the signed-in person's account, search, window buttons) - not opened
                                   exclude=((lambda n, r=rib: r.contains(n) or n.rect[3] <= r.band[1] + 2) if rib is not None else None))
            read_items = mrep.pop("read", []) + ribbon_read
            self.report["phases"]["menus"] = mrep
            self.ui.phase("menus", f"{mrep['opened']}/{mrep['openers']} openers opened · {mrep['items']} items read · {mrep.get('submenus', 0)} submenus entered · {mrep['seconds']}s"
                          + (f" · problems {mrep['failed'][:2]}" if mrep["failed"] else ""))
            for sk in mrep.get("skipped", [])[:4]:
                self.ui.note(f"left closed: {sk['path']} - {sk['why']}")
            self.report["phases"]["catalog_after_menus"] = cat.summary()
        except Exception as exc:
            read_items = list(ribbon_read)
            self.report["phases"]["menus"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}", "trace": traceback.format_exc()[-600:]}
            self.say("menu expansion failed: " + self.report["phases"]["menus"]["error"])
        # the buttons that open a DIALOG or a whole PAGE (Page setup, Font, Find, Settings ...): click each once, read what appears, leave again and prove the application is back
        surfaces: List[Dict[str, Any]] = []
        if self.adapter is None and not self._no_reveal and os.environ.get("HOJAIGA_REVEAL", "1") != "0":
            try:
                from . import reveal as RV
                big = rib is not None or len(read_items) > 120
                rrep = RV.reveal_surfaces(self.ex, self.fx, self.hwnd, cat, read_items, history=self.history, toolkit=ds.profile.family, archetype=self.arch.get("id", ""), popups0=self._popups0,
                                          on_surface=self.on_surface, reset=self.reset_ui, restore=self._reshow_ui, budget_s=float(os.environ.get("HOJAIGA_REVEAL_BUDGET", "300" if big else "150")),
                                          max_surfaces=int(os.environ.get("HOJAIGA_REVEAL_MAX", "40" if big else "20")), max_depth=3, learner=self.learner, per_surface_s=45.0)
                surfaces = rrep.get("surfaces", [])
                self.report["phases"]["options"] = rrep
                self.ui.phase("options", f"{rrep['opened']}/{rrep['tried']} clicked options opened more ({rrep['dialogs']} dialogs · {rrep['pages']} pages · {rrep['inline']} inline) · {rrep['controls']} new controls · "
                              f"dialog tabs {rrep.get('dialog_tabs', 0)} · nested dialogs {rrep.get('nested_dialogs', 0)} · deepest level {rrep.get('deepest_level', 0)} · left again {rrep['left_ok']}/{rrep['tried']} · {rrep['seconds']}s")
                for sk in rrep.get("skipped", [])[:5]:
                    self.ui.note(f"not clicked: {sk['path']} - {sk['why']}")
                self.report["phases"]["catalog_after_options"] = cat.summary()
                if rrep.get("tainted"):
                    self.ui.phase("options", self.ui.c("failed", rrep["stopped"]))
                    raise RevealTainted(rrep["stopped"])
            except RevealTainted:
                raise
            except Exception as exc:
                self.report["phases"]["options"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}", "trace": traceback.format_exc()[-600:]}
                self.say("option exploration failed: " + self.report["phases"]["options"]["error"])
        try:
            from . import reveal as RV
            self.report["phases"]["ui_map"] = RV.build_map(cat, surfaces)
        except Exception:
            pass
        try:
            sm2, img2, _i = self.sess.look(self.hwnd, mode="quick", force=True)
            self.shoot_scan("scan_2_deep", sm2, img2)
            self.report["phases"]["tree_picture"] = self.shoot_tree("scan_3_tree_levels")
        except Exception:
            pass
        self.report["phases"]["coverage"] = self.button_coverage()
        cv = self.report["phases"]["coverage"]
        self.ui.phase("coverage", f"{cv['tried']}/{cv['eligible']} safe on-screen controls tried ({cv['percent']}%) · {cv['seen']} more seen inside opened menus · by {cv['by']}")
        try:
            cat.save()
            self.history.register_app(self.spec.key, self.spec.name, self.target.exe if self.target else "", ds.profile.family, self.spec.tier, self._guide_docs(), len(cat.verbs), self.spec.notes)
        except Exception:
            pass
        self.report["phases"]["perceive_s"] = round(time.time() - t0, 1)
        self._capture_tabs()
        self.checkpoint("after_scan_home")

    def _make_executor(self, cat: Any, sm: Any) -> None:
        """Effector + Executor + dialog handling + the object-model reroute, bound to the CURRENT owned window (used by perceive, and again after a relaunch with the catalog kept)."""
        from .effectors import Effector
        from .executor import Executor, milestone_checker, DOC_EDITOR_ARCHETYPES
        from .virtual_mouse import VirtualMouse
        family = self.profile.family if self.profile is not None else ""
        self.fx = Effector(self.hwnd, allow_input=True, owned=True)
        pointer = VirtualMouse(self.sess.overlay, self.history, self.spec.key, visible=self.overlay_visible, learner=self.learner)
        vc = milestone_checker(self.sess.vlm) if (self.spec.vision_verify and getattr(self, "_vision_up", False)) else None
        self.ex = Executor(self.hwnd, self.fx, cat, sm, self.sess.brain, owned=True, vision_check=vc, skills=self.skills, guide_index=self.index, archetype=self.arch.get("id", ""),
                           history=self.history, learner=self.learner, toolkit=family, pointer=pointer)
        try:
            from . import workflows as WF
            self.ex.app_words = WF.app_words_for(self.gkey, cat)
        except Exception:
            pass
        self.ex.blind = bool(getattr(self, "_blind", False))                                              # the interface tree is blind: routes through the application's own engine come first
        self.ex.visible = self.visible                                         # a gesture may use synthetic touch only on a window that is on screen
        self.ex.sandboxed = bool(self.guard is not None and (self.guard.tmp_dirs or self.guard.report.get("backed_up")))          # throw-away state: settings-like verbs are harmless here
        # popups, file dialogs and the clipboard: a sandbox folder of the run's own, a driver that completes dialogs with files in it, a clipboard guard that gives the person's clipboard back
        try:
            from . import dialogs as DG
            from .knowledge import guide_steps as GS
            if self.sandbox is None:
                self.sandbox = DG.Sandbox(self.spec.key, self.stamp)
            self.dialogs = DG.DialogDriver(self.fx, self.hwnd, self.sandbox, baseline=self._popups0, history=self.history, toolkit=family, log=self.say)
            self.dialogs.user_files = list(getattr(self, "user_files", []) or [])       # files / folders the PERSON named in the request
            self.dialogs.start_watch()
            if self.clip is None:
                self.clip = DG.ClipboardGuard()
            self.ex.dialogs, self.ex.clip, self.ex.sandbox = self.dialogs, self.clip, self.sandbox
            GS.SANDBOX_FILES = True
        except Exception as exc:
            self.say("dialog handling unavailable: " + type(exc).__name__)
        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else deny_rx(self.dialogs is not None, self.arch.get("id") in DOC_EDITOR_ARCHETYPES)
        if getattr(self, "bridge", None) is not None:                           # the application's own scripting engine: its command registry + a pointer-free route
            try:
                if self.bridge.alive():
                    from .adapters import script_bridge as SB
                    mres = self.bridge.request("menus", timeout=90.0)
                    pverbs = SB.prop_verbs(self.bridge.props())                                    # the SETTINGS its panels draw, at the path they are drawn at (a guide names settings, not commands)
                    verbs = SB.menu_verbs(mres.get("menus", {})) + pverbs + SB.registry_verbs(self.bridge.registry())      # its own menus (real paths) first, then its settings, then every command it declares
                    cat.sources["script-properties"] = len(pverbs)
                    keys = self.bridge.request("keymap", timeout=60.0).get("keys", {})           # the application's own keymap: the shortcut of each command
                    from .harvest import normalize_chord
                    for v in verbs:
                        ks = keys.get(v.aid[7:]) if v.aid.startswith("script:") else None
                        if ks:
                            plain = [c for c, km in ks if km in ("Window", "Screen", "Object Mode", "3D View", "Mesh")] or [c for c, _km in ks]
                            v.shortcut = normalize_chord(plain[0])
                    have = {(tuple(v.path), v.label.lower()) for v in cat.verbs}
                    cat.verbs += [v for v in verbs if (tuple(v.path), v.label.lower()) not in have]
                    cat.sources["script-registry"] = len(verbs)
                    cat.sources["script-keymap"] = sum(1 for v in verbs if v.shortcut)
                    self.ex.script_bridge = self.bridge
                    self.report["phases"]["bridge"] = {"alive": True, "commands": len(verbs)}
                    self.ui.phase("scripting", f"the application's own scripting engine answers: {len(verbs)} commands from its registry (label + description), a pointer-free route for commands and view gestures")
                    from . import gestures as GE
                    GE.save_trait(self.spec.key, "scripting", True)
                else:
                    self.report["phases"]["bridge"] = {"alive": False}
            except Exception as exc:
                self.report["phases"]["bridge"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        try:                                                                   # the reroute: the application's own automation object model, bound to THIS owned window
            from .adapters.object_model import OfficeModel
            if (self.report["phases"].get("vendor_manifest") or {}).get("family") == "office" and self.target is not None:
                self.ex.object_model = OfficeModel.for_window(self.hwnd, self.target.exe)
                self.report["phases"]["object_model"] = bool(self.ex.object_model)
                if self.ex.object_model is not None:
                    self.ui.phase("reroute", "the application's object model answers on this window: every catalogued command can also be run through it when the UI route fails")
        except Exception as exc:
            self.report["phases"]["object_model"] = f"{type(exc).__name__}: {str(exc)[:100]}"

    def _alive(self) -> str:
        """'' when the owned instance is usable; else why not (its window is gone - it crashed or closed itself - or it stopped responding)."""
        import ctypes
        from .reveal import app_hung
        if not self.hwnd or not ctypes.windll.user32.IsWindow(self.hwnd):
            return "the application's window is gone (it closed or crashed)"
        try:
            if app_hung(self.hwnd):
                time.sleep(3.0)
                if app_hung(self.hwnd):
                    return "the application stopped responding"
        except Exception:
            pass
        return ""

    def _revive(self, why: str) -> bool:
        """The owned instance died or hung during a procedure: record it (the procedure that was running keeps its failure), start a FRESH owned instance and go on with the same catalog -
        what was learnt about the interface is still true; only the window is new. Never more than twice per run."""
        rel = self.report.setdefault("relaunches", [])
        if len(rel) >= 2:
            return False
        rel.append({"after_tasks": len(self.tasks), "why": why})
        self.ui.phase("relaunch", self.ui.c("failed", f"{why}: starting a fresh owned instance (catalog kept)"))
        cat, sm = self.cat, self.sm
        self._teardown()
        if not self.start():
            rel[-1]["result"] = "launch failed"
            return False
        self._ensure_parked()
        if any("ribbon" in (v.sources or []) for v in cat.verbs):
            self._widen_parked()
        self.dialogs, self.clip = None, None
        self._make_executor(cat, sm)
        self._capture_tabs()
        rel[-1]["result"] = f"fresh instance {self.hwnd}"
        return True

    def _capture_tabs(self) -> None:
        try:
            nodes = self.ex._all_nodes()
            self._tabs0 = {fold(n.name) for n in nodes[: self.ex._main_n or len(nodes)] if n.role == "tabitem" and n.name}
        except Exception:
            self._tabs0 = set()

    def _widen_parked(self, width: int = 2400, height: int = 1000) -> Dict[str, Any]:
        """A PARKED window (off every monitor) is laid out at its own size; ribbons and toolbars fold groups away when it is narrow. Make it wide - nothing of it is on screen, and the
        original placement comes back when the session ends."""
        import ctypes
        from core_organs import background_window as bw
        if getattr(self.bg, "mode", "") != "parked" or not self.hwnd:
            return {}
        try:
            r0 = bw._rect(self.hwnd)
            if r0[2] - r0[0] >= width - 10:
                return {}
            ctypes.windll.user32.SetWindowPos(self.hwnd, 0, 0, 0, width, height, 0x0002 | 0x0004 | 0x0010)        # NOMOVE | NOZORDER | NOACTIVATE
            time.sleep(0.9)
            with contextlib.suppress(Exception):
                bw.sliver(self.hwnd)
            time.sleep(0.6)
            return {"from": [r0[2] - r0[0], r0[3] - r0[1]], "to": [width, height]}
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}

    CLICKABLE = {"button", "menu_item", "dropdown", "tab", "list_item", "radio", "checkbox", "toggle", "tree_item", "link", "hyperlink", "splitbutton"}

    def button_coverage(self) -> Dict[str, Any]:
        """How much of what can safely be clicked was actually TRIED (opened, clicked to reveal, probed) - and how much was only SEEN inside a menu that was opened. Over the controls the
        live application showed (tree / menus / ribbon / dialogs); vendor-manifest commands that were never on screen are not in the denominator."""
        from . import reveal as RV, menus as MN
        tried: Dict[str, set] = {"opened (menus / ribbon openers)": set(), "clicked (dialogs / pages)": set(), "probed": set()}
        m = self.report["phases"].get("menus") or {}
        for k in (m.get("by_opener") or {}):
            tried["opened (menus / ribbon openers)"].add(fold(k.split(" > ")[-1]))
        for k in ((self.report["phases"].get("ribbon") or {}).get("opened_names") or []):
            tried["opened (menus / ribbon openers)"].add(fold(k))
        for t in ((self.report["phases"].get("options") or {}).get("tried_controls") or []):
            tried["clicked (dialogs / pages)"].add(fold(t.split(" > ")[-1]))
        for t in ((self.report["phases"].get("probe") or {}).get("labels") or []):
            tried["probed"].add(fold(t))
        allt = set().union(*tried.values())
        elig = [v for v in (self.cat.verbs if self.cat is not None else []) if (set(v.sources or []) - {"vendor-manifest", "atlas-uimap"}) and v.role in self.CLICKABLE and v.safety == "safe" and v.enabled
                and not RV.EXTERNAL_RX.search(v.label) and not RV.FILEPICK_RX.search(v.label) and not MN.PRIVATE_RX.search(v.label)]
        labels = {fold(v.label) for v in elig}
        hit = labels & allt
        seen = {fold(v.label) for v in elig if set(v.sources or []) & {"menu-expand", "ribbon", "reveal"}} - hit
        return {"eligible": len(labels), "tried": len(hit), "percent": round(100.0 * len(hit) / max(1, len(labels)), 1), "seen": len(seen),
                "by": {k: len(v & labels) for k, v in tried.items()}}

    def _attach_devtools(self, port: int) -> None:
        """A Chromium-family window: read its pages and commands through the DevTools protocol (professor.adapters) in addition to its accessibility tree."""
        try:
            from .adapters.cdp import CdpBrowser
            from .adapters.chromium import ChromiumAdapter
            from .knowledge import guide_card as GCARD
            br = CdpBrowser(port)
            if not br.wait(20.0):
                self.report["phases"]["cdp"] = {"error": "the debugging port never answered"}
                return
            try:
                card = GCARD.build_card(self.gkey, self.index, save=False)
                shortcuts, terms, menus = card.get("shortcuts", {}), [t["term"] for t in card["ui_taxonomy"]["terms"]], card["ui_taxonomy"]["menus"]
            except Exception:
                shortcuts, terms, menus = {}, [], {}
            self.adapter = ChromiumAdapter(br, log=self.say, guide_shortcuts=shortcuts, guide_terms=terms, guide_menus=menus)
            rep = self.adapter.harvest_all(self.cat)
            self.report["phases"]["cdp"] = rep
            self.ex.adapter = self.adapter
            self.ui.phase("devtools", f"{rep.get('commands', 0)} browser commands · {rep.get('pages', 0)} pages read ({rep.get('page_verbs', 0)} controls) · {rep.get('seconds', 0)}s")
        except Exception as exc:
            from .adapters.chromium import BrowserGone
            if isinstance(exc, BrowserGone):
                raise
            self.report["phases"]["cdp"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            self.say("DevTools route failed: " + self.report["phases"]["cdp"]["error"])

    def _guide_docs(self) -> int:
        try:
            return int(self.index.db.execute("SELECT COUNT(*) FROM docs WHERE app=?", (self.gkey,)).fetchone()[0])
        except Exception:
            return 0

    # ----------------------------------------------------------------------------------------------- hidden UI
    def reveal_ui(self) -> List[str]:
        """A toolbar / ribbon / side panel that is collapsed hides the very controls a guide talks about ('click Select'). Show it - and remember how to put it back (the application keeps
        such a preference in the user's own settings, so the run leaves it as it found it)."""
        done: List[str] = []
        for n in self.ex._all_nodes():
            if n.role == "button" and n.name and REVEAL_RX.match(n.name.strip()) and not n.offscreen and n.enabled and not safety_blocked(n.name):
                ok, how = self.fx.node(n)
                if ok:
                    done.append(n.name)
                    self._revealed.append(n.name)
                    time.sleep(0.8)
        if done:
            try:
                self.sm, _i, _f = self.sess.look(self.hwnd, mode="quick", force=True)
                self.ex.refresh_catalog()
            except Exception:
                pass
        return done

    def _reshow_ui(self) -> int:
        """Show the collapsed toolbar / panel again if the application collapsed it (some applications reset it when a settings page is left); same buttons as reveal_ui, nothing new is recorded."""
        n_shown = 0
        for n in self.ex._all_nodes():
            if n.role == "button" and n.name and REVEAL_RX.match(n.name.strip()) and not n.offscreen and n.enabled and not safety_blocked(n.name):
                ok, _how = self.fx.node(n)
                n_shown += 1 if ok else 0
                time.sleep(0.8)
        return n_shown

    def unreveal_ui(self) -> List[str]:
        undone: List[str] = []
        for name in self._revealed:
            opposite = re.sub(r"^(show|expand|unhide|pin|open)\b", lambda m: {"show": "hide", "expand": "collapse", "unhide": "hide", "pin": "unpin", "open": "close"}[m.group(1).lower()], name, flags=re.I)
            for n in self.ex._all_nodes():
                if n.role == "button" and n.name and fold(n.name) == fold(opposite) and not n.offscreen and n.enabled:
                    ok, how = self.fx.node(n)
                    if ok:
                        undone.append(n.name)
                    break
        self._revealed = []
        return undone

    # ----------------------------------------------------------------------------------------------- tasks
    def _launch_rx(self) -> "re.Pattern":
        words = {w for w in re.findall(r"[a-z0-9]+", (self.spec.name + " " + self.spec.key + " " + (self.target.display if self.target else "")).lower()) if len(w) > 2}
        words |= {"app", "application", "start menu", "taskbar", "microsoft store", "windows"}
        alt = "|".join(re.escape(w) for w in sorted(words))
        return re.compile(r"^\s*(?:\d+[.)]\s*)?(?:how (?:do i|to) )?(?:open|start|launch|run|update|install|download|get|find)\b.*\b(?:" + alt + r")\b|\bfrom the (?:start menu|taskbar)\b|\bstart menu\b", re.I)

    def build_tasks(self) -> List[Dict[str, Any]]:
        """The guide's procedures that can be attempted here: the first step grounds in the live catalog (or at least half of the steps do). Every procedure the guide has is accounted for in
        `self.ledger` - attempted, or set aside WITH the reason."""
        from .knowledge import guide_card as GCARD, guide_steps as GS, task_like as TL
        procs = GCARD.procedures(self.gkey, self.index)
        name_words = {w for w in re.findall(r"[a-z0-9]+", (self.spec.name + " " + self.spec.key + " " + (self.target.display if self.target else "")).lower()) if len(w) > 2}
        launch_rx = self._launch_rx()
        out: List[Dict[str, Any]] = []
        cands: List[Dict[str, Any]] = []
        self.ledger = []

        def put(p: Dict[str, Any], disposition: str, why: str, cover: float = 0.0) -> None:
            self.ledger.append({"goal": p["goal"], "cite": p["cite"], "source": p["source"], "steps": len(p["steps"]), "grounded": round(cover, 3), "disposition": disposition, "reason": why})
            try:
                self.history.log_guide_run(self.spec.key, p["source"], p["cite"], p["goal"], len(p["steps"]), cover, False, False, f"{disposition}: " + why, 0)
            except Exception:
                pass

        for p in procs:
            steps = [s for s in p["steps"] if not (s.action == "open" and s.target and {w for w in re.findall(r"[a-z0-9]+", s.target.lower())} <= name_words)]
            if not steps:
                put(p, "skipped", "only says to open the application")
                continue
            if len(steps) < len(p["steps"]) and all(s.chord or s.action in ("press", "type") for s in steps):
                put(p, "skipped", "describes starting the application (Start menu), not using it")
                continue
            if launch_rx.search(p["goal"]) and not any(s.path for s in steps):
                put(p, "skipped", "describes launching / updating the application, not using it")
                continue
            if self.spec.mode == "navigate" and (NAV_FORBID_RX.search(p["goal"]) or any(NAV_FORBID_RX.search(s.raw) for s in steps)):
                put(p, "skipped", "navigate mode: the procedure changes or sends something")
                continue
            if ACCOUNT_RX.search(p.get("text", "")):
                put(p, "blocked", "policy: the section needs the user's account / subscription / a service plan")
                continue
            g = GS.ground(steps, self.cat, self.ex.app_words if self.ex is not None else ())
            if g and all(x.how in GS.EXCLUDED_HOW for x in g):
                put(p, "skipped", "not a procedure of this application / edition: " + (g[0].note or "")[:120])
                continue
            ok = [x for x in g if x.how in GS.GROUNDED_HOW]
            n_ok, n_app = GS.coverage(g)
            cover = n_ok / max(1, n_app)
            if not ok:
                put(p, "skipped", "no step names a control that exists in this application's interface (" + "; ".join((x.note or x.step.raw)[:60] for x in g[:2]) + ")", cover)
                continue
            if cover < 0.5 and g[0].how not in GS.GROUNDED_HOW:                       # a procedure whose FIRST step grounds can ground the rest just in time (dialog fields appear only after the dialog opens)
                put(p, "skipped", f"its first step ('{g[0].step.target or g[0].step.raw[:30]}') matches no control and only {cover:.0%} of the steps do", cover)
                continue
            score = TL.task_score({**p, "steps": steps})
            first = next((x for x in g if x.how in GS.GROUNDED_HOW and x.verb is not None), None)
            if getattr(self.ex, "script_bridge", None) is not None and getattr(self.ex, "blind", False):
                # the interface cannot be read and only the application's own engine can act: a step that names a control the engine does not offer cannot be performed at all
                ui_only = next((x for x in g if x.how in GS.GROUNDED_HOW and x.verb is not None and not str(x.verb.aid).startswith("script:")), None)
                if ui_only is not None:
                    put(p, "skipped", f"step '{(ui_only.step.target or ui_only.step.raw)[:40]}' names a control the application's scripting engine does not offer, and its interface cannot be read (blind)", cover)
                    continue
            cands.append({"goal": p["goal"], "cite": p["cite"], "source": p["source"], "steps": steps, "grounded": round(cover, 3), "text": p.get("text", ""), "task": round(score, 2), "why_ref": TL.explain(p),
                          "_first": (first.verb.aid if first is not None else ""), "_p": p})
        # an application with its own scripting engine can say which commands can run NOW: a procedure whose first command is not available in the starting state (it needs an object, a
        # selection, another mode or an earlier operation that the procedure itself does not make) is set aside WITH that reason instead of using up a slot and failing
        pollable = sorted({c["_first"][7:] for c in cands if c["_first"].startswith("script:") and not c["_first"].startswith("script:rna:")})
        polls: Dict[str, bool] = {}
        if pollable and getattr(self, "bridge", None) is not None and getattr(self.ex, "script_bridge", None) is not None:
            try:
                polls = self.bridge.polls(pollable)
            except Exception:
                polls = {}
        for c in cands:
            aid = c.pop("_first")
            pp = c.pop("_p")
            if aid.startswith("script:") and polls.get(aid[7:]) is False:
                put(pp, "skipped", f"its first command ({aid[7:]}) is not available in the starting state: it needs an object, a selection, another mode or an earlier operation that the procedure does not make", c["grounded"])
                continue
            out.append(c)
        focus = re.compile(self.spec.focus, re.I) if self.spec.focus else None
        # real TASKS first (instructions with a result), reference material (what a menu entry / region means) after them: a guide's index is mostly reference, and attempting it measures nothing
        out.sort(key=lambda t: (0 if (focus and focus.search(t["goal"] + " " + t["cite"])) else 1, 0 if t["task"] >= TL.TASK_THRESHOLD else 1, -t["grounded"], -t["task"], len(t["steps"])))
        seen, uniq = set(), []
        for t in out:
            k = (t["goal"].lower(), t["steps"][0].target.lower())
            if k in seen:
                self.ledger.append({"goal": t["goal"], "cite": t["cite"], "source": t["source"], "steps": len(t["steps"]), "grounded": t["grounded"], "disposition": "skipped", "reason": "duplicate of a procedure already queued"})
                continue
            seen.add(k)
            uniq.append(t)
        for t in uniq[self.spec.max_tasks:]:
            self.ledger.append({"goal": t["goal"], "cite": t["cite"], "source": t["source"], "steps": len(t["steps"]), "grounded": t["grounded"], "disposition": "skipped",
                                "reason": "beyond the per-run task cap" if t["task"] >= TL.TASK_THRESHOLD else "beyond the per-run task cap; also reads as reference material (" + t["why_ref"] + ")"})
        return uniq[: self.spec.max_tasks]

    # ----------------------------------------------------------------------------------------------- doing
    def reset_ui(self) -> None:
        """Back to a clean state between procedures: expanded drop-downs collapsed, stray popups / dialogs closed, menus dismissed, a protocol-driven browser left with one blank tab."""
        from . import menus as MN
        try:
            self.ex._hold_release()
        except Exception:
            pass
        try:
            for n in self.ex._all_nodes():
                if getattr(n, "expand_state", -1) == 1 and n.name and not n.offscreen:
                    MN.collapse(n, deadline_s=1.0)
        except Exception:
            pass
        try:
            self.fx.close_popups(self._popups0)
        except Exception:
            pass
        try:
            for _ in range(2):
                self.fx.key("escape")
                time.sleep(0.15)
        except Exception:
            pass
        try:                                                                   # a MODE a procedure entered (Slide Master view: a contextual tab that was not there at the start) is left by its own Close command
            nodes = self.ex._all_nodes()
            tabs0 = getattr(self, "_tabs0", None)
            extra = [n.name for n in nodes[: self.ex._main_n or len(nodes)] if n.role == "tabitem" and n.name and fold(n.name) not in tabs0] if tabs0 else []
            if extra or self.ex.entered_contexts:
                left = self.ex.leave_contexts(extra)
                if left:
                    self.ui.note("; ".join(left))
        except Exception:
            pass
        if self.adapter is not None:
            try:
                self.adapter.reset()
            except Exception:
                pass
        time.sleep(0.3)

    @staticmethod
    def _judge(rep: Any) -> Tuple[str, str]:
        if rep.ok:
            return "ok", ""
        last = rep.results[-1] if rep.results else None
        if last is None:
            return "failed", rep.stopped or "no step was performed"
        st = last.status
        if st in ("needs_human", "disabled"):
            return "blocked", last.summary
        if st == "unknown":
            if "pointer gesture" in (last.summary or "") or (last.summary or "").startswith("policy:"):
                return "blocked", last.summary
            if "names no control" in (last.summary or ""):
                return "blocked", "underspecified: " + (last.summary or "")
            return "ungrounded", last.summary or rep.stopped
        if st in ("no_effect", "refused"):
            return st, (last.summary + " | tried: " + "; ".join(last.tried[:4]))[:400]
        return "failed", (rep.stopped or st)[:300]

    def _remedy(self, status: str) -> str:
        """The fix that fits the reason (applied before the next attempt). Returns what was done, '' when nothing applies."""
        from core_organs.atlas import scanner as SC
        done: List[str] = []
        self.reset_ui()
        rp = self._ensure_parked()
        if rp:
            done.append(rp)
        if status in ("ungrounded", "no_effect", "refused", "failed"):
            try:
                if getattr(self.bg, "mode", "") == "parked":
                    self.bg.lay_out(settle_s=0.6)
                    done.append("re-laid-out the parked window")
            except Exception:
                pass
            try:
                nodes, waited, frame_only = SC.ensure_tree(self.hwnd, self.bg, max_s=4.0)
                done.append(f"re-read the tree ({len(nodes)} nodes)")
            except Exception:
                pass
        if status == "ungrounded":
            try:
                sm, _img, _info = self.sess.look(self.hwnd, mode="quick", force=True)
                self.sm = sm
                n = self.ex.refresh_catalog()
                done.append(f"re-scanned; {n} new verbs in the catalog")
            except Exception:
                pass
        self.settle_s = min(6.0, self.settle_s + 1.0) if status == "no_effect" else self.settle_s
        if self.dialogs is not None and self.dialogs.needs_prime:                  # a Save dialog was cancelled because it showed a folder outside the sandbox
            try:
                note = self.ex.prime_dialog_folder()
                if note:
                    done.append(note)
            except Exception as exc:
                done.append(f"priming the file dialogs failed ({type(exc).__name__})")
        return "; ".join(done)

    def evidence(self, tag: str) -> str:
        """What the screen looked like when something failed: a picture of the window with its pop-ups, and the windows / controls the tree showed. Kept beside the report."""
        try:
            from . import capture as CAP
            from core_organs import headless_input as hin
            os.makedirs(os.path.join(self.run_dir, "evidence"), exist_ok=True)
            base = os.path.join(self.run_dir, "evidence", re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)[:60])
            pops = hin.popup_windows(self.hwnd)[:6]
            fr = CAP.grab_composite(self.hwnd, pops)
            if fr is not None:
                fr.image.save(base + ".png")
            wins = [(w, hin._class_name(w), hin.safe_window_text(w, 100)) for w in hin.process_windows(self.hwnd, include_hidden=False)]
            nodes = self.ex._all_nodes()
            with open(base + ".json", "w", encoding="utf-8") as fh:
                json.dump({"windows": wins, "popups": pops, "nodes": [(n.ctype[:-7], n.name[:40], n.expand_state, n.rect) for n in nodes if n.name and not n.offscreen][:80]}, fh, ensure_ascii=False, default=str)
            return base + ".png"
        except Exception:
            return ""

    MAX_REPLANS = 2
    _precond_note = ""
    CREATE_RX = re.compile(r"(?i)^\s*(?:how to\s+)?(?:insert|add|create|draw|make|place)\b")
    OBJECT_WORDS_RX = re.compile(r"(?i)\b(wordart|picture|image|photo|table|chart|shape|text ?box|smartart|icon|video|audio|equation|hyperlink|link|comment|footnote|header|footer|"
                                 r"section|slide|layer|selection|bookmark|caption|citation|text)\b")

    def _satisfy_precondition(self, t: Dict[str, Any], at: Any, kind: str = "") -> bool:
        """A step needs an object that does not exist (a step was DISABLED, or 'select the WordArt to change' found no WordArt in the run's document): find another procedure of the same guide
        that CREATES that kind of object - one whose steps reach a control named after the object ('Insert > WordArt'), or whose goal says insert / add / create it - run it first (once),
        and say so. Only the application's own guide is used; nothing is invented. Returns True when the creating procedure ran and verified."""
        from .schema import fold as _f
        words = {m.group(1).lower().replace(" ", "") for m in self.OBJECT_WORDS_RX.finditer((kind or "") + " " + t["goal"] + " " + " ".join(getattr(s, "raw", "") for s in t["steps"]) + " " + at.why)}
        if kind:
            words |= {kind.lower().replace(" ", "")}
        words -= {"text", "selection", "section"} if kind or len(words) > 1 else set()
        if not words:
            return False
        from .knowledge import guide_card as GCARD, guide_steps as GS
        cands: List[Tuple[Any, Dict[str, Any]]] = []
        for p in GCARD.procedures(self.gkey, self.index):
            if p["cite"] == t["cite"]:
                continue
            g = GS.ground(p["steps"], self.cat, self.ex.app_words)
            n_ok, n_app = GS.coverage(g)
            if not n_app or n_ok / n_app < 0.75:
                continue
            # the creating control: a grounded step whose control is NAMED after the object (WordArt gallery, Table, Chart, Pictures), not merely inside its tab
            makers = [x for x in g if x.verb is not None and x.how in GS.GROUNDED_HOW and {w.replace(" ", "") for w in _f(x.verb.label).split()} & words
                      and not (x.verb.path and str(x.verb.path[0]).startswith("Context menu"))]
            pw = {m.group(1).lower().replace(" ", "") for m in self.OBJECT_WORDS_RX.finditer(p["goal"])}
            by_goal = bool(self.CREATE_RX.search(p["goal"]) and words & pw)
            if not makers and not by_goal:
                continue
            if any(x.how == "content" or (x.verb is None and x.step.action in ("select", "click", "double_click") and x.how not in ("choice", "dialog", "key", "typed")) for x in g[:1]):
                continue                                                       # a procedure that itself starts on an existing object cannot create one
            # a maker that only OPENS a gallery creates nothing unless the procedure then picks from it
            picks = any(x.verb is not None and x in makers and ("menu" not in (x.verb.leads_to or "") or (i + 1 < len(g) and g[i + 1].how in ("choice", "label", "path"))) for i, x in enumerate(g))
            key = (bool(makers), picks, len(words & (pw | {w for x in makers for w in _f(x.verb.label).split()})), n_ok / n_app, -len(p["steps"]))
            cands.append((key, p))
        if not cands:
            self._precond_note = f"no procedure of the guide creates what '{t['goal']}' needs ({', '.join(sorted(words))})"
            return False
        cands.sort(key=lambda kp: kp[0], reverse=True)
        notes: List[str] = []
        for _key, p in cands[:3]:
            rep = self.ex.plan_from_procedure(p["goal"], p["cite"], p["steps"], text=p.get("text", ""))
            self.ex.run(rep, dry_run=False, approve=None, settle_s=self.settle_s)
            made = bool(rep.ok)
            if kind and self.ex.object_model is not None and hasattr(self.ex.object_model, "select_object"):
                made, _how = self.ex.object_model.select_object(kind)          # the model says whether the object exists now (a procedure may stop after creating it)
            notes.append(f"'{p['goal']}' ({'created it' if made else 'did not create it: ' + (rep.stopped or 'no such object afterwards')[:70]})")
            self.reset_ui()
            if made:
                self._precond_note = f"ran {notes[-1]} first to create a {'/'.join(sorted(words))}" + (f" (after {len(notes) - 1} other attempt(s))" if len(notes) > 1 else "")
                return True
        self._precond_note = "no procedure created it: " + "; ".join(notes)
        return False

    def run_task(self, t: Dict[str, Any]) -> TaskResult:
        tr = TaskResult(t["goal"], t["cite"], t["source"], len(t["steps"]), t["grounded"])
        next_plan: Any = None
        tried_cites: List[str] = [t["cite"]]
        replans = 0
        precond_done = False
        for n in range(1, self.max_attempts + 1 + self.MAX_REPLANS):
            t0 = time.time()
            dead = self._alive()
            if dead:                                                               # the instance died during the previous attempt: that attempt keeps its failure; a fresh instance takes the next
                if not self._revive(dead):
                    tr.attempts.append(Attempt(n, "failed", f"{dead}; a fresh instance could not be started", "", 0, 0, 0.0, ""))
                    break
                if tr.attempts:
                    tr.attempts[-1].remedy += f" | {dead}: relaunched a fresh owned instance"
            try:
                rep = next_plan or self.ex.plan_from_procedure(t["goal"], t["cite"], t["steps"], text=t.get("text", ""))
                next_plan = None
                self.ex.run(rep, dry_run=False, approve=None, settle_s=self.settle_s)
                status, why = self._judge(rep)
                at = Attempt(n, status, why, "", len(rep.steps), sum(1 for r in rep.results if r.status == "done"), round(time.time() - t0, 1), rep.by,
                             [{"step": r.index + 1, "verb": r.verb, "status": r.status, "route": r.route, "effect": r.effect, "summary": r.summary[:160], "vision_ok": r.vision_ok, "ms": r.ms,
                               "expected": r.expected, "verified": r.verified, "evidence": r.evidence[:160]} for r in rep.results])
                if rep.unknown:
                    at.results.append({"unknown_in_guide": rep.unknown[:6]})
            except Exception as exc:
                at = Attempt(n, "error", f"{type(exc).__name__}: {str(exc)[:200]}", "", 0, 0, round(time.time() - t0, 1), "", [{"trace": traceback.format_exc()[-500:]}])
            try:
                self.history.log_guide_run(self.spec.key, t["source"], t["cite"], t["goal"], len(t["steps"]), t["grounded"], at.done > 0, at.status == "ok", (at.status + ": " + at.why)[:400], n)
            except Exception:
                pass
            tr.attempts.append(at)
            self.ui.attempt(n, at.status, at.done, at.steps, at.why)
            if at.status not in ("ok", "blocked"):
                at.results.append({"evidence": self.evidence(f"{len(self.tasks) + 1:02d}_{t['goal']}_a{n}")})
            need_obj = next((r for r in at.results if str(r.get("summary", "")).startswith("needs_object")), None)
            if not precond_done and ((at.status == "blocked" and "disabled" in at.why) or need_obj is not None):
                precond_done = True
                ok_pre = self._satisfy_precondition(t, at, kind=str(need_obj.get("verb", "")) if need_obj else "")
                at.remedy = "precondition: " + self._precond_note
                self.ui.remedy(at.remedy)
                if ok_pre:
                    continue                                                       # the object the step needs exists now: the procedure runs again from its first step
                if need_obj is not None:
                    at.status, at.why = "failed", f"needs an object the run could not create: {self._precond_note}"
            if at.status in ("ok", "blocked"):
                break
            at.remedy = self._remedy(at.status)
            if at.remedy:
                self.ui.remedy(at.remedy)
            prev = tr.attempts[-2] if len(tr.attempts) >= 2 else None
            same_again = prev is not None and prev.status == at.status and prev.done == at.done and prev.why[:80] == at.why[:80]
            if (same_again or n >= self.max_attempts) and replans < self.MAX_REPLANS and at.status in ("ungrounded", "no_effect", "failed", "refused"):
                try:                                                               # autonomy: another control with the same meaning, or another passage of the guide (capped)
                    alt = self.ex.replan(t["goal"], rep, tried_cites, t.get("text", ""))
                except Exception:
                    alt = None
                if alt is not None:
                    replans += 1
                    tried_cites.append(alt.cite)
                    next_plan = alt
                    at.remedy += f" | re-plan {replans}/{self.MAX_REPLANS}: {alt.fallback}"
                    self.ui.remedy(f"re-plan {replans}/{self.MAX_REPLANS}: {alt.fallback[:110]}")
                    continue
            if same_again:
                self.ui.remedy("the same failure twice after a remedy: stopping (see the diagnosis)")
                at.remedy += " | repeated identically: no further attempts"
                break
            if n >= self.max_attempts:
                break
        tr.final = "ok" if tr.attempts[-1].status == "ok" else ("blocked" if tr.attempts[-1].status == "blocked" else "failed")
        self.reset_ui()
        return tr

    # ----------------------------------------------------------------------------------------------- scenario 3 / probing on the owned window
    def phase_probe(self, budget_s: float = 90.0, max_probes: int = 25) -> Dict[str, Any]:
        """Hypothesis-driven probing of the application's own controls (safe verbs only, every one unwound and verified): each probe is a row in the history database -> training data."""
        from .probe import ProbeEngine
        pe = ProbeEngine(self.hwnd, self.fx, self.cat, self.spec.key, budget_s=budget_s, max_probes=max_probes, owned=True, history=self.history, learner=self.learner,
                         toolkit=self.profile.family if self.profile else "", archetype=self.arch.get("id", ""))
        self.reset_ui()
        with self.fx.focus_watch():
            rep = pe.run()
        by: Dict[str, int] = {}
        for r in rep.rules:
            by[r.effect] = by.get(r.effect, 0) + 1
        out = {"probes": len(rep.rules), "by_effect": by, "skipped": len(rep.skipped), "stopped": rep.stopped, "seconds": rep.seconds, "tainted": pe.tainted,
               "labels": [r.verb for r in rep.rules if not str(r.how).startswith("not")]}
        self.ui.phase("probe", f"{out['probes']} controls tried · {by} · {rep.stopped or 'finished'}")
        self.reset_ui()
        return out

    def phase_explore(self, actions: int = 4, budget_s: float = 150.0) -> Dict[str, Any]:
        """Idle permutation learning: for pairs of safe actions run A-then-B and B-then-A, record whether the ORDER matters, put the application back exactly (owned window only)."""
        from .explore import Explorer
        ex = Explorer(self.hwnd, self.fx, self.cat, self.spec.key, self.history, owned=True, idle_required_s=0.0, max_actions=actions, budget_s=budget_s, learner=self.learner,
                      toolkit=self.profile.family if self.profile else "")
        self.reset_ui()
        with self.fx.focus_watch():
            rep = ex.run(require_idle=False)
        out = rep.summary()
        out["all_restored"] = all(p.restored for p in rep.pairs)
        self.ui.phase("explore", f"{len(rep.pairs)} pairs · order matters {len(out['order_matters'])} · commute {len(out['commute'])} · restored={out['all_restored']} · {rep.stopped or 'finished'}")
        self.reset_ui()
        return out

    def _teardown(self) -> None:
        """Close the owned instance and release its state (used when the run must start over)."""
        from core_organs.atlas import scanner as SC
        with contextlib.suppress(Exception):
            if self.dialogs is not None:
                self.dialogs.stop_watch()
            if self.clip is not None:
                self.clip.end()
        with contextlib.suppress(Exception):
            if self.adapter is not None:
                self.adapter.close()
        self.adapter = None
        with contextlib.suppress(Exception):
            if self.bg is not None:
                self.bg.__exit__(None, None, None)
        with contextlib.suppress(Exception):
            if self.hwnd:
                self._close_owned_app()
        with contextlib.suppress(Exception):
            if self.guard is not None:
                self.guard.after()
        with contextlib.suppress(Exception):
            from .executor import release_kept
            release_kept()
        self.hwnd, self.bg, self.fx, self.ex = 0, None, None, None
        time.sleep(1.0)

    def _close_owned_app(self) -> Dict[str, Any]:
        """Close the instance this run launched. One that is 'Not Responding' cannot answer a polite close (and UI Automation calls into it block): its process - ours, holding only the run's
        throw-away document - is ended directly."""
        import subprocess
        from core_organs.atlas import scanner as SC
        from . import perception_ladder as PL
        from .reveal import app_hung
        if app_hung(self.hwnd):
            pid = PL._pid(self.hwnd)
            if pid:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
                time.sleep(0.8)
                return {"how": "the application was not responding: its process (launched by this run) was ended"}
        return SC.close_owned(self.hwnd)

    def _test_account_ok(self) -> bool:
        """An account-holding application (navigate mode) may only be driven when the person has listed a TEST account for it. A Chromium browser is exempt: the launcher always gives it a
        throw-away profile directory (--user-data-dir), so no person's account is ever in it."""
        try:
            from .knowledge.guide_finder import settings
            acc = (settings().get("accounts") or {})
            listed = {str(x).lower() for x in acc.get("test_accounts_available", [])}
            personal = {str(x).lower() for x in acc.get("personal_account_apps", [])}
            if self.spec.key.lower() in listed or self.spec.name.lower() in listed:
                return True
            if not acc or not ({self.spec.key.lower(), self.spec.name.lower()} & personal):
                return True                                                   # not an application the person named as holding their own account: navigate-mode rules apply
        except Exception:
            return True
        try:
            from . import launcher as LN
            return bool(LN.resolve(self.spec.name).chromium == "browser")
        except Exception:
            return False

    def run(self) -> Dict[str, Any]:
        t0 = time.time()
        self._t_run = t0
        self.ui.banner(f"{self.spec.key} · tier {self.spec.tier}" + (f" · scenario: {self.spec.scenario}" if self.spec.scenario else ""), f"guide key '{self.gkey}' · mode {self.spec.mode}")
        try:
            if self.spec.mode == "navigate" and not self._test_account_ok():
                self.report["result"] = "blocked_by_policy"
                self.report["policy"] = ("this application holds a person's account; the standing decision (data/professor/settings.json -> accounts) is TEST / SANDBOX ACCOUNTS ONLY and none is "
                                         f"listed for '{self.spec.key}' - not launched (add it to accounts.test_accounts_available once a test account is signed in)")
                self.ui.phase("policy", self.ui.c("failed", self.report["policy"][:160]))
                return self.finish()
            if not self.start():
                self.report["result"] = "launch_failed"
                return self.finish()
            try:
                self.perceive()
            except Exception as exc:
                from .adapters.chromium import BrowserGone
                if not isinstance(exc, (BrowserGone, RevealTainted)):
                    raise
                if isinstance(exc, RevealTainted):
                    # a clicked option could not be proved closed again: what it showed is kept in the report AND in the catalog (the controls were really seen), the instance is
                    # thrown away and the guide runs on a fresh one
                    self._carry = [v for v in (self.cat.verbs if self.cat is not None else []) if set(v.sources or []) & {"reveal", "ribbon", "menu-expand"}]
                    self.report["phases"]["options_first_try"] = self.report["phases"].get("options", {})
                    self.report["phases"]["relaunched_after"] = str(exc)[:160]
                    self._no_reveal = True
                    self.ui.phase("options", self.ui.c("failed", "starting a fresh instance without option exploration"))
                else:
                    # the application exited on a page the crawl opened: it is now written down as a hazard; start over once with a fresh instance
                    self.ui.phase("devtools", self.ui.c("failed", f"the application exited while opening {exc.url} - recorded; starting a fresh instance"))
                    self.report["phases"]["relaunched_after"] = exc.url
                self._teardown()
                if not self.start():
                    self.report["result"] = "launch_failed"
                    return self.finish()
                self.perceive()
            if "guide" in self.phases:
                tasks = self.build_tasks()
                self.report["phases"]["guide"] = {"docs": self._guide_docs(), "runnable_procedures": len(tasks)}
                lc = {k: sum(1 for r in self.ledger if r["disposition"] == k) for k in ("skipped", "blocked")}
                self.ui.phase("guide", f"{self._guide_docs()} documents · {len(tasks)} procedures to run · set aside with a reason: {lc}")
                for i, t in enumerate(tasks, 1):
                    dead = self._alive()
                    if dead and not self._revive(dead):
                        self.report["error"] = f"{dead}; no fresh instance could be started - the remaining procedures were not run"
                        break
                    self.ui.task_start(i, len(tasks), t["goal"], len(t["steps"]), t["grounded"])
                    self.tasks.append(self.run_task(t))
                    self.checkpoint(f"task{i:02d}_{self.tasks[-1].final}_{t['goal']}")
            if "probe" in self.phases:
                self.report["phases"]["probe"] = self.phase_probe(budget_s=float(os.environ.get("HOJAIGA_PROBE_BUDGET", "90")), max_probes=int(os.environ.get("HOJAIGA_PROBE_MAX", "25")))
                self.report["phases"]["coverage"] = self.button_coverage()
            if "explore" in self.phases:
                self.report["phases"]["explore"] = self.phase_explore()
        except Exception as exc:
            self.report["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            self.report["trace"] = traceback.format_exc()[-1200:]
            self.say("ERROR " + self.report["error"])
        self.checkpoint("end_of_run")
        self.report["seconds"] = round(time.time() - t0, 1)
        return self.finish()

    def finish(self) -> Dict[str, Any]:
        from core_organs.atlas import scanner as SC
        counts = {"ok": 0, "blocked": 0, "failed": 0}
        for tr in self.tasks:
            counts[tr.final] = counts.get(tr.final, 0) + 1
        done = {(t.goal, t.cite): t for t in self.tasks}
        for row in self.ledger:
            t = done.get((row["goal"], row["cite"]))
            if t is not None and row["disposition"] not in ("skipped", "blocked"):
                row["disposition"] = t.final
        for t in self.tasks:
            if not any(r["goal"] == t.goal and r["cite"] == t.cite for r in self.ledger):
                self.ledger.append({"goal": t.goal, "cite": t.cite, "source": t.source, "steps": t.steps_in_guide, "grounded": t.grounded, "disposition": t.final, "reason": (t.attempts[-1].why if t.attempts else "")})
        self.report["ledger"] = self.ledger
        self.report["ledger_counts"] = {k: sum(1 for r in self.ledger if r["disposition"] == k) for k in sorted({r["disposition"] for r in self.ledger})}
        self.report["tasks"] = [t.to_dict() for t in self.tasks]
        self.report["counts"] = counts
        try:
            self.report["ml"] = self.learner.report()
        except Exception:
            pass
        try:
            self.report["history"] = self.history.stats(self.spec.key)
            self.report["pointer"] = self.history.pointer_stats(self.spec.key)
        except Exception:
            pass
        if self.fx is not None:
            self.report["focus_returns"] = getattr(self.fx, "focus_returns", None)
        try:
            handled = (self.ex.dialog_log if self.ex is not None else []) or []
            self.report["dialogs"] = {"handled": [{k: h.get(k) for k in ("kind", "title", "ok", "steps", "path", "saved")} for h in handled[:40]], "count": len(handled),
                                      "sandbox": self.sandbox.summary() if self.sandbox is not None else {},
                                      "clipboard": self.clip.end() if self.clip is not None else "not used"}
            if self.dialogs is not None:
                self.dialogs.stop_watch()
        except Exception:
            pass
        with contextlib.suppress(Exception):
            if self.bg is not None:
                self.bg.__exit__(None, None, None)
        try:
            if self.adapter is not None:
                self.adapter.close()
        except Exception:
            pass
        try:
            if self._revealed and self.ex is not None:
                self.report["phases"]["unrevealed"] = self.unreveal_ui()
        except Exception:
            pass
        with contextlib.suppress(Exception):
            if self.fx is not None:
                self.fx.close_pointer()                                              # the virtual mouse's in-process agent leaves the application before it is closed
        if self.hwnd:
            try:
                self.report["phases"]["close"] = self._close_owned_app()
            except Exception as exc:
                self.report["phases"]["close"] = {"error": f"{type(exc).__name__}: {str(exc)[:100]}"}
        with contextlib.suppress(Exception):
            from .executor import release_kept
            release_kept()
        try:
            self.report["phases"]["state_after"] = self.guard.after() if self.guard is not None else {}
        except Exception as exc:
            self.report["phases"]["state_after"] = {"error": f"{type(exc).__name__}: {str(exc)[:100]}"}
        os.makedirs(os.path.join(self.run_dir, "evidence"), exist_ok=True)
        path = os.path.join(self.run_dir, "report.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.report, fh, indent=1, ensure_ascii=False, default=str)
        with open(os.path.join(OUT_DIR, f"{self.spec.key}_{self.stamp}.json"), "w", encoding="utf-8") as fh:        # the flat copy older tooling reads
            json.dump(self.report, fh, indent=1, ensure_ascii=False, default=str)
        try:
            self.report["html"] = runui.write_html(self.report, self.run_dir)
        except Exception as exc:
            self.report["html_error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
        self.report["path"] = path
        try:                                                                   # the guide's procedures, analysed against what the run saw, with this run's result on each
            from . import workflows as WF
            WF.build(self.spec.key, ix=self.index, catalog=self.cat, guide_key=self.gkey)
            doc = WF.record_run(self.spec.key, self.report)
            for ext in ("json", "md"):
                shutil.copy(WF.path_of(self.spec.key, ext), os.path.join(self.run_dir, f"workflows.{ext}"))
            self.report["workflows"] = {"file": WF.path_of(self.spec.key, "md"), "count": len(doc["workflows"]) if doc else 0, "by_status": (doc or {}).get("summary", {}).get("by_status", {})}
        except Exception as exc:
            self.report["workflows_error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
        self.ui.summary(counts, self.report["ledger_counts"], self.report.get("seconds", 0), self.report.get("html", path))
        return self.report


def run_app(key: str, **kw: Any) -> Dict[str, Any]:
    spec = SPECS[key]
    return AppRun(spec, **kw).run()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Run an application's guide against the real application")
    ap.add_argument("app", nargs="?", choices=sorted(SPECS))
    ap.add_argument("--tier", type=int, default=0, help="run every application of a tier, one after the other")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--tasks", type=int, default=0)
    ap.add_argument("--no-vision", action="store_true")
    ap.add_argument("--phases", default="guide", help="comma list of: guide, probe, explore")
    a = ap.parse_args()
    keys = TIERS.get(a.tier, []) if a.tier else ([a.app] if a.app else [])
    for k in keys:
        if a.tasks:
            SPECS[k].max_tasks = a.tasks
        run_app(k, max_attempts=a.attempts, vision=not a.no_vision, phases=tuple(x.strip() for x in a.phases.split(",") if x.strip()))
