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
ADMIN_RX = re.compile(r"(?i)(group policy|policies|\bintune\b|\bmdm\b|\badmx\b|registry editor|regedit|\bgpedit\b|configuration service provider|\bcsp\b)")
SCREEN_READER_RX = re.compile(r"(?i)(screen reader|\bnarrator\b.{0,40}\b(say|says|announce|read)|you(?:'ll)? hear\b|\bJAWS\b|\bNVDA\b|scan mode)")
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
    hours: float = 0.0             # the wall-clock this run may take (0 = no limit): an unattended run stops by itself and says what it did not reach
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
                 out_dir: Optional[str] = None, visible: bool = False, actions: str = ""):
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
        self.actions = actions or os.environ.get("HOJAIGA_ACTION_LIST", "")      # a file of actions the PERSON wrote: they run through the same grounding / safety / history path as the guide's own procedures
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
        hin.ensure_input_desktop()
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
        with contextlib.suppress(Exception):
            from . import perception_ladder as _PL
            self._owned_pid = _PL._pid(self.hwnd)                                # the process THIS run started: the only one a teardown may end
        self.report["phases"]["tree"] = {"nodes": len(nodes), "waited_s": prep["attempts"][-1]["s"] if prep["attempts"] else 0.0, "frame_only": prep["used"] == "vision-needed"}
        if prep["used"] != "tree":
            self.ui.phase("tree", f"tree ladder: {prep['used']} after {len(prep['attempts'])} rung(s) - " + "; ".join(f"{a['how']} -> {a['nodes']}" for a in prep["attempts"][-3:]))
        ws = self._open_blank_workspace(nodes)
        with contextlib.suppress(Exception):
            from .executor import _timed_snapshot as _ts
            self._nodes0 = len(_ts(self.hwnd, 8.0) or [])                         # the tree's size in the healthy starting state (the blind check compares with it)
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
        if (self.vision or blind) and not self.sess.vlm.available():
            with contextlib.suppress(Exception):
                from . import vision_server as VS
                VS.ensure(wait_s=90.0)
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
        # THE EYE BEFORE THE HAND (initialization). A first-run splash, a 'what's new' card or a consent dialog can sit in front of a freshly opened window: the catalog would then be harvested FROM the
        # overlay and every later step would fight a screen the person would have clicked past in one second. So LOOK at what is in front, press the control whose OWN word says skip / close / agree (never a
        # destructive word, never picked by the application's name), and read the window again. Runs only when something actually looks in the way: the tree is blind, or a new top-level window joined ours.
        fresh_pops: List[int] = []
        with contextlib.suppress(Exception):
            from core_organs import headless_input as hin
            fresh_pops = [p for p in hin.popup_windows(self.hwnd) if p not in (self._popups0 or [])]
        if blind or fresh_pops:
            cleared = self._dismiss_blocking_popup(blind=blind, seen=getattr(sm, "elements", None))
            if cleared:
                self.report.setdefault("popups", []).append(cleared)
                time.sleep(1.2)
                with contextlib.suppress(Exception):
                    ds = IA.deep_scan(self.hwnd, budget_s=15.0)
                    self.profile = ds.profile
                with contextlib.suppress(Exception):
                    sm, img, info = self.sess.look(self.hwnd, mode="standard" if vision_up else "quick", force=True)
                if ds.nodes >= 8 and len(sm.elements) > 0:
                    blind, self._blind = False, False
                self.report["phases"]["popup_at_init"] = {"did": cleared, "fresh_popups": len(fresh_pops), "nodes_after": ds.nodes, "seen_after": len(sm.elements)}
                self.ui.phase("popup", self.ui.c("ok", f"initialization overlay: {cleared} · window now reads {ds.nodes} controls / {len(sm.elements)} seen"))
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
        cat2 = HV.harvest_tree(self.hwnd, self.spec.key, sm.window_title, sm.process)
        if len(cat.verbs) < 4 and len(cat2.verbs) > len(cat.verbs):             # the scan found nothing nameable: the plain tree harvest is the floor
            cat = cat2
        elif len(cat2.verbs) >= 2 * max(1, len(cat.verbs)):                     # the PICTURE was poor (a parked modern app renders nothing off-screen) but the tree is rich: its commands join
            have = {(tuple(v.path), v.label.lower()) for v in cat.verbs}
            add = [v for v in cat2.verbs if (tuple(v.path), v.label.lower()) not in have]
            cat.verbs += add
            self.report["phases"]["catalog_from_tree"] = {"picture_verbs": len(cat.verbs) - len(add), "tree_verbs_added": len(add)}
        cat.app_key = self.spec.key
        carried = getattr(self, "_carry", None) or []
        if not carried:
            carried = self._reuse_exploration()                                # an earlier run already explored THIS build of the application: its findings are carried in
            if carried:
                self._carry = carried
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
            done_openers = {(fold(str(v.path[0])), fold(str(v.path[1])), fold(str(v.path[2]))) for v in (getattr(self, "_carry", None) or [])
                            if "ribbon" in (v.sources or []) and len(v.path) >= 3}
            if rib is not None and self.adapter is None and getattr(self, "_reused", None):
                self.ui.phase("ribbon", f"{rib.why} · fully read by an earlier run of this build: carried over, not walked again")
                rib_seen = True
            elif rib is not None and self.adapter is None:
                rr = RB.walk(self.fx, self.ex._all_nodes, cat, rib, budget_s=float(os.environ.get("HOJAIGA_RIBBON_BUDGET", "1800")), history=self.history, toolkit=ds.profile.family,
                             on_items=self.on_flyout, log=self.say, done=done_openers)
                ribbon_read = rr.pop("read", [])
                self.report["phases"]["ribbon"] = rr
                self.ui.phase("ribbon", f"{rib.why} · structure confirmed by switching tabs: {rr.get('confirmed')} · {rr.get('tabs_read', len(rr['tabs']))}/{rr.get('tabs_found', '?')} tabs read · "
                              f"{rr['groups']} groups · {rr['controls']} controls · openers: {rr['opened']} opened now + {rr.get('opened_earlier', 0)} read earlier of {rr.get('openers_found', rr['openers'])} found "
                              f"({rr['items']} items, {rr['submenus']} submenus) · {len(rr['skipped'])} left for the next run · {rr['seconds']}s")
        except Exception as exc:
            self.report["phases"]["ribbon"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}", "trace": traceback.format_exc()[-600:]}
            self.say("ribbon walk failed: " + self.report["phases"]["ribbon"]["error"])
        # the deep tree: open every opener once (owned window), read its items, close it - a guide speaks in menu paths the tree alone cannot show
        try:
            from . import menus as MN
            if getattr(self, "_reused", None):                                   # the menus of this build were read by an earlier run (carried in above)
                mrep = {"opened": 0, "openers": 0, "items": 0, "submenus": 0, "seconds": 0.0, "failed": [], "skipped": [], "read": [], "reused_from": self._reused}
            else:
                mrep = None
            mrep = mrep or MN.expand_menus(self.fx, self.hwnd, cat, self.ex._all_nodes, budget_s=(8.0 if self.adapter else float(os.environ.get("HOJAIGA_MENU_BUDGET", "300"))), history=self.history, toolkit=ds.profile.family, restore_popups=self._popups0,
                                   on_items=self.on_flyout, ribbon=(False if rib is None else None),
                                   # a partial earlier exploration still carries its READ flyouts: an opener already read by this build is not opened again (speed: repeat runs start guiding in minutes)
                                   done={(fold(str(v.path[-1])), fold(str(v.path[-2])) if len(v.path) >= 2 else "") for v in (getattr(self, "_carry", None) or [])
                                         if "menu-expand" in (v.sources or []) and v.path},
                                   # the ribbon is read by its own walk; the caption row ABOVE its tab strip holds the window's own things (the signed-in person's account, search, window buttons) - not opened
                                   exclude=((lambda n, r=rib: r.contains(n) or n.rect[3] <= r.band[1] + 2) if rib is not None else None))
            read_items = mrep.pop("read", []) + ribbon_read
            self.report["phases"]["menus"] = mrep
            self.ui.phase("menus", f"{mrep['opened']}/{mrep['openers']} openers opened · {mrep['items']} items read · {mrep.get('submenus', 0)} submenus entered · {mrep['seconds']}s"
                          + (f" · {mrep['reused']} flyouts read by an earlier run of this build, not opened again" if mrep.get("reused") else "")
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
                                          on_surface=self.on_surface, reset=self.reset_ui, restore=self._reshow_ui, budget_s=float(os.environ.get("HOJAIGA_REVEAL_BUDGET", "450" if big else "200")),
                                          max_surfaces=int(os.environ.get("HOJAIGA_REVEAL_MAX", "60" if big else "30")), max_depth=3, learner=self.learner, per_surface_s=45.0)
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
        img2 = None
        try:
            sm2, img2, _i = self.sess.look(self.hwnd, mode="quick", force=True)
            self.shoot_scan("scan_2_deep", sm2, img2)
            self.report["phases"]["tree_picture"] = self.shoot_tree("scan_3_tree_levels")
        except Exception:
            pass
        self.report["phases"]["coverage"] = self.button_coverage()
        with contextlib.suppress(Exception):
            self.report["phases"]["scan_coverage"] = self._scan_coverage(cat)
        if img2 is not None and getattr(self, "_vision_up", False) and os.environ.get("HOJAIGA_SYMBOL_EVAL", "1") != "0":
            try:
                from . import symbol_eval as SE, labeler as LB, icon_memory as IM
                from core_organs import background_window as bw
                band = (int(rib.band[1]), int(rib.band[3])) if rib is not None and getattr(rib, "band", None) else None
                srep = SE.evaluate(img2, self.ex._all_nodes()[: self.ex._main_n or None], bw._rect(self.hwnd), LB.Labeler(self.sess.vlm, IM.memory()), self.spec.key,
                                   max_icons=int(os.environ.get("HOJAIGA_SYMBOL_MAX", "60")), band=band, memory_first=bool(int(os.environ.get("HOJAIGA_SYMBOL_MEMORY", "1"))))
                self.report["phases"]["symbols"] = srep
                self.ui.phase("symbols", f"vision named {srep['correct']}/{srep['icons']} icon-only controls like the application does ({srep['accuracy']}%; ribbon {srep['ribbon']['accuracy']}%) "
                                         f"· {srep['learned']} icons learned into the symbol memory")
            except Exception as exc:
                self.say(f"symbol evaluation error: {type(exc).__name__}: {str(exc)[:120]}")
        cv = self.report["phases"]["coverage"]
        self.ui.phase("coverage", f"{cv['tried']}/{cv['eligible']} safe on-screen controls tried ({cv['percent']}%) · {cv['seen']} more seen inside opened menus · by {cv['by']}")
        try:
            ran = any(isinstance(self.report["phases"].get(k), dict) and not self.report["phases"][k].get("error") for k in ("ribbon", "options")) or                 bool((self.report["phases"].get("menus") or {}).get("openers"))
            if ran and not getattr(self, "_reused", None):
                rib_r = self.report["phases"].get("ribbon") or {}
                men_r = self.report["phases"].get("menus") or {}
                complete = not rib_r.get("skipped") and not any("time budget" in str(f) for f in (rib_r.get("failed") or []) + (men_r.get("failed") or []))                     and not self.report["phases"].get("relaunched_after")
                cat.notes = [n for n in cat.notes if not str(n).startswith("explored|")] + [f"explored|{self._exe_version()}|{int(time.time())}|{'complete' if complete else 'partial'}"]
            elif getattr(self, "_stamp", ""):                                   # this run REUSED an exploration: its stamp stays (the saved catalog must not lose it)
                cat.notes = [n for n in cat.notes if not str(n).startswith("explored|")] + [self._stamp]
            with contextlib.suppress(Exception):                                 # what each command does, in the vendor's own guide sentences (cited)
                from .knowledge import guide_explain as GEX
                if self.index is not None:
                    self.report["phases"]["explained"] = GEX.enrich(cat, self.index, self.gkey)
            cat.save()
            self.history.register_app(self.spec.key, self.spec.name, self.target.exe if self.target else "", ds.profile.family, self.spec.tier, self._guide_docs(), len(cat.verbs), self.spec.notes)
        except Exception:
            pass
        self.report["phases"]["perceive_s"] = round(time.time() - t0, 1)
        self._capture_tabs()
        self.checkpoint("after_scan_home")

    def _scan_coverage(self, cat: Any) -> Dict[str, Any]:
        """DEEP UI SCAN, measured: of the named, visible, operable controls the live tree shows in the main window now, how many are in the application's knowledge (catalog)?"""
        from . import menus as MN
        nodes = self.ex._all_nodes()[: self.ex._main_n or None]
        known = {fold(v.label) for v in cat.verbs} | {fold(re.sub(r"\.\.\.$|…$", "", v.label)) for v in cat.verbs}
        live = [n for n in nodes if n.role in MN.ITEM_ROLES and (n.name or "").strip() and not n.offscreen and n.enabled and not safety_blocked(n.name)]
        names = {fold(MN._item_label(n)[0]) for n in live} - {""}
        got = {x for x in names if x in known}
        return {"live_controls": len(names), "in_knowledge": len(got), "percent": round(100.0 * len(got) / len(names), 1) if names else None,
                "missing": sorted(names - got)[:20]}

    def _exe_version(self) -> str:
        try:
            from .knowledge.guide_finder import version_info
            exe = self.target.exe if self.target else ""
            return str((version_info(exe) or {}).get("FileVersion", "")) if exe and os.path.isfile(exe) else ""
        except Exception:
            return ""

    def _reuse_exploration(self) -> List[Any]:
        """The ribbon walk, menu reading and dialog exploration of an application take minutes (measured: Word 76 min a run) and give the same answer for the same build. A catalog saved
        by an earlier run that EXPLORED this same FileVersion within HOJAIGA_REUSE_DAYS days (default 7; 0 = always explore) gives its explored controls instead. Returns those verbs."""
        days = float(os.environ.get("HOJAIGA_REUSE_DAYS", "7") or 0)
        ver = self._exe_version()
        if days <= 0 or not ver:
            return []
        from .harvest import Catalog
        old = Catalog.load(self.spec.key)
        stamp = next((str(n) for n in reversed(getattr(old, "notes", []) or []) if str(n).startswith("explored|")), "") if old else ""
        parts = stamp.split("|")
        if len(parts) not in (3, 4) or parts[1] != ver or time.time() - float(parts[2] or 0) > days * 86400:
            return []
        verbs = [v for v in old.verbs if set(v.sources or []) & {"reveal", "ribbon", "menu-expand"}]
        if len(verbs) < 10:
            return []
        self._stamp = stamp
        when = time.strftime('%Y-%m-%d %H:%M', time.localtime(float(parts[2])))
        complete = len(parts) == 4 and parts[3] == "complete"
        if complete:
            self._reused = f"{ver} explored {when}"
            self._no_reveal = True                                              # its dialogs / pages were explored then too
            self.ui.phase("reuse", f"this build ({ver}) was fully explored on {when}: {len(verbs)} explored controls carried in, ribbon / menus / dialogs not walked again")
        else:
            self.ui.phase("reuse", f"this build ({ver}) was PARTLY explored on {when}: {len(verbs)} controls carried in; the walk continues with what was not read")
        self.report["phases"]["reused_exploration"] = {"version": ver, "explored_at": when, "verbs": len(verbs), "complete": complete}
        return verbs

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
        prev_stats = getattr(self, "_accumulated_pointer_stats", None)
        if prev_stats is not None:
            self.ex.pointer_stats = prev_stats
        else:
            self._accumulated_pointer_stats = self.ex.pointer_stats
        with contextlib.suppress(Exception):
            from .triggers import TriggerBank
            self._triggers = getattr(self, "_triggers", None) or TriggerBank(self.spec.key)     # one bank per run (kept across a relaunch): the cap counts the whole run
            self.ex.triggers = self._triggers
        try:
            from . import workflows as WF
            self.ex.app_words = WF.app_words_for(self.gkey, cat)
        except Exception:
            pass
        self.ex.blind = bool(getattr(self, "_blind", False))                                              # the interface tree is blind: routes through the application's own engine come first

        def _eyes(mode: str = "quick") -> List[Any]:                                                     # THE EYE, HANDED TO THE EXECUTOR: some dialogs are painted by the application inside its own canvas
            try:                                                                                         # (a 3-D suite's file browser has no accessibility objects: the tree cannot name its buttons, the screen can)
                if self.sess is None or not self.hwnd:
                    return []
                sm_l, _img, _i = self.sess.look(self.hwnd, mode=mode, force=True)
                return list(getattr(sm_l, "elements", []) or [])
            except Exception:
                return []
        self.ex.look_here = _eyes
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

    def _budget_out(self) -> bool:
        """The wall-clock the person gave this run is up. An unattended run has to stop by itself and say what it did not reach, instead of running into the night."""
        h = float(getattr(self.spec, "hours", 0) or 0) or float(os.environ.get("HOJAIGA_RUN_HOURS", "0") or 0)
        return bool(h) and (time.time() - float(getattr(self, "_t_run", time.time()) or time.time())) > h * 3600.0

    def _frame_count(self) -> int:
        """How many controls the frame shows: the count the background tree reader published (one whole-tree read of Word's frame costs 22 s - a liveness check that pays it per task is what made a
        run look stalled). Nothing published yet (the window is brand new, or a dialog owns it) falls back to a single bounded read."""
        try:
            m = getattr(self.ex, "mirror", None) if self.ex is not None else None
            got = m.latest() if m is not None else None
            if got is not None:
                return len(got)
        except Exception:                                                       # noqa: BLE001
            pass
        from .executor import _timed_snapshot
        return len(_timed_snapshot(self.hwnd, 8.0) or [])

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
        # A DIALOG CAN TAKE THE WINDOW: while one is up the frame is disabled, nothing on it can be pressed and its tree cannot change - which looks EXACTLY like an application that went blind.
        # A person answers the card and goes on; the run does the same (and the background reader, which does not read a disabled frame, starts publishing again the moment it is free).
        from .executor import _frame_enabled
        if self.ex is not None and not _frame_enabled(self.hwnd):
            cleared = self.ex._clear_owning_dialog()
            if cleared:
                self.report.setdefault("modals", []).append(cleared)
                self.ui.phase("modal", f"a dialog owned the window: {cleared}")
                return ""
        n0 = int(getattr(self, "_nodes0", 0) or 0)
        if n0 >= 40:                                                           # a window that had a rich interface tree and now shows almost nothing has gone blind (measured: Word after a pane click)
            try:
                from .executor import _timed_snapshot
                now = self._frame_count()
                if now < 0.3 * n0:
                    time.sleep(2.0)
                    now = self._frame_count()
                    if now < 0.3 * n0:
                        # the interface may not have gone: it may have MOVED. A suite that opens a picker / online-content browser in a helper process leaves its own frame almost empty while the real
                        # controls are all in the new window - and the executor already follows that window. Count what is being followed before calling the application blind.
                        followed = list(getattr(self.ex, "follow", []) or []) if self.ex is not None else []
                        if followed:
                            from .executor import _timed_snapshot as _ts
                            extra = sum(len(_ts(w, 5.0) or []) for w in followed)
                            if extra >= 0.3 * n0:
                                self.ui.phase("follow", f"the interface moved to a window the run follows ({', '.join(str(w) for w in followed)}): {extra} controls there, {now} left in the frame")
                                return ""
                        # a person does not reinstall the app when a splash / consent card covers it: they READ the overlay and click past it. Look, name what is in front, dismiss it, then see if the tree returns.
                        cleared = self._dismiss_blocking_popup(blind=True)
                        if cleared:
                            self.report.setdefault("popups", []).append(cleared)
                            now = len(_timed_snapshot(self.hwnd, 8.0) or [])
                            if now >= 0.3 * n0:
                                self.ui.phase("popup", f"{cleared} · the interface came back ({now} controls)")
                                return ""
                        return f"the application's interface went blind ({now} readable controls, {n0} at the start)"
            except Exception:
                pass
        return ""

    DISMISS_RX = re.compile(r"(?i)^(?:\s*(?:\u00d7|\u2715|x)\s*|(?:close|skip(?:\s+(?:this\s+)?(?:tour|walkthrough)?)?|dismiss|got\s+it|i\s+(?:have\s+)?got\s+it|get\s+started|start\s+using|continue(?:\s+to)?|accept(?:\s+all)?|i\s+agree|ok(?:ay)?|finish|finish\s+setup|later|no\s+thanks|not\s+now|maybe\s+later|don'?t\s+show(?:\s+again)?|next|sounds\s+good|lets\s+go|let'?s\s+go)\b)")

    def _dismiss_blocking_popup(self, blind: bool = False, seen: Optional[List[Any]] = None) -> str:
        """The EYE before the hand: a first-run splash, a 'what's new' card or a consent dialog can cover the window so its accessibility tree reports (almost) nothing. The vision pipeline names
        what is in front of it; the control whose OWN word says 'leave / agree / skip' is pressed with the virtual mouse - chosen by the word on it, never by the application's name, never a
        destructive word. `blind` also permits a bare Escape when the tree is empty and nothing on the overlay could be named. `seen`: the reading already in hand (a full vision pass costs a
        minute - the caller that just looked passes what it saw instead of asking the eye to look again). Returns what was done ('' when there was nothing to dismiss)."""
        if not self.hwnd or getattr(self, "sess", None) is None:
            return ""
        hand = self.fx                                                       # at initialization the executor's hand is not built yet: the eye brings its own
        if hand is None:
            from .effectors import Effector
            hand = Effector(self.hwnd, allow_input=True, owned=True)
        if seen is None:
            try:
                sm, _img, _i = self.sess.look(self.hwnd, mode="standard", force=True)
                seen = list(getattr(sm, "elements", []) or [])
            except Exception:
                seen = []
        else:
            seen = list(seen)
        cands = [e for e in seen if (e.role in ("button", "window_control", "icon", "link") or not getattr(e, "role", ""))
                 and e.bbox.x2 > e.bbox.x1 and self.DISMISS_RX.search((e.label or "").strip())
                 and not re.search(r"(?i)\b(delete|remove|discard|format|quit|exit|uninstall|empty|reset|turn\s+off|disable)\b", e.label or "")]
        if not seen and blind:                                               # the eye itself could not read the window either: say so, and still try the one gesture that is always harmless
            ok, how = hand.key("escape")
            time.sleep(0.8)
            return "nothing could be read on the blocking screen: sent Escape blindly (a person's other hand)" if ok else ""
        if cands:
            def rank(e):                                                       # least-committal first: Skip / Close / No thanks beats Accept / Get started; a real button beats a bare icon
                lab = fold(e.label or "")
                soft = 0 if re.search(r"^(close|\u00d7|\u2715|skip|no\s+thanks|not\s+now|maybe\s+later|dismiss|don'?t\s+show)\b", lab) else 1
                return (soft, 0 if e.role == "button" else 1, -float(e.conf or 0))
            pick = sorted(cands, key=rank)[0]
            ok, how = hand.click_xy(int(pick.bbox.cx), int(pick.bbox.cy))
            time.sleep(1.0)
            return f"read the overlay and pressed '{(pick.label or '').strip()[:34]}' ({'delivered' if ok else how})"
        # THE EYE REPORTS WHAT IT SAW, even when it names no dismiss button: what was in front is written into the report, so a person reading the report later knows what held the run. A canvas-drawn
        # splash (an OpenGL program paints its own start-up card, no accessibility object exists for it) answers a click ANYWHERE off the card, so one click is placed on the window's own top strip -
        # the only surface that is never content.
        if blind and seen:
            self.report.setdefault("popup_sightings", []).append({"words": [str(e.label or "").strip()[:40] for e in seen if (e.label or "").strip()][:24]})
            frame = None
            try:
                import ctypes
                from ctypes import wintypes as _wt
                r = _wt.RECT()
                ctypes.windll.user32.GetWindowRect(self.hwnd, ctypes.byref(r))
                frame = (r.left, r.top, r.right, r.bottom)
            except Exception:
                frame = None
            if frame and frame[2] > frame[0] and frame[3] > frame[1]:
                sx, sy = (frame[0] + frame[2]) // 2, int(frame[1] + 0.12 * (frame[3] - frame[1]))
                if not any(e.bbox.x1 - 8 <= sx <= e.bbox.x2 + 8 and e.bbox.y1 - 8 <= sy <= e.bbox.y2 + 8 and (e.label or "").strip() for e in seen):
                    ok, how = hand.click_xy(sx, sy)
                    time.sleep(1.0)
                    if ok:
                        return "the blocking screen is drawn by the program itself (no control to name): clicked once on its own top strip to clear it"
        if blind:
            ok, how = hand.key("escape")
            time.sleep(0.8)
            if ok:
                return "the overlay held no readable control: sent Escape (a person's other hand)"
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
    def _person_procs(self) -> List[Dict[str, Any]]:
        """ACTIONS THE PERSON WROTE DOWN, read as runnable material. The list goes through the SAME pipeline as a procedure of the guide (parse the lines -> ground every step against the LIVE catalog
        -> perform it with the virtual mouse -> judge, record, undo), so a hand-written step is never a way around the safety rules: a step that names no real control is set aside with that reason, a
        step that sends something to another person still needs a yes.
        A `.json` file: [{"goal": "...", "steps": ["Click File > Open", "Type \"notes.txt\" in the File name box"]}] (or the same list under a "tasks" key). Any other file: blocks of lines split by an
        empty line, the first line of a block being the goal and the rest the steps."""
        path = getattr(self, "actions", "") or ""
        if not path or not os.path.exists(path):
            return []
        from .knowledge import guide_steps as GS
        out: List[Dict[str, Any]] = []
        try:
            if path.lower().endswith(".json"):
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                rows = data.get("tasks") if isinstance(data, dict) else data
                for i, r in enumerate(rows or [], 1):
                    if isinstance(r, str):
                        r = {"goal": r, "steps": [r]}
                    goal = str(r.get("goal") or f"action list {i}").strip()
                    lines = [str(s) for s in (r.get("steps") or []) if str(s).strip()]
                    if not lines:
                        continue
                    cite = "the person's own list > " + goal[:80]
                    out.append({"goal": goal, "cite": cite, "source": "person", "steps": GS.parse_steps("\n".join(lines), cite), "text": "\n".join(lines)})
            else:
                with open(path, "r", encoding="utf-8") as fh:
                    blocks = [b.strip() for b in re.split(r"\n\s*\n", fh.read()) if b.strip()]
                for b in blocks:
                    lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
                    goal, lines = lines[0], lines[1:] or lines[:1]
                    cite = "the person's own list > " + goal[:80]
                    out.append({"goal": goal, "cite": cite, "source": "person", "steps": GS.parse_steps("\n".join(lines), cite), "text": "\n".join(lines)})
        except Exception as exc:                                                # noqa: BLE001
            with contextlib.suppress(Exception):
                self.report["actions_error"] = f"{type(exc).__name__}: {str(exc)[:150]}"
                self.say(f"the action list {os.path.basename(path)} could not be read: {self.report['actions_error']}")
            return []
        kept = [p for p in out if p["steps"]]
        if kept:
            self.ui.phase("guide", f"the person's action list: {len(kept)} task(s), {sum(len(p['steps']) for p in kept)} step(s) read from {os.path.basename(path)}")
        return kept

    def _launch_rx(self) -> "re.Pattern":
        words = {w for w in re.findall(r"[a-z0-9]+", (self.spec.name + " " + self.spec.key + " " + (self.target.display if self.target else "")).lower()) if len(w) > 2}
        words |= {"app", "application", "start menu", "taskbar", "microsoft store", "windows"}
        alt = "|".join(re.escape(w) for w in sorted(words))
        return re.compile(r"^\s*(?:\d+[.)]\s*)?(?:how (?:do i|to) )?(?:open|start|launch|run|update|install|download|get|find)\b.*\b(?:" + alt + r")\b|\bfrom the (?:start menu|taskbar)\b|\bstart menu\b", re.I)

    def build_tasks(self) -> List[Dict[str, Any]]:
        """The guide's procedures that can be attempted here: the first step grounds in the live catalog (or at least half of the steps do). Every procedure the guide has is accounted for in
        `self.ledger` - attempted, or set aside WITH the reason."""
        from .knowledge import guide_card as GCARD, guide_steps as GS, task_like as TL
        procs = self._person_procs() or GCARD.procedures(self.gkey, self.index)
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

        import urllib.parse
        from .knowledge import guide_finder as GF
        strict_src = bool(GF.settings().get("guide_web_strict", True))
        seed_domains: List[str] = []
        with contextlib.suppress(Exception):
            from .knowledge import guide_corpus as GCOR
            for a in GCOR.load_catalog():
                if a.get("key") == self.gkey:
                    for sd in a.get("seeds") or []:
                        u = sd["url"] if isinstance(sd, dict) else str(sd)
                        seed_domains.append(GF.registrable((urllib.parse.urlsplit(u).hostname or "").lower()))
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
            src = str(p.get("source") or "")
            if src.startswith("http") and strict_src:
                reg_src = GF.registrable((urllib.parse.urlsplit(src).hostname or "").lower())
                okh, whyh = (True, "a curated seed's site") if reg_src in seed_domains else GF.allowed_host(src, [reg_src])
                if not okh:                                                        # the person's standing rule: official documentation only (pages taken before the allow list existed are still in the corpus)
                    put(p, "skipped", "not an official documentation page: " + whyh)
                    continue
            if SCREEN_READER_RX.search(p["goal"] + " " + p.get("cite", "") + " " + p.get("text", "")[:600]):
                put(p, "blocked", "policy: a screen-reader walkthrough (Tab / arrow keys with speech feedback) needs the person's real keyboard focus - a parked run never takes it")
                continue
            if ADMIN_RX.search(p["goal"] + " " + p.get("cite", "") + " " + p.get("text", "")[:400]):
                put(p, "skipped", "an administrator's policy (Group Policy / MDM / registry), not a task inside the application")
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
        min_run_tasks = min(4, self.spec.max_tasks)
        if len(uniq) < min_run_tasks and getattr(self, "cat", None) and self.cat.verbs:
            have_targets = {t["steps"][0].target.lower() for t in uniq if t.get("steps")}
            synth = self._synthesize_button_tasks(min_run_tasks - len(uniq), exclude_targets=have_targets)
            uniq.extend(synth)
        for t in uniq[self.spec.max_tasks:]:
            self.ledger.append({"goal": t["goal"], "cite": t["cite"], "source": t["source"], "steps": len(t["steps"]), "grounded": t["grounded"], "disposition": "skipped",
                                "reason": "beyond the per-run task cap" if t["task"] >= TL.TASK_THRESHOLD else "beyond the per-run task cap; also reads as reference material (" + t["why_ref"] + ")"})
        return uniq[: self.spec.max_tasks]

    def _synthesize_button_tasks(self, needed: int, exclude_targets: Optional[set] = None) -> List[Dict[str, Any]]:
        """When an application's official guide yields fewer runnable procedures than the run needs, dynamically synthesize tasks
        from its own safe, enabled catalog verbs (buttons, menus, toggles). Completely generic across all toolkits and applications."""
        if not getattr(self, "cat", None) or not self.cat.verbs or needed <= 0:
            return []
        from .knowledge.guide_steps import GuideStep
        exclude = set(exclude_targets or set())
        safe_verbs = [
            v for v in self.cat.verbs
            if v.enabled and v.safety in ("safe", "runtime")
            and v.role in ("button", "menu_item", "toggle", "dropdown", "radio", "tab")
            and v.label and len(v.label.strip()) > 1
            and v.label.lower() not in exclude
            and not any(v.label.lower().startswith(p) for p in ("close", "minimize", "maximize", "system", "exit", "quit"))
        ]
        by_path: Dict[str, List[Any]] = {}
        for v in safe_verbs:
            key = " > ".join(v.path) if v.path else "main"
            by_path.setdefault(key, []).append(v)

        chosen: List[Any] = []
        while len(chosen) < needed and any(by_path.values()):
            for k in list(by_path.keys()):
                if by_path[k]:
                    v = by_path[k].pop(0)
                    if v.label.lower() not in exclude:
                        chosen.append(v)
                        exclude.add(v.label.lower())
                        if len(chosen) >= needed:
                            break
                else:
                    by_path.pop(k, None)

        synth_tasks: List[Dict[str, Any]] = []
        for v in chosen:
            act = "toggle" if v.role == "toggle" else "click"
            raw_text = f"Select {v.label}" if act == "click" else f"Toggle {v.label}"
            step = GuideStep(n=1, raw=raw_text, action=act, target=v.label, path=list(v.path), chord=v.shortcut or "")
            cite = " > ".join(v.path + [v.label]) if v.path else v.label
            synth_tasks.append({
                "goal": f"Use {v.label}",
                "cite": cite,
                "source": "app_catalog",
                "steps": [step],
                "grounded": 1.0,
                "text": v.desc or v.label,
                "task": 1.0,
                "why_ref": "synthesized from live interface control",
            })
        return synth_tasks

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
        try:
            for n in self.ex._all_nodes():
                if n.role == "button" and n.name and n.name.lower() in ("back", "navigate up") and not n.offscreen:
                    self.fx.node(n)
                    time.sleep(0.2)
                    break
        except Exception:
            pass
        try:
            self.fx.key("alt+left")
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
    _precond_depth = 0
    CREATE_RX = re.compile(r"(?i)^\s*(?:how to\s+)?(?:insert|add|create|draw|make|place)\b")
    OBJECT_WORDS_RX = re.compile(r"(?i)\b(scene|wordart|picture|image|photo|table|chart|shape|text ?box|smartart|icon|video|audio|equation|hyperlink|link|comment|footnote|header|footer|"
                                 r"section|slide|layer|selection|bookmark|caption|citation|text object|text|mode|edit mode|mesh|armature|curve|bone|camera|light|document|window)s?\b")

    def _satisfy_precondition(self, t: Dict[str, Any], at: Any, kind: str = "") -> bool:
        """A step needs an object that does not exist (a step was DISABLED, or 'select the WordArt to change' found no WordArt in the run's document): find another procedure of the same guide
        that CREATES that kind of object - one whose steps reach a control named after the object ('Insert > WordArt'), or whose goal says insert / add / create it - run it first (once),
        and say so. Only the application's own guide is used; nothing is invented. Returns True when the creating procedure ran and verified."""
        from .schema import fold as _f
        self._precond_note = ""
        err_texts = " ".join([str(r.get("summary", "")) for r in at.results if isinstance(r, dict)] + [str(r.get("evidence", "")) for r in at.results if isinstance(r, dict)])
        full_text = (kind or "") + " " + t["goal"] + " " + " ".join(getattr(s, "raw", "") for s in t["steps"]) + " " + at.why + " " + err_texts
        words = {m.group(1).lower().replace(" ", "") for m in self.OBJECT_WORDS_RX.finditer(full_text)}
        if kind:
            words |= {kind.lower().replace(" ", "")}
        words -= {"text", "selection", "section"} if kind or len(words) > 1 else set()
        if not words:
            return self._create_with_own_command(t, at) or self._seed_document_content(full_text)
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
            made = self._create_with_own_command(t, at)
            if made:
                return True
            if self._seed_document_content(full_text):
                return True
            self._precond_note = f"no procedure of the guide creates what '{t['goal']}' needs ({', '.join(sorted(words))})" + (f"; {self._precond_note}" if self._precond_note else "")
            return False
        cands.sort(key=lambda kp: kp[0], reverse=True)
        notes: List[str] = []
        for _key, p in cands[:3]:
            rep = self.ex.plan_from_procedure(p["goal"], p["cite"], p["steps"], text=p.get("text", ""))
            self.ex.run(rep, dry_run=False, approve=None, settle_s=self.settle_s)
            made = bool(rep.ok)
            if not made and self._precond_depth < 2:                              # the creating procedure hit a precondition of ITS OWN: chain one level deeper (create what the creator needs), then run it again
                fail_txt = (rep.stopped or "") + " " + " ".join(str(getattr(r, "summary", ""))[:160] for r in rep.results)
                if re.search(r"(?i)cannot|can'?t|needs?\b|requires?\b|must be|not found|nothing selected|app_says", fail_txt):
                    import types as _ts
                    sub_at = _ts.SimpleNamespace(why=rep.stopped or "", results=[{"step": r.index + 1, "verb": r.verb, "status": r.status, "summary": r.summary[:160], "evidence": r.evidence[:160]} for r in rep.results])
                    self._precond_depth += 1
                    try:
                        chained = self._satisfy_precondition({"goal": p["goal"], "cite": p["cite"], "source": p.get("source", ""), "steps": p["steps"], "text": p.get("text", ""), "grounded": 1.0}, sub_at)
                    finally:
                        self._precond_depth -= 1
                    if chained:
                        self._precond_note = f"(chain: {self._precond_note}) "
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
        return self._seed_document_content(full_text)

    ADD_RX = re.compile(r"(?i)^(add|new|insert|create|enter|toggle mode|switch to)\b")
    _STOP = {"the", "and", "you", "your", "with", "for", "from", "into", "this", "that", "then", "mode", "select", "selected", "click", "press", "choose", "open", "edit", "view", "menu", "tab",
             "panel", "button", "option", "options", "tool", "tools", "use", "using", "want", "can", "will", "all", "each", "one", "new", "add", "window", "file", "workspace"}

    THING_RX = re.compile(r"(?i)\b(scene|wordart|picture|image|photo|table|chart|shape|text ?box|smartart|video|audio|equation|hyperlink|comment|footnote|header|footer|slide|layer|bookmark|"
                          r"caption|citation|object|mesh|armature|bone|camera|light|lamp|curve|empty|lattice|metaball|surface|strip|node|keyframe|marker|track|collection|material|"
                          r"modifier|constraint|texture|uv map|vertex group|shape key|particle system|grease pencil|text object|text|mode|edit mode|speaker|probe|force field|volume|point cloud|document|window)s?\b")

    def _create_with_own_command(self, t: Dict[str, Any], at: Any) -> bool:
        """No guide procedure creates what the step needs: the application's OWN 'Add / New / Insert <thing>' command for the thing the failing step names (its goal and the step's
        words: 'pose the bone' -> 'Add Armature' only if the step says armature / bone ...), run once through the routes the executor has (scripting / object model / UI)."""
        from .schema import fold as _f
        fail = next((r for r in reversed(at.results) if isinstance(r, dict) and r.get("status") not in ("done", None)), {})
        summ = str(fail.get("summary", ""))[:200]
        if re.search(r"(?i)\bfile\.|needs a file|file browser|file dialog", summ + " " + (at.why or "")):
            return False                                                           # a file is missing, not an object: the sandbox file handling owns that, nothing is created
        idx = int(fail.get("step", 0) or 0)
        step_raw = getattr(t["steps"][idx - 1], "raw", "") if 0 < idx <= len(t["steps"]) else " ".join(getattr(s, "raw", "") for s in t["steps"])
        err_texts = " ".join([str(r.get("summary", "")) for r in at.results if isinstance(r, dict)] + [str(r.get("evidence", "")) for r in at.results if isinstance(r, dict)])
        text = " ".join([str(fail.get("verb", "")), summ, step_raw, at.why or "", err_texts])               # the FAILING step and its reason name the missing thing
        want = {m.group(1).lower().rstrip("s") if len(m.group(1)) > 4 else m.group(1).lower() for m in self.THING_RX.finditer(text)}
        want = {"vertex" if w == "vertice" else w for w in want}
        if not want:
            return False
        own = {_f(t["goal"])} | {_f(getattr(s, "target", "") or "") for s in t["steps"]} | {_f(str(r.get("verb", ""))) for r in at.results if isinstance(r, dict)}
        best, best_s = None, 0
        for v in self.cat.verbs:
            if _f(v.label) in own:                                                 # the task's OWN command ('Create Orientation') is what failed: it cannot be its own precondition
                continue
            is_creator = bool(self.ADD_RX.search(v.label) or (v.path and any(self.ADD_RX.search(p) for p in v.path)))
            if not is_creator or not v.enabled or v.safety not in ("safe", "commit") or (v.path and str(v.path[0]).startswith("Context menu")):
                continue
            rest = _f(v.label).split()[1:] or _f(v.label).split()
            if v.path:
                rest = rest + [w for p in v.path for w in _f(p).split() if not self.ADD_RX.search(w)]
            lw = {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in rest if len(w) > 2 and w not in self._STOP}
            hit = len(lw & want)
            if not hit:
                continue
            hit = hit - 0.1 * len(lw - want) + (0.5 if lw <= want else 0.0)       # 'Add Armature' (every word wanted) over 'Create Pose Asset' (one wanted, one not)
            if hit > best_s:
                best, best_s = v, hit
        if best is None:
            return False
        step = self.ex._step_for_verb(best, f"create what '{t['goal']}' needs", 0.8, "internal")
        from .executor import ExecReport
        rep = ExecReport(goal=f"create: {best.label}", steps=[step])
        self.ex.run(rep, dry_run=False, approve=None, settle_s=self.settle_s)
        self._precond_note = f"ran the application's own '{best.text_path}' first ({'done' if rep.ok else 'did not work: ' + (rep.stopped or '')[:80]})"
        self.reset_ui()
        return bool(rep.ok) or self._seed_document_content(text)

    SEED_TEXT_RX = re.compile(r"(?i)\b(text|words?|paragraphs?|sentences?|content|letters?|title|notes?|body|typed)\b")

    def _seed_document_content(self, context: str) -> bool:
        """Last resort of the precondition remedy: a guide passage assumes content that EXISTS (text to format, words to select) and the run's document is empty. The run created that blank
        document itself, so making the precondition true is its own job: type a short sample paragraph into the document's MAIN editor - through the effector (UIA value / posted characters,
        never the physical keyboard, focus returned at once). Gated generally: only editors of the document kinds (by the run's archetype, never by application name), only in full mode (an
        application holding the person's account is never typed into), only when the failing words are about text - and only twice per run, so a step that needs a real object is not
        papered over with typed filler again and again."""
        if getattr(self, "_seeded", 0) >= 2 or not self.SEED_TEXT_RX.search(context or ""):
            return False
        from .executor import DOC_EDITOR_ARCHETYPES
        if self.spec.mode != "full" or self.arch.get("id", "") not in DOC_EDITOR_ARCHETYPES:
            return False
        fx = getattr(self, "fx", None) or getattr(self.ex, "fx", None)
        if fx is None or not fx.allowed:
            return False
        self._seeded = getattr(self, "_seeded", 0) + 1
        ok, how = fx.insert_text("Hojaiga sample text: one two three. A second sentence to work on.", deadline_s=6.0)
        self._precond_note = f"typed a sample paragraph into the document's own editor ({'done' if ok else str(how)[:70]})"
        with contextlib.suppress(Exception):
            self.report.setdefault("seeds", []).append(self._precond_note)
        return bool(ok)

    def run_task(self, t: Dict[str, Any]) -> TaskResult:
        tr = TaskResult(t["goal"], t["cite"], t["source"], len(t["steps"]), t["grounded"])
        next_plan: Any = None
        tried_cites: List[str] = [t["cite"]]
        replans = 0
        precond_count = 0
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
            if at.status == "ok" or (at.status == "blocked" and "disabled" not in (at.why or "")):
                break
            if at.status != "blocked":
                at.results.append({"evidence": self.evidence(f"{len(self.tasks) + 1:02d}_{t['goal']}_a{n}")})
            need_obj = next((r for r in at.results if str(r.get("summary", "")).startswith("needs_object")), None)
            fail_text = (at.why or "") + " " + " ".join(str(r.get("summary", "")) + " " + str(r.get("verb", "")) for r in at.results if isinstance(r, dict))
            has_contextual_fail = bool(re.search(r"(?i)context|tab[a-z0-9]*(?:tools|design|format)|-2147024809|not found in the live tree", fail_text)
                                       and self.THING_RX.search(t["goal"] + " " + fail_text))
            is_precond_fail = (
                (at.status == "blocked" and "disabled" in at.why)
                or need_obj is not None
                or has_contextual_fail
                or re.search(r"(?i)precondition|poll|did not create|cannot|needs? (?:an? )?[a-z0-9 ]+|create [a-z0-9 ]+ first|must be in", at.why or "")
                or any(re.search(r"(?i)cannot|needs?|require[s]?|must be in", str(r.get("summary", ""))) for r in at.results if isinstance(r, dict))
            )
            if precond_count < 3 and is_precond_fail:
                precond_count += 1
                ok_pre = self._satisfy_precondition(t, at, kind=str(need_obj.get("verb", "")) if need_obj else "")
                at.remedy = f"precondition ({precond_count}/3): " + self._precond_note
                self.ui.remedy(at.remedy)
                if ok_pre:
                    continue                                                       # the prerequisite exists now: the procedure runs again from its first step
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
                from .executor import stop_mirrors
                stop_mirrors()                                           # the reader of the window that is about to die is called off first (it otherwise walks a dead provider for 45 s)
                self._close_owned_app()
        self._wait_owned_exit()
        with contextlib.suppress(Exception):
            if self.guard is not None:
                self.guard.after()
        with contextlib.suppress(Exception):
            from .executor import release_kept
            release_kept()
        self.hwnd, self.bg, self.fx, self.ex = 0, None, None, None
        time.sleep(1.0)

    def _wait_owned_exit(self, wait_s: float = 10.0) -> str:
        """After closing: wait for the process this run started to be GONE (a single-instance application that is still exiting would otherwise hand the next launch its dying window -
        measured: a relaunched Word that was blind). Still there after the wait: ended by its process id (it is ours; the person's own instances have other ids)."""
        import subprocess
        pid = int(getattr(self, "_owned_pid", 0) or 0)
        if not pid:
            return ""
        end = time.time() + wait_s
        while time.time() < end:
            try:
                import psutil
                if not psutil.pid_exists(pid):
                    return "exited"
            except Exception:
                out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, creationflags=0x08000000).stdout or ""
                if str(pid) not in out:
                    return "exited"
            time.sleep(0.5)
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
        time.sleep(1.0)
        self.report.setdefault("phases", {}).setdefault("ended_owned_process", []).append(pid)
        return "ended"

    def _close_owned_app(self) -> Dict[str, Any]:
        """Close the instance this run launched. One that is 'Not Responding' cannot answer a polite close (and UI Automation calls into it block): its process - ours, holding only the run's
        throw-away document - is ended directly. A document with unsaved changes ANSWERS the close request with a card ('Save your changes to this file?'): the run backs out of its own request
        (Cancel / Escape - never a save into the person's folders) and never sends a second close into an open dialog, which is what stacked Word's 'You cannot close Microsoft Word because a
        dialog box is open' and left the next launch inheriting a blind, dialog-owned window."""
        import subprocess
        from core_organs.atlas import scanner as SC
        from . import perception_ladder as PL
        from .executor import _frame_enabled
        from .reveal import app_hung
        answered: List[str] = []
        if app_hung(self.hwnd):
            pid = PL._pid(self.hwnd)
            if pid:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
                time.sleep(0.8)
                return {"how": "the application was not responding: its process (launched by this run) was ended"}
        res = SC.close_owned(self.hwnd)
        for _ in range(3):                                                    # a card may follow the close request, and a card may be sitting in front of it already
            time.sleep(1.4)
            with contextlib.suppress(Exception):
                if self.ex is None or _frame_enabled(self.hwnd):
                    break
                got = self.ex._clear_owning_dialog()
                if not got:
                    break
                answered.append(got)
        if answered:
            res = dict(res or {})
            res["dialogs_answered_after_close"] = answered
        return res

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
                    if self._budget_out():                                           # an unattended run must end: what was not reached is written into the ledger with the reason, not silently dropped
                        self.report["error"] = f"the run's time budget ({self.spec.hours}h) ended: {len(tasks) - i + 1} procedure(s) of the guide were not attempted"
                        for rest in tasks[i - 1:]:
                            self.ledger.append({"goal": rest["goal"], "cite": rest["cite"], "source": rest["source"], "steps": len(rest["steps"]), "grounded": rest["grounded"],
                                                "disposition": "skipped", "reason": "not attempted: the run's time budget ended (the guide is longer than one run)"})
                        break
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
            if "practice" in self.phases:                                            # PERMUTATION AND COMBINATION: the guide used one route per control; here the alternatives are performed on purpose, measured and put back, so the routing model is fed examples the guide never produced (professor.perms)
                try:
                    from . import perms as PM
                    flat = [s for t in (tasks if "guide" in self.phases else []) for s in t["steps"]]
                    self.report["phases"]["practice"] = PM.practise(self.ex, self.fx, self.history, self.cat, self.spec.key, self.hwnd,
                                                                    toolkit=(self.profile.family if self.profile is not None else ""), archetype=self.arch.get("id", ""),
                                                                    mode=self.spec.mode, steps=flat, log=self.say)
                    self.ui.phase("practice", f"route permutations + order pairs practised: {self.report['phases']['practice'].get('routes', 0)} routes, "
                                              f"{self.report['phases']['practice'].get('pairs', 0)} pairs, {self.report['phases']['practice'].get('seconds', 0)}s (rows train the router)")
                except Exception as exc:
                    self.report["phases"]["practice"] = {"error": f"{type(exc).__name__}: {str(exc)[:140]}"}
            if os.environ.get("HOJAIGA_POINTER_COURSE", "") == "1":
                try:                                                    # the dot course: the Professor's own window, drags a dot across the screen and trains the motor model (professor.pointer_course)
                    from . import pointer_course as PC
                    self.report["phases"]["pointer_course"] = PC.run_course(learner=self.learner, log=self.say)
                except Exception as exc:
                    self.report["phases"]["pointer_course"] = {"error": f"{type(exc).__name__}: {str(exc)[:140]}"}
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
            if self.ex is not None:
                self._revealed += [x for x in (getattr(self.ex, "revealed_log", None) or []) if x not in self._revealed]     # what the executor showed mid-task is put back too
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
            from .executor import release_kept, stop_mirrors
            stop_mirrors()                                                   # the background tree readers stop with the window they were reading
            release_kept()
        with contextlib.suppress(Exception):
            # WHAT THE BACKGROUND TREE READER DID: the step loop never waited for a provider read (one Word frame read costs 22 s), so these numbers explain the wall clock to whoever reads the report.
            m = getattr(self.ex, "mirror", None) if self.ex is not None else None
            if m is not None:
                self.report["tree_mirror"] = m.stats()
            if self.ex is not None and getattr(self.ex, "modal_log", None):
                self.report["modals"] = (self.report.get("modals") or []) + [x["did"] for x in self.ex.modal_log]
            if self.ex is not None and getattr(self.ex, "eye_log", None):
                self.report["eye"] = list(self.ex.eye_log)      # what the eye saw in front of a step that no route could move, and whether it backed out of it
            if self.ex is not None and getattr(self.ex, "sibling_log", None):
                self.report["sibling_frames"] = list(self.ex.sibling_log)   # the run's own handle went to a shell and the application's interface was found on a sibling window
        try:
            self.report["phases"]["state_after"] = self.guard.after() if self.guard is not None else {}
        except Exception as exc:
            self.report["phases"]["state_after"] = {"error": f"{type(exc).__name__}: {str(exc)[:100]}"}
        with contextlib.suppress(Exception):
            if getattr(self, "_triggers", None) is not None:
                self.report["phases"]["triggers"] = self._triggers.summary()
        with contextlib.suppress(Exception):
            if hasattr(self, "_accumulated_pointer_stats"):
                self.report["phases"]["pointer"] = dict(self._accumulated_pointer_stats)
            elif self.ex is not None:
                self.report["phases"]["pointer"] = dict(self.ex.pointer_stats)
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


def run_app(key: str, tasks: int = 0, **kw: Any) -> Dict[str, Any]:
    spec = SPECS[key]
    if tasks:
        spec.max_tasks = tasks
    return AppRun(spec, **kw).run()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Run an application's guide against the real application")
    ap.add_argument("app", nargs="?", choices=sorted(SPECS))
    ap.add_argument("--tier", type=int, default=0, help="run every application of a tier, one after the other")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--tasks", type=int, default=0, help="how many procedures to run (0 = the plan's own number, -1 = every procedure of the guide)")
    ap.add_argument("--all", action="store_true", help="FULL BOOK: run every procedure the guide yields for this application, not the first N")
    ap.add_argument("--hours", type=float, default=0.0, help="wall-clock budget for the run; what it does not reach is written into the ledger with the reason")
    ap.add_argument("--no-vision", action="store_true")
    ap.add_argument("--visible", action="store_true", help="leave the owned window on screen (the person's mouse and keyboard are still never touched; focus is returned instantly)")
    ap.add_argument("--phases", default="guide", help="comma list of: guide, probe, explore, practice")
    ap.add_argument("--actions", default="", help="a file of actions the PERSON wrote (JSON [{goal, steps:[...]}] or text blocks): they replace the guide's procedures and run through the same grounding, safety and history path")
    a = ap.parse_args()
    keys = TIERS.get(a.tier, []) if a.tier else ([a.app] if a.app else [])
    for k in keys:
        if a.all or a.tasks < 0:
            SPECS[k].max_tasks = 10 ** 6                                             # the whole book
        elif a.tasks:
            SPECS[k].max_tasks = a.tasks
        if a.hours:
            SPECS[k].hours = a.hours
        run_app(k, max_attempts=a.attempts, vision=not a.no_vision, visible=a.visible, phases=tuple(x.strip() for x in a.phases.split(",") if x.strip()), actions=a.actions)
