"""
si_tests_behavior.py -- suite tests for the behavior-model layer (organ_48), scan knowledge
(organ_49), popup_mode and the organ_29/organ_30 hooks. Kept out of run_system_intelligence_tests.py
(same pattern as si_tests_extra.py); every function receives the suite's TestOutcome dataclass.

Live tests drive REAL apps (Notepad, Paint) in fresh, isolated windows that this module opens and
closes itself — a user's own windows/documents are never touched. A tier or app that cannot run
reports skipped / ENV-BLOCKED, never a fake pass.
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")

_u32 = ctypes.windll.user32


# --------------------------------------------------------------------------- helpers

def _tmpdb() -> str:
    return os.path.join(tempfile.gettempdir(), "hj_bm_" + uuid.uuid4().hex[:8] + ".db")


def _rm_db(path: str) -> None:
    for suf in ("", "-wal", "-shm"):
        try:
            os.remove(path + suf)
        except Exception:
            pass


def _top_windows(cls_sub: str) -> List[int]:
    out: List[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if _u32.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(256)
            _u32.GetClassNameW(h, b, 256)
            if cls_sub in b.value.lower():
                out.append(h)
        return True
    _u32.EnumWindows(cb, 0)
    return out


APPS = {"notepad": ("notepad.exe", "notepad"), "paint": ("mspaint.exe", "mspaintapp"),
        # a live XAML-island app (what #5 is about): ApplicationFrameWindow + CoreWindow children.
        # This is a LAUNCH registry (which exe to start, which class to find), never actuation logic.
        "calc": ("calc.exe", "applicationframewindow")}


class LiveApp:
    """Open a FRESH window of an app MINIMIZED (never raised, never focused), expose its hwnd,
    close it again. Never reuses (or closes) a window the user already had.

    park=True  (default) holds a background_window session for the whole `with` block, so low-level
               test calls see a laid-out window — the same state the scanner works in.
    park=False leaves the window truly minimized so the library entry points must park by
               themselves (that is what MIN1 verifies)."""

    def __init__(self, app: str, park: bool = True):
        self.app = app
        self.exe, self.cls = APPS[app]
        self.hwnd = 0
        self.ok = False
        self.why = ""
        self.park = park
        self._bg = None
        self.launch_note = ""

    def _await_window(self, before: "set[int]", seconds: float = 20.0) -> int:
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(0.4)
            new = [h for h in _top_windows(self.cls) if h not in before]
            if new:
                return new[0]
        return 0

    def _ours_stale(self) -> int:
        """A live window of this app's class that the OWNERSHIP registry says WE made (never the user's)."""
        from core_organs import background_window as bw
        for h in bw.ours_alive():
            b = ctypes.create_unicode_buffer(256)
            _u32.GetClassNameW(h, b, 256)
            if self.cls in b.value.lower() and (_u32.IsWindowVisible(h) or _u32.IsIconic(h)):
                return h
        return 0

    def _stabilize(self, fg_before: int, seconds: float = 6.0) -> None:
        """Apps run their own startup (session restore re-opens tabs, restores the window and
        activates it AFTER our minimize). Harness hygiene: keep the window minimized until it has
        stayed that way, and hand focus straight back to what the user was using."""
        from core_organs import background_window as bw
        self.launch_note = bw.stabilize_minimized(self.hwnd, fg_before, seconds)

    def __enter__(self):
        self.launch_note = ""
        fg_before = _u32.GetForegroundWindow()
        before = set(_top_windows(self.cls))
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags = 1                                       # STARTF_USESHOWWINDOW
            si.wShowWindow = 7                                   # SW_SHOWMINNOACTIVE
            subprocess.Popen([self.exe], startupinfo=si)
        except Exception as exc:
            self.why = f"cannot launch {self.exe}: {exc}"
            return self
        self.hwnd = self._await_window(before)
        if not self.hwnd:
            # A single-instance app that refuses a second window is only a genuine ENV-BLOCK when some OTHER
            # process owns the live window. If the live one is OURS (a test that died mid-run), that is a harness
            # leak and self-healing is the honest move: close our own window, launch again, wait once more.
            stale = self._ours_stale()
            if stale:
                from core_organs import universal_scan as us
                if us.close_window(stale, timeout_s=6.0, discard_unsaved=True):
                    self.launch_note = f"reclaimed our own leaked window {stale}; relaunched"
                    self.hwnd = self._await_window(before)
        if not self.hwnd:
            self.why = "no new window appeared"
            return self
        from core_organs import background_window as bw
        bw.mark_ours(self.hwnd)                                  # this module created it: safe to park/close, and
        # the suite's boundary reclaim can find it even if this test dies before __exit__
        _u32.ShowWindow(self.hwnd, 7)                            # minimize without activating (some apps ignore the launch flag)
        self._stabilize(fg_before)
        # readiness: wait until the UIA tree actually exposes controls (a loaded machine is slow)
        try:
            import uiautomation as auto
            end = time.time() + 20
            while time.time() < end:
                try:
                    if len(auto.ControlFromHandle(self.hwnd).GetChildren()) >= 2:
                        break
                except Exception:
                    pass
                time.sleep(0.5)
        except Exception:
            pass
        time.sleep(1.0)
        if self.park:
            from core_organs import background_window as bw
            self._bg = bw.BackgroundSession(self.hwnd)
            self._bg.__enter__()
            time.sleep(1.0)                                      # let the restored layout settle
        self.ok = True
        return self

    def __exit__(self, *exc):
        if self._bg is not None:
            try:
                self._bg.__exit__(None, None, None)
            except Exception:
                pass
        if self.hwnd:
            try:
                _u32.PostMessageW(self.hwnd, 0x0010, 0, 0)          # WM_CLOSE
                end = time.time() + 4
                while time.time() < end and _u32.IsWindow(self.hwnd):
                    time.sleep(0.2)
                if _u32.IsWindow(self.hwnd):                        # "save changes?" -> cancel/close
                    from core_organs import headless_input as hin
                    for w in hin.popup_windows(self.hwnd):
                        _u32.PostMessageW(w, 0x0010, 0, 0)
                    _u32.PostMessageW(self.hwnd, 0x0010, 0, 0)
            except Exception:
                pass
        return False


def _title(h: int) -> str:
    b = ctypes.create_unicode_buffer(300)
    _u32.GetWindowTextW(h, b, 300)
    return b.value


def _wait_dialog(hwnd: int, timeout_s: float = 8.0) -> List[int]:
    """Poll (bounded) for a visible dialog of the app instead of guessing a delay."""
    from core_organs import headless_input as hin
    end = time.time() + timeout_s
    while time.time() < end:
        d = [w for w in hin.popup_windows(hwnd) if _u32.IsWindowVisible(w)]
        if d:
            time.sleep(0.2)
            return d
        time.sleep(0.1)
    return []


def _bm():
    from core_organs import organ_48_app_behavior_model as bm
    return bm


# --------------------------------------------------------------------------- BM1: pack format

def run_bm1(TestOutcome):
    """BM1: knowledge-pack format validates strictly, enforces the trust cap, loads as unverified data"""
    bm = _bm()
    checks: List[Tuple[str, bool, str]] = []
    good = {"schema": bm.PACK_SCHEMA, "app": "zzdemo", "trust": "catalog",
            "modes": [{"name": "m1", "indicator": [{"kind": "title_contains", "value": "demo"}]}],
            "commands": [{"name": "Do It", "shortcut": "ctrl+d", "risk": "E1",
                          "post": [{"kind": "window_opened"}]}],
            "templates": [{"name": "make a thing", "aliases": ["build a thing"],
                           "steps": [{"id": "s1", "goal": "g", "do": [{"verb": "key", "keys": "ctrl+d"}],
                                      "post": [{"kind": "ui_changed"}]}]}]}
    checks.append(("valid-pack-accepted", bm.validate_pack(good) == [], str(bm.validate_pack(good))))
    bad_cases = {
        "wrong-schema": dict(good, schema="x/1"),
        "self-declared-learned": dict(good, trust="learned"),
        "unknown-assertion": dict(good, commands=[{"name": "c", "post": [{"kind": "feels_right"}]}]),
        "unknown-verb": dict(good, templates=[{"name": "t", "steps": [
            {"id": "s", "goal": "g", "do": [{"verb": "telepathy"}], "post": []}]}]),
        "dup-step-id": dict(good, templates=[{"name": "t", "steps": [
            {"id": "s", "goal": "g", "post": []}, {"id": "s", "goal": "g2", "post": []}]}]),
        "bad-risk": dict(good, commands=[{"name": "c", "risk": "E9"}]),
        "no-target": {"schema": bm.PACK_SCHEMA},
    }
    for name, pk in bad_cases.items():
        errs = bm.validate_pack(pk)
        checks.append((f"rejects-{name}", bool(errs), (errs[:1] or ["NOT REJECTED"])[0]))

    db = _tmpdb()
    m = bm.BehaviorModel(db)
    try:
        r = m.load_pack(good)
        cmds = m.commands("zzdemo")
        tpl = m.match_template("zzdemo", "please build a thing for me")
        checks.append(("loads-as-catalog-unverified",
                       r["loaded"] and cmds and all(c["source"] == "catalog" for c in cmds), str(r.get("counts"))))
        checks.append(("template-matches-alias", tpl is not None and tpl.name == "make a thing",
                       f"{tpl.name if tpl else None}"))
        rej = m.load_pack(dict(good, trust="learned"))
        checks.append(("invalid-pack-not-ingested", rej["loaded"] is False and "errors" in rej, "refused"))
        # directory packs shipped with the repo must all validate (the seed data is itself tested)
        shipped = m.load_pack_dir()
        bad = [x["file"] for x in shipped if not x.get("loaded")]
        checks.append(("shipped-packs-valid", bool(shipped) and not bad, f"{len(shipped)} packs, bad={bad}"))
        # the shipped seeds must be unverified: nothing ships as learned
        learned = m._conn.execute("SELECT COUNT(*) c FROM bm_templates WHERE source='learned'").fetchone()["c"]
        checks.append(("nothing-ships-learned", learned == 0, f"learned templates at load: {learned}"))
        blender = m.match_template("blender", "model a chair from scratch", archetype="3d_suite")
        checks.append(("chair-is-a-data-row", blender is not None and len(blender.steps) >= 4
                       and bool(blender.seed_note), f"{blender.name if blender else None}"))
    finally:
        m.close()
        _rm_db(db)
    passed = all(ok for _, ok, _ in checks)
    return TestOutcome(passed=passed,
                       evidence="; ".join(f"{n}={'OK' if ok else 'FAIL(' + d + ')'}" for n, ok, d in checks)[:900],
                       metrics={"checks": f"{sum(1 for _, ok, _ in checks if ok)}/{len(checks)}"})


# --------------------------------------------------------------------------- BM2: assertions

def run_bm2(TestOutcome):
    """BM2: pre/postconditions are machine-checkable; an unobservable effect is OPAQUE, never PASS"""
    bm = _bm()
    S = bm.ObservedState
    checks: List[Tuple[str, bool, str]] = []

    def chk(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    b = S(title="Untitled - Notepad", names=["file", "edit"], windows=[], ocr="Vertices 0  Faces 0",
          ocr_status="ok")
    a = S(title="a.txt - Notepad", names=["file", "edit", "file name"], windows=["save as"],
          values=["hello world"], ocr="Vertices 8  Faces 6", ocr_status="ok")
    ev = bm.evaluate
    chk("title_contains", ev([{"kind": "title_contains", "value": "a.txt"}], b, a).ok)
    chk("element_appeared", ev([{"kind": "element_appeared", "name": "file name"}], b, a).ok)
    chk("element_absent", ev([{"kind": "element_absent", "name": "zzz"}], b, a).ok)
    chk("window_opened", ev([{"kind": "window_opened", "title_contains": "save"}], b, a).ok)
    chk("value_contains", ev([{"kind": "value_contains", "text": "hello"}], b, a).ok)
    r = ev([{"kind": "ocr_number_increase", "pattern": r"vert\w*\s*([\d,]+)", "min_delta": 8}], b, a)
    chk("ocr_number_increase 0->8 (the 'verts' proof)", r.ok, r.text())
    r = ev([{"kind": "ocr_number_increase", "pattern": r"vert\w*\s*([\d,]+)", "min_delta": 9}], b, a)
    chk("ocr_number_increase rejects too-small delta", r.verdict == "FAIL", r.text())
    r = ev([{"kind": "title_contains", "value": "nope"}, {"kind": "window_opened"}], b, a)
    chk("one failing assertion fails the whole step", r.verdict == "FAIL", r.text())
    # honesty: OCR unavailable => SKIPPED => OPAQUE, never a pass
    a2 = S(title="x", ocr=None, ocr_status="skipped:pytesseract-missing")
    r = ev([{"kind": "ocr_number_increase", "pattern": r"vert\w*\s*([\d,]+)"}], b, a2)
    chk("unobservable tier => OPAQUE (not PASS)", r.verdict == "OPAQUE" and r.skipped, r.text())
    r = ev([{"kind": "ocr_contains", "text": "x"}, {"kind": "title_contains", "value": "x"}], b, a2)
    chk("skipped assertion never counts as satisfied but others still decide",
        r.verdict == "PASS" and len(r.skipped) == 1, r.text())
    r = ev([], b, a)
    chk("empty postcondition is OPAQUE", r.verdict == "OPAQUE")
    # file assertions on a real temp file
    tf = os.path.join(tempfile.gettempdir(), "hj_bm2_" + uuid.uuid4().hex[:6] + ".txt")
    with open(tf, "w", encoding="utf-8") as fh:
        fh.write("alpha beta")
    chk("file_exists + file_contains",
        ev([{"kind": "file_exists", "path": tf, "wait_s": 0.2},
            {"kind": "file_contains", "path": tf, "text": "beta", "wait_s": 0.2}], b, a).ok)
    chk("file_exists MISSING fails",
        ev([{"kind": "file_exists", "path": tf + ".nope", "wait_s": 0.2}], b, a).verdict == "FAIL")
    os.remove(tf)
    # slot substitution keeps templates data
    chk("slot substitution", bm.fmt_params({"x": ["{text}/{path}"]}, {"text": "T", "path": "P"}) == {"x": ["T/P"]})
    # mode indicators
    st = S(ocr="... Edit Mode ...", ocr_status="ok")
    chk("mode indicator via OCR regex",
        ev([{"kind": "ocr_regex", "pattern": r"edit\s+mode"}], None, st).ok)
    passed = all(ok for _, ok, _ in checks)
    return TestOutcome(passed=passed,
                       evidence="; ".join(f"{n}={'OK' if ok else 'FAIL(' + d + ')'}" for n, ok, d in checks)[:900],
                       metrics={"checks": f"{sum(1 for _, ok, _ in checks if ok)}/{len(checks)}"})


# --------------------------------------------------------------------------- BM3: model logic

def run_bm3(TestOutcome):
    """BM3: autonomy gate, trust climb/erosion, version demotion, state-machine path, effector learning"""
    bm = _bm()
    db = _tmpdb()
    m = bm.BehaviorModel(db)
    checks: List[Tuple[str, bool, str]] = []

    def chk(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
    try:
        post = [{"kind": "ui_changed"}]
        key = "zz:t:s"
        # ---- gate: (a) verified, (b) reversible, (c) checkable postcondition
        g = m.gate(key, risk="E1", post=post)
        chk("fresh reversible step -> SAFE_ATTEMPT (verify, don't trust)", g.action == "SAFE_ATTEMPT", g.reason)
        chk("no postcondition -> QUEUE", m.gate(key, risk="E1", post=[]).action == "QUEUE")
        chk("opaque -> QUEUE", m.gate(key, risk="E1", post=post, opaque=True).action == "QUEUE")
        chk("E2 never auto-executes", m.gate(key, risk="E2", post=post, allow_destructive=True).action == "QUEUE")
        chk("EU without unwind -> QUEUE", m.gate(key, risk="EU", post=post).action == "QUEUE")
        for _ in range(bm.GATE_MIN_SUCCESSES):
            m.record_step_outcome(key, "PASS")
        chk(f"{bm.GATE_MIN_SUCCESSES} verified successes -> EXECUTE", m.gate(key, risk="E1", post=post).action == "EXECUTE")
        chk("verified E2 still needs the explicit allow flag",
            m.gate(key, risk="E2", post=post, allow_destructive=False).action == "QUEUE"
            and m.gate(key, risk="E2", post=post, allow_destructive=True).action == "EXECUTE")
        c0 = m.step_stats(key)["confidence"]
        m.record_step_outcome(key, "FAIL")
        c1 = m.step_stats(key)["confidence"]
        chk("a failure erodes confidence and revokes unattended execution",
            c1 < c0 and m.gate(key, risk="E1", post=post).action == "SAFE_ATTEMPT", f"{c0:.2f}->{c1:.2f}")

        # ---- trust order + promotion rules
        cid = m.upsert_command("zz", {"name": "Thing", "menu_path": "File > Thing", "post": post}, source="catalog")
        chk("pack/catalog entry is NOT learned", m.commands("zz")[0]["source"] == "catalog")
        c_before = m.commands("zz")[0]["confidence"]
        m.command_outcome(cid, "PASS", "evidence", promote=True)
        row = m.commands("zz")[0]
        chk("verified outcome promotes to learned", row["source"] == "learned" and row["confidence"] > c_before,
            f"{row['source']} {c_before:.2f}->{row['confidence']:.2f}")
        m.upsert_command("zz", {"name": "Thing", "menu_path": "File > Thing", "post": post}, source="distilled")
        chk("a weaker source never overwrites a stronger one", m.commands("zz")[0]["source"] == "learned")

        # ---- version change demotes, never silently trusts
        m.check_version("zz", "hashA")
        chk("same version keeps trust", m.check_version("zz", "hashA") == 0
            and m.commands("zz")[0]["source"] == "learned")
        n = m.check_version("zz", "hashB")
        row = m.commands("zz")[0]
        chk("version change demotes learned->catalog + stale", n >= 1 and row["source"] == "catalog" and row["stale"],
            f"{n} demoted, now {row['source']} stale={row['stale']}")
        # a template earns `learned` only via a fully verified run
        m.upsert_template("zz", {"name": "t1", "steps": [{"id": "a", "goal": "g", "post": post}]}, source="archetype")
        tid = m._conn.execute("SELECT tpl_id FROM bm_templates WHERE name='t1'").fetchone()["tpl_id"]
        m.template_outcome(tid, "FAIL")
        conf_fail = m._conn.execute("SELECT confidence, source FROM bm_templates WHERE tpl_id=?", (tid,)).fetchone()
        m.template_outcome(tid, "PASS")
        conf_ok = m._conn.execute("SELECT confidence, source FROM bm_templates WHERE tpl_id=?", (tid,)).fetchone()
        chk("template: failure erodes, verified run promotes to learned",
            conf_ok["source"] == "learned" and conf_ok["confidence"] > conf_fail["confidence"],
            f"{conf_fail['confidence']:.2f}->{conf_ok['confidence']:.2f} {conf_ok['source']}")

        # ---- state machine: mode graph + shortest recovery path
        m.upsert_command("zz2", {"name": "to edit", "shortcut": "tab", "risk": "E1",
                                 "pre": [{"kind": "mode_is", "mode": "object"}],
                                 "post": [{"kind": "mode_is", "mode": "edit"}]}, source="catalog")
        m.upsert_command("zz2", {"name": "to sculpt", "shortcut": "ctrl+tab", "risk": "E1",
                                 "pre": [{"kind": "mode_is", "mode": "edit"}],
                                 "post": [{"kind": "mode_is", "mode": "sculpt"}]}, source="catalog")
        path = m.path_to_mode(["zz2"], "object", "sculpt")
        chk("BFS finds object->edit->sculpt", path and [c["name"] for c in path] == ["to edit", "to sculpt"],
            str([c["name"] for c in path] if path else None))
        chk("no path => None (no invention)", m.path_to_mode(["zz2"], "sculpt", "object") is None)
        st = bm.ObservedState(title="x", ocr="Edit Mode", ocr_status="ok")
        m.set = None
        m._conn.execute("INSERT OR REPLACE INTO bm_modes VALUES ('zz2','edit',?)",
                        (json.dumps([{"kind": "ocr_regex", "pattern": "edit mode"}]),))
        chk("current_mode read from perception", m.current_mode(["zz2"], st) == "edit")

        # ---- transitions are (state, action, effector) -> state', and repeats just count
        s0 = bm.ObservedState(title="Untitled - Notepad")
        s1 = bm.ObservedState(title="Untitled - Notepad", windows=["save as"])
        m.record_transition("zz3", s0, "key:ctrl+shift+s", "key", s1, "opened")
        m.record_transition("zz3", s0, "key:ctrl+shift+s", "key", s1, "opened")
        tr = m.transitions("zz3")
        chk("transition recorded once with count 2", len(tr) == 1 and tr[0]["count"] == 2)
        chk("doc-name changes don't fork the state",
            m.state_signature(bm.ObservedState(title="*a.txt - Notepad"))
            == m.state_signature(bm.ObservedState(title="b.txt - Notepad")))

        # ---- effector learning: what THIS app accepts floats to the top
        m.record_effector("zz4", "key", "key", False)
        m.record_effector("zz4", "key", "key", False)
        m.record_effector("zz4", "key", "menu_command", True)
        m.record_effector("zz4", "key", "menu_command", True)
        order = m.effector_order("zz4", "key", ["key", "menu_command"])
        chk("learned effector order flips to what works", order[0] == "menu_command", str(order))

        # ---- risk classifier: generic cues, E2 never explored
        chk("risk cues", bm.classify_risk("Delete") == "E2" and bm.classify_risk("Close tab") == "E2"
            and bm.classify_risk("Page setup") == "E1" and bm.classify_risk("Word wrap") == "EU")
        # ---- discovery budget: yield extends, flatline stops, hard cap holds
        b = bm.DiscoveryBudget(base_s=0.05, extend_s=0.3, max_s=0.5, patience=2)
        b.credit(5)
        time.sleep(0.08)
        extended = b.reason_to_stop() == ""
        b2 = bm.DiscoveryBudget(base_s=5, extend_s=1, max_s=10, patience=2)
        b2.credit(0)
        b2.credit(0)
        chk("budget: yield extends the deadline", extended)
        chk("budget: flattening stops early", b2.reason_to_stop() == "flattened")
    finally:
        m.close()
        _rm_db(db)
    passed = all(ok for _, ok, _ in checks)
    return TestOutcome(passed=passed,
                       evidence="; ".join(f"{n}={'OK' if ok else 'FAIL(' + d + ')'}" for n, ok, d in checks)[:1100],
                       metrics={"checks": f"{sum(1 for _, ok, _ in checks if ok)}/{len(checks)}"})


# --------------------------------------------------------------------------- BM4: harvesters

def run_bm4(TestOutcome):
    """BM4: harvest the app's own machine-readable artifacts (keymaps/settings/CLI registry) as unverified candidates"""
    bm = _bm()
    checks: List[Tuple[str, bool, str]] = []

    def chk(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
    vsc = '[ // comment\n {"key": "ctrl+shift+p", "command": "workbench.action.showCommands"},\n {"key": "ctrl+s", "command": "workbench.action.files.save"}]'
    got = bm.harvest_keymap_text(vsc)
    chk("json keybindings", {c["shortcut"] for c in got} == {"ctrl+shift+p", "ctrl+s"}, str(got[:1]))
    pyk = ('("object.mode_set", {"type": \'TAB\', "value": \'PRESS\'}, {"properties": []}),\n'
           '("mesh.extrude_region_move", {"type": \'E\', "value": \'PRESS\', "ctrl": True, "shift": True}, None)')
    got = bm.harvest_keymap_text(pyk)
    chk("python-literal keymap (exported-keymap shape)",
        {c["name"]: c["shortcut"] for c in got} == {"object.mode_set": "tab",
                                                    "mesh.extrude_region_move": "ctrl+shift+e"}, str(got))
    ini = "Save = Ctrl+S\nFind: Ctrl+F\nnoise line\nQuit=Alt+F4"
    got = bm.harvest_keymap_text(ini)
    chk("ini accelerator table", {c["name"]: c["shortcut"] for c in got}.get("Save") == "ctrl+s", str(got))
    st = bm.harvest_settings_schema('{"ui": {"dark": true, "scale": 2}, "autosave": false}')
    chk("settings schema -> opaque toggles", {c["name"] for c in st} == {"toggle ui.dark", "toggle autosave"}
        and all(c["opaque"] for c in st), str(st))
    cli = [sys.executable, "-c",
           "import json;print('noise');print('HJ_JSON'+json.dumps([{'name':'obj.add','description':'add'},'obj.del']))"]
    items, status = bm.harvest_cli_json(cli, marker="HJ_JSON", exe=sys.executable)
    chk("cli command-registry dump (marker + JSON)", status == "ok" and {i["name"] for i in items} == {"obj.add", "obj.del"},
        f"{status} {items}")
    items, status = bm.harvest_cli_json(["{exe}", "--x"], exe="")
    chk("missing exe self-reports skipped (not an error, not faked)", items == [] and status.startswith("skipped"), status)
    items, status = bm.harvest_cli_json([r"C:\definitely\not\here.exe"], exe="")
    chk("nonexistent binary self-reports skipped", status.startswith("skipped"), status)
    db = _tmpdb()
    m = bm.BehaviorModel(db)
    try:
        rep = bm.harvest_pack_sources(m, "zzapp", [{"kind": "cli_json", "cmd": cli, "marker": "HJ_JSON"},
                                                  {"kind": "keymap_file", "path": r"C:\nope\keymap.json"}],
                                      exe=sys.executable)
        cmds = m.commands("zzapp")
        chk("harvested entries land as catalog (unverified)", len(cmds) == 2 and all(c["source"] == "catalog" for c in cmds),
            str(rep))
        chk("missing artifact reported in 'skipped'", any("file-not-found" in x for x in rep["skipped"]), str(rep["skipped"]))
    finally:
        m.close()
        _rm_db(db)
    passed = all(ok for _, ok, _ in checks)
    return TestOutcome(passed=passed,
                       evidence="; ".join(f"{n}={'OK' if ok else 'FAIL(' + d + ')'}" for n, ok, d in checks)[:1000],
                       metrics={"checks": f"{sum(1 for _, ok, _ in checks if ok)}/{len(checks)}"})


# --------------------------------------------------------------------------- SC1: E0 crawl, two apps, same code

def run_sc1(TestOutcome):
    """SC1: read-only E0 crawl maps ANY app's menus through one code path; no clicks, popups unwound, time adapts"""
    bm = _bm()
    rows, fails, env = [], [], []
    for app in ("notepad", "paint"):
        db = _tmpdb()
        m = bm.BehaviorModel(db)
        with LiveApp(app) as la:
            if not la.ok:
                env.append(f"{app}: {la.why}")
                m.close()
                _rm_db(db)
                continue
            from core_organs import headless_input as hin
            title0 = _title(la.hwnd)
            t0 = time.time()
            rep = bm.crawl_e0(m, app, la.hwnd)
            dt = time.time() - t0
            cmds = m.commands(bm._app_key(app), limit=5000)
            accel = sum(1 for c in cmds if c["shortcut"])
            has_save = any(c["shortcut"] == "ctrl+s" for c in cmds)
            leftover = bm._open_popups(la.hwnd)
            same_title = _title(la.hwnd) == title0
            nested = sum(1 for c in cmds if c["menu_path"].count(">") >= 2)
            ok = (len(cmds) >= 15 and has_save and not leftover and same_title and rep["stopped"] == "complete"
                  and dt < 40)
            rows.append(f"{app}: {len(cmds)} cmds ({accel} w/ accelerators, {nested} nested) in {dt:.1f}s "
                        f"stop={rep['stopped']} leftover_popups={len(leftover)} title_unchanged={same_title}")
            if not ok:
                fails.append(app)
        m.close()
        _rm_db(db)
    if env and not rows:
        return TestOutcome(passed=False, env_blocked=True, evidence="; ".join(env))
    return TestOutcome(passed=not fails and bool(rows), evidence=" | ".join(rows) + (f" | FAILED: {fails}" if fails else "")
                       + (f" | skipped: {env}" if env else ""),
                       metrics={"apps_mapped": len(rows)})


# --------------------------------------------------------------------------- SC2: E1 sees what E0 cannot

def run_sc2(TestOutcome):
    """SC2: E1 reversible probing discovers a child window invisible to E0, then unwinds to baseline"""
    bm = _bm()
    db = _tmpdb()
    m = bm.BehaviorModel(db)
    try:
        with LiveApp("notepad") as la:
            if not la.ok:
                return TestOutcome(passed=False, env_blocked=True, evidence=la.why)
            from core_organs import headless_input as hin
            key = bm._app_key("notepad")
            bm.crawl_e0(m, "notepad", la.hwnd)
            e0_regions = m.regions(key)
            # E0 saw menus only: the Page Setup dialog's controls are not in any E0 knowledge
            cand = next((c for c in m.commands(key, limit=500)
                         if c["risk"] == "E1" and "page setup" in c["name"].lower()), None)
            if cand is None:
                return TestOutcome(passed=False, evidence="E0 produced no E1 'Page setup' candidate; names="
                                   + str([c["name"] for c in m.commands(key, limit=60)][:25]))
            baseline = list(hin.popup_windows(la.hwnd))
            res = bm.probe_e1(m, "notepad", la.hwnd, cand)
            back = [w for w in hin.popup_windows(la.hwnd) if w not in baseline]
            row = m.command_by_name(key, cand["name"])
            trs = m.transitions(key)
            ok = (res.get("probed") and res.get("effect_observed") and res.get("unwound") and res.get("promoted")
                  and not back and row and row["source"] == "learned" and len(trs) >= 1
                  and len(res.get("new_controls", [])) >= 3)
            # E2 must never be explored
            e2 = next((c for c in m.commands(key, limit=500) if c["risk"] == "E2"), None)
            e2_refused = e2 is not None and bm.probe_e1(m, "notepad", la.hwnd, e2).get("probed") is False
            ex = bm.explore_e1(m, "notepad", la.hwnd, max_actions=2, budget_s=30)
            gains = [bm.info_gain(c) for c in m.commands(key, limit=500) if c["risk"] == "E1"]
            return TestOutcome(
                passed=bool(ok and e2_refused),
                evidence=(f"probe '{cand['menu_path']}': effect={res.get('effect_observed')} "
                          f"new_windows={res.get('new_windows')} new_controls={len(res.get('new_controls', []))} "
                          f"effector={res.get('effector')} unwound={res.get('unwound')} promoted={res.get('promoted')} "
                          f"in {res.get('elapsed_s')}s; E0 knew {len(e0_regions)} child-window regions beforehand; "
                          f"E2 probe refused={e2_refused}; explore_e1 stop={ex['stopped']} probes={len(ex['probes'])}"),
                metrics={"controls_discovered_by_E1": len(res.get("new_controls", [])),
                         "regions_known_by_E0": len(e0_regions)})
    finally:
        m.close()
        _rm_db(db)


# --------------------------------------------------------------------------- PM1: probe-mode popups

def run_pm1(TestOutcome):
    """PM1: popup_mode — probe-opened dialogs are cancel-only (never accepted, never cached); expected dialogs are kept"""
    bm = _bm()
    from core_organs import popup_mode as pm
    from core_organs.organ_29_popup_handler import DesktopInteractionManager
    checks: List[Tuple[str, bool, str]] = []

    def chk(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
    pm.set_policy("task")
    pm.clear_expected()
    chk("default policy is task", pm.current_policy() == "task")
    pm.set_policy("probe")
    chk("probe policy visible cross-process (file flag)", pm.current_policy() == "probe")
    pm.set_policy("task")
    pm.expect_popup("Save As")
    chk("expected popup registered", pm.is_expected("Save As - Notepad") and not pm.is_expected("Other"))
    pm.clear_expected()
    with LiveApp("notepad") as la:
        if not la.ok:
            return TestOutcome(passed=False, env_blocked=True, evidence=la.why)
        from core_organs import headless_input as hin
        dim = DesktopInteractionManager()
        db = _tmpdb()
        m = bm.BehaviorModel(db)
        try:
            # --- probe policy: open a REAL dialog, hand it to organ_29, require a cancel-only close
            ok, note = bm.open_menu_path(la.hwnd, "File > Page setup")
            dlg = _wait_dialog(la.hwnd)
            chk("real dialog opened for the test", ok and bool(dlg), f"{note} dialogs={len(dlg)}")
            if dlg:
                pm.set_policy("probe")
                node = dim.wrap_hwnd(dlg[0])
                cached_before = dim.db.check_popup_history(node.title) if node else None     # global DB may hold older entries
                t0 = time.time()
                res = dim.resolve_and_mitigate(node) if node else (False, 0, 0, "no-node")
                dt = time.time() - t0
                time.sleep(0.4)
                gone = not _u32.IsWindow(dlg[0]) or not _u32.IsWindowVisible(dlg[0])
                chk("probe-mode closes via cancel_only", res[0] and res[3] == "cancel_only" and gone, f"{res} gone={gone}")
                chk("cancel-only is fast (no LLM tier)", dt < 2.0, f"{dt:.2f}s")
                cached_after = dim.db.check_popup_history(node.title) if node else None
                chk("nothing NEW written to the pathway cache in probe mode", cached_after == cached_before, f"before={cached_before} after={cached_after}")
            # --- expected popup in task mode is left alone
            pm.set_policy("task")
            ok, note = bm.open_menu_path(la.hwnd, "File > Page setup")
            dlg2 = _wait_dialog(la.hwnd)
            if dlg2:
                node2 = dim.wrap_hwnd(dlg2[0])
                pm.expect_popup(node2.title or "page setup")
                res2 = dim.resolve_and_mitigate(node2)
                still = _u32.IsWindow(dlg2[0]) and _u32.IsWindowVisible(dlg2[0])
                chk("expected dialog left open", res2[3] == "expected_keep" and still, f"{res2} still_open={still}")
                pm.clear_expected()
                _u32.PostMessageW(dlg2[0], 0x0010, 0, 0)               # test hygiene
            else:
                chk("second dialog opened", False,
                    f"open_menu_path -> ok={ok} note={note!r}; app windows now: "
                    f"{[(_title(w), bm._win_class(w), bool(_u32.IsWindowVisible(w))) for w in hin.popup_windows(la.hwnd)]}; "
                    f"expanded menu items: {len(bm._open_popups(la.hwnd))}")
        finally:
            pm.set_policy("task")
            pm.clear_expected()
            m.close()
            _rm_db(db)
    passed = all(ok for _, ok, _ in checks)
    return TestOutcome(passed=passed,
                       evidence="; ".join(f"{n}={'OK' if ok else 'FAIL(' + d + ')'}" for n, ok, d in checks)[:900],
                       metrics={"checks": f"{sum(1 for _, ok, _ in checks if ok)}/{len(checks)}"})


# --------------------------------------------------------------------------- TPL1: pack-driven task run

def _png_ok(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(8) == b"\x89PNG\r\n\x1a\n"
    except Exception:
        return False


def run_tpl1(TestOutcome):
    """TPL1: a task decomposed from DATA templates runs verified leaf-by-leaf on two unrelated apps"""
    bm = _bm()
    rows, fails = [], []
    db = _tmpdb()
    m = bm.BehaviorModel(db)
    try:
        m.load_pack_dir()
        for app, task, ext, params in (
                ("notepad", "write text and save as file", ".txt", {"text": "hello " + uuid.uuid4().hex[:6]}),
                ("paint", "save the image as file", ".png", {})):
            with LiveApp(app) as la:
                if not la.ok:
                    return TestOutcome(passed=False, env_blocked=True, evidence=la.why)
                path = os.path.join(tempfile.gettempdir(), "hj_tpl1_" + uuid.uuid4().hex[:6] + ext)
                runner = bm.TemplateRunner(m)
                res = runner.run(app, task, dict(params, path=path), hwnd_fn=lambda h=la.hwnd: h
                                 if _u32.IsWindow(h) else 0)
                # independent ground truth, not the runner's own claim
                if ext == ".txt":
                    truth = os.path.exists(path) and params["text"] in open(path, encoding="utf-8", errors="replace").read()
                else:
                    truth = os.path.exists(path) and _png_ok(path)
                good = res.get("completed") and truth
                rows.append(f"{app}: completed={res.get('completed')} truth={truth} {res.get('elapsed_s')}s "
                            f"leaves={[(l['step_id'], l['verdict'], l['attempts']) for l in res.get('leaves', [])]}")
                if not good:
                    fails.append(app)
                try:
                    os.remove(path)
                except Exception:
                    pass
        # verify-only leaf must not act: a template whose only step has an explicit empty `do`
        m.upsert_template("@archetype:text_editor", {"name": "zz verify only", "steps": [
            {"id": "v", "goal": "check", "risk": "E1", "do": [],
             "post": [{"kind": "file_exists", "path": "{path}", "wait_s": 0.1}]}]}, source="archetype")
        r = bm.TemplateRunner(m, loop=None).run("notepad", "zz verify only", {"path": r"C:\nope\x"},
                                                hwnd_fn=lambda: 1)
        vo = r["matched"] and r["leaves"][0]["effectors"] == [] and r["leaves"][0]["verdict"] in ("FAIL",)
        rows.append(f"verify-only leaf acted={'NO' if vo else 'YES?'}")
        if not vo:
            fails.append("verify-only")
        # unmatched task is reported honestly, not invented
        r2 = bm.TemplateRunner(m).run("notepad", "compose a symphony for orchestra", {})
        if r2.get("matched"):
            fails.append("unmatched-task-invented")
        rows.append(f"unmatched task matched={r2.get('matched')}")
        learned = m._conn.execute("SELECT COUNT(*) c FROM bm_templates WHERE source='learned'").fetchone()["c"]
        rows.append(f"templates promoted to learned by verified runs: {learned}")
        if learned < 2:
            fails.append("no-promotion")
    finally:
        m.close()
        _rm_db(db)
    return TestOutcome(passed=not fails, evidence=" | ".join(rows) + (f" | FAILED: {fails}" if fails else ""),
                       metrics={"apps": 2})


# --------------------------------------------------------------------------- DAY1: unattended day

def run_day1(TestOutcome):
    """DAY1: unattended task-list day: never stalls the queue, escalates what it must, report matches ground truth"""
    bm = _bm()
    db = _tmpdb()
    m = bm.BehaviorModel(db)
    files: Dict[str, str] = {}
    try:
        m.load_pack_dir()
        with LiveApp("notepad") as ln, LiveApp("paint") as lp:
            if not (ln.ok and lp.ok):
                return TestOutcome(passed=False, env_blocked=True, evidence=ln.why or lp.why)
            hw = {"notepad": ln.hwnd, "paint": lp.hwnd}
            txt, png = [os.path.join(tempfile.gettempdir(), "hj_day_" + uuid.uuid4().hex[:6] + e) for e in (".txt", ".png")]
            marker = "daytask-" + uuid.uuid4().hex[:5]
            tasks = [
                {"id": "T1 write note", "app": "notepad", "task": "write text and save as file",
                 "params": {"text": marker, "path": txt}, "expect": "DONE", "file": txt},
                {"id": "T2 save drawing", "app": "paint", "task": "save the image as file",
                 "params": {"path": png}, "expect": "DONE", "file": png},
                {"id": "T3 no such skill", "app": "notepad", "task": "compose a symphony for orchestra",
                 "params": {}, "expect": "FAILED", "file": None},
                {"id": "T4 3D chair (no 3D app here)", "app": "blender", "task": "model a simple chair",
                 "params": {}, "expect": "FAILED_OR_ESCALATED", "file": None},
            ]
            runner = bm.TemplateRunner(m)
            orig_find = runner.g.find_window
            runner.g.find_window = lambda hint, _o=orig_find: hw.get(hint) or _o(hint)

            def verify(task, res):
                f = task.get("file")
                if not f:
                    return False, "no artifact expected"
                if f.endswith(".png"):
                    return os.path.exists(f) and _png_ok(f), "png on disk" if os.path.exists(f) else "missing"
                try:
                    return marker in open(f, encoding="utf-8", errors="replace").read(), "text on disk"
                except Exception as exc:
                    return False, f"{type(exc).__name__}"
            t0 = time.time()
            rep = bm.run_task_list(tasks, model=m, runner=runner, verify_fn=verify)
            dt = time.time() - t0
            # ground truth vs the system's own report
            truth_done = {t["id"] for t in tasks if t.get("file") and os.path.exists(t["file"])}
            said_done = {x["task"] for x in rep["done"]}
            said_not = {x["task"] for x in rep["attempted_failed"]} | {x["task"] for x in rep["escalated"]}
            honest = said_done == truth_done and said_not == {t["id"] for t in tasks} - truth_done
            all_accounted = len(said_done) + len(said_not) == len(tasks)
            for f in (txt, png):
                try:
                    os.remove(f)
                except Exception:
                    pass
            return TestOutcome(
                passed=bool(honest and all_accounted and len(said_done) == 2),
                evidence=(f"report done={rep['counts']['done']} failed={rep['counts']['attempted_failed']} "
                          f"escalated={rep['counts']['escalated']} in {dt:.0f}s; self-report==ground-truth: {honest}; "
                          f"every task accounted for: {all_accounted}; "
                          f"failed reasons={[ (x['task'], x['reason'][:50]) for x in rep['attempted_failed']]}"),
                metrics={"done": rep["counts"]["done"], "failed": rep["counts"]["attempted_failed"],
                         "escalated": rep["counts"]["escalated"]})
    finally:
        m.close()
        _rm_db(db)


# --------------------------------------------------------------------------- SCK1: scanner integration

def run_sck1(TestOutcome):
    """SCK1: organ_30 scan consults organ_48 knowledge: E0 map first, cached on re-scan, scan result carries knowledge"""
    db = _tmpdb()
    os.environ["HOJAIGA_BEHAVIOR_DB"] = db
    try:
        from core_organs import organ_48_app_behavior_model as bm
        bm._MODEL = None
        bm.DB_PATH = db
        from core_organs import organ_30_app_scanner as sc
        with LiveApp("paint") as la:
            if not la.ok:
                return TestOutcome(passed=False, env_blocked=True, evidence=la.why)
            scanner = sc.AppScanner()
            try:
                t0 = time.time()
                r1 = scanner.scan_app_active("paint", la.hwnd)
                d1 = time.time() - t0
                t0 = time.time()
                r2 = scanner.scan_app_active("paint", la.hwnd)
                d2 = time.time() - t0
            finally:
                scanner.stop()
            if r1.get("status") != "completed":
                return TestOutcome(passed=False, env_blocked=True, evidence=f"scanner unavailable: {r1.get('message')}")
            k1, k2 = r1.get("knowledge", {}), r2.get("knowledge", {})
            ok = (bool(k1) and k1.get("known_after", 0) >= 15 and "skipped" in k2.get("e0", {})
                  and k2.get("known_before", 0) >= k1.get("known_after", 0) - 1 and d2 < d1)
            return TestOutcome(
                passed=bool(ok),
                evidence=(f"scan1: {r1['controls_scanned']} controls, learned {k1.get('known_after')} commands "
                          f"(E0 {k1.get('e0', {}).get('elapsed_s')}s) in {d1:.1f}s; "
                          f"scan2: E0 {list(k2.get('e0', {}).keys())[:1]} cached, skipped_known={k2.get('skipped_known')}, "
                          f"catalog_only={k2.get('catalog_only')} in {d2:.1f}s; stop={k1.get('stopped')}"),
                metrics={"scan1_s": round(d1, 1), "scan2_s": round(d2, 1)})
    finally:
        os.environ.pop("HOJAIGA_BEHAVIOR_DB", None)
        _rm_db(db)


# --------------------------------------------------------------------------- LM1: layout map

def run_lm1(TestOutcome):
    """LM1: every section + control + its window-relative position is mapped generically, deepening is reversible"""
    bm = _bm()
    from core_organs import organ_50_layout_map as lm
    rows, fails = [], []
    for app in ("notepad", "paint"):
        db = _tmpdb()
        m = bm.BehaviorModel(db)
        try:
            with LiveApp(app) as la:
                if not la.ok:
                    return TestOutcome(passed=False, env_blocked=True, evidence=la.why)
                before_names: List[str] = []
                for _ in range(6):                              # wait for the UI to settle: two equal reads
                    o1 = bm.observe(la.hwnd)
                    time.sleep(0.7)
                    o2 = bm.observe(la.hwnd)
                    before_names = o2.names
                    if o1.uia_signature() == o2.uia_signature():
                        break
                before = True
                t0 = time.time()
                s = lm.map_layout(m, app, la.hwnd, version_hash="v1")
                dt = time.time() - t0
                key = bm._app_key(app)
                rows_db = m._conn.execute("SELECT rx0,ry0,rx1,ry1,offscreen,region_kind FROM bm_layout WHERE app_key=?",
                                          (key,)).fetchall()
                in_range = all(-0.02 <= r["rx0"] <= 1.02 and -0.02 <= r["ry0"] <= 1.02 for r in rows_db if not r["offscreen"])
                kinds = s.get("region_kinds", {})
                f = lm.where(m, key, "File", role="menuitem") or lm.where(m, key, "File")
                file_top = bool(f) and f[0]["center_rel"][1] < 0.2 and "menubar" in f[0]["region"]
                cached = lm.layout_cached(m, key, "v1") is not None
                stale = lm.layout_cached(m, key, "v2") is None                 # new version => must re-map
                names_b, names_a = set(before_names), set(bm.observe(la.hwnd).names)
                jac = len(names_b & names_a) / max(len(names_b | names_a), 1)
                view_ok = jac >= 0.97                        # dynamic text (status lines) may change; structure must not
                ok = (s.get("controls", 0) >= 40 and "menubar" in kinds and len(kinds) >= 4 and in_range
                      and file_top and cached and stale and view_ok and dt < 60)
                if app == "paint":
                    canvas = [r for r in s.get("opaque_regions", [])]
                    # window-size independent: a drawing surface UIA cannot see into is reported opaque
                    ok = ok and s.get("controls", 0) >= 100 and bool(canvas)
                else:
                    ok = ok and not s.get("opaque_regions")                    # readable text editor is NOT opaque
                rows.append(f"{app}: {s.get('controls')} controls in {s.get('regions')} regions {kinds} "
                            f"deepen={s.get('deepen')} opaque={len(s.get('opaque_regions', []))} "
                            f"File@{f[0]['center_rel'] if f else None} view_similarity={jac:.3f} {dt:.1f}s")
                conds = {"controls>=40": s.get("controls", 0) >= 40, "menubar": "menubar" in kinds, "kinds>=4": len(kinds) >= 4,
                         "coords_in_range": in_range, "File_top": file_top, "cached": cached, "stale_on_new_version": stale,
                         "view_ok": view_ok, "fast": dt < 60}
                if app == "paint":
                    conds["paint_canvas_opaque"] = bool(s.get("opaque_regions"))
                else:
                    conds["notepad_not_opaque"] = not s.get("opaque_regions")
                rows.append("conds=" + str({k: v for k, v in conds.items() if not v} or "all-true"))
                if not ok:
                    fails.append(app)
        finally:
            m.close()
            _rm_db(db)
    return TestOutcome(passed=not fails, evidence=" | ".join(rows) + (f" | FAILED: {fails}" if fails else ""),
                       metrics={"apps": 2})


# --------------------------------------------------------------------------- MIN1: never seen, never focused

class _ScreenMonitor:
    """Samples every ~20 ms: did the target app (or any of its windows) ever become the foreground
    window, and how many pixels of any of its windows were ever on a REAL monitor?"""

    def __init__(self, hwnd: int):
        import threading
        self.hwnd = hwnd
        self.pid = ctypes.c_ulong()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(self.pid))
        self.fg_hits = 0
        self.max_px = 0
        self.exposed_samples = 0
        self.run_ms = 0.0
        self.max_run_ms = 0.0
        self.fg_run_ms = 0.0
        self.max_fg_run_ms = 0.0
        self.samples = 0
        self.who: Dict[str, int] = {}
        self.phase = "start"
        self.by_phase: Dict[str, float] = {}
        import collections
        self._dts = collections.deque(maxlen=101)
        self._ep_start = None
        self._fg_start = None
        self.max_fg_raw_ms = 0.0
        self._rgn = ctypes.windll.gdi32.CreateRectRgn(0, 0, 0, 0)       # ONE scratch region for GetWindowRgn (freed in stop(): no GDI leak)
        self._own: Dict[int, Tuple[float, bool]] = {}
        self._stop = False
        self._target_cls = ""
        self._t = threading.Thread(target=self._run, daemon=True)

    def _screens(self):
        from core_organs import background_window as bw
        return bw._screens()

    def _cls(self, h: int) -> str:
        b = ctypes.create_unicode_buffer(128)
        _u32.GetClassNameW(h, b, 128)
        return b.value

    def _ours(self, h: int) -> bool:
        """The target window itself, or a popup/dialog/flyout of the same process (different class).
        Other main windows of the same app (same class) belong to someone else. Cached for 0.5 s per window: the answer is asked for every window
        on every sample, and a monitor that burns the interpreter slows the very thing it is measuring."""
        if h == self.hwnd:
            return True
        c = self._own.get(h)
        now = time.perf_counter()
        if c and now - c[0] < 0.5:
            return c[1]
        from core_organs import background_window as bw
        v = bool(bw.holds_app_focus(h, self.hwnd, self.pid.value))
        self._own[h] = (now, v)
        return v

    def _period(self) -> float:
        """The sampling period as it really was (median gap between quiet samples): the resolution of every number this monitor reports."""
        d = sorted(self._dts)
        return d[len(d) // 2] if d else 10.0

    def _tids(self):
        if time.perf_counter() - getattr(self, "_tids_at", -9) > 0.4:
            self._tids_at = time.perf_counter()
            try:
                import psutil
                self._tid_list = [t.id for t in psutil.Process(self.pid.value).threads()]
            except Exception:
                self._tid_list = []
        return self._tid_list

    def _run(self):
        screens = self._screens()
        self._target_cls = self._cls(self.hwnd)
        while not self._stop:
            try:
                fg = _u32.GetForegroundWindow()
                now0 = time.perf_counter()
                dfg = (now0 - getattr(self, "_lastfg", now0)) * 1000
                self._lastfg = now0
                from core_organs import background_window as _bwf
                present = _bwf.user_idle_ms() <= _bwf.FOCUS_IDLE_MS                     # a person is at the keyboard / mouse right now
                if self._ours(fg):
                    self.fg_hits += 1
                    if self._fg_start is None:
                        self._fg_start = now0
                    raw_run = (now0 - self._fg_start) * 1000 + self._period()
                    self.max_fg_raw_ms = max(self.max_fg_raw_ms, raw_run)
                    if present:                                                          # only a hold WHILE the user is present can misdirect their input
                        self.fg_run_ms = raw_run
                        self.max_fg_run_ms = max(self.max_fg_run_ms, self.fg_run_ms)
                    else:
                        self.fg_run_ms = 0.0
                else:
                    self._fg_start = None
                    self.fg_run_ms = 0.0
                worst = 0

                @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
                def cb(h, _):
                    nonlocal worst
                    p = ctypes.c_ulong()
                    _u32.GetWindowThreadProcessId(h, ctypes.byref(p))
                    if self._ours(h) and _u32.IsWindowVisible(h) and not _u32.IsIconic(h):
                        # GetWindowRgn is USER32, not gdi32 (CreateRectRgn is the GDI half). Asked of gdi32 it raised
                        # AttributeError inside this callback on every sweep: ctypes swallows a callback exception, so
                        # the NULLREGION skip never happened, the overlap math after it never ran, and stderr filled
                        # with 11k tracebacks per MIN1.
                        if _u32.GetWindowRgn(h, self._rgn) == 1:            # NULLREGION: a window with an empty region draws nothing anywhere
                            return True
                        if _u32.GetWindowLongW(h, -20) & 0x00080000:        # a LAYERED window at alpha 0 puts no pixel on any screen
                            _al, _fl, _ck = ctypes.c_ubyte(255), wt.DWORD(0), wt.DWORD(0)
                            if _u32.GetLayeredWindowAttributes(h, ctypes.byref(_ck), ctypes.byref(_al), ctypes.byref(_fl)) and (_fl.value & 2) and _al.value == 0:
                                return True
                        r = wt.RECT()
                        _u32.GetWindowRect(h, ctypes.byref(r))
                        for sl, st, sr, sb in screens:
                            w = min(r.right, sr) - max(r.left, sl)
                            hh = min(r.bottom, sb) - max(r.top, st)
                            if w > 0 and hh > 0:
                                worst = max(worst, w * hh)
                                if w * hh > 16:                    # WHO is on screen (a dialog of the app is not the app's main window)
                                    tb = ctypes.create_unicode_buffer(60)
                                    _u32.GetWindowTextW(h, tb, 60)
                                    k = ("MAIN" if h == self.hwnd else "popup") + ":" + self._cls(h)[:22] + ":" + tb.value[:22]
                                    self.who[k] = self.who.get(k, 0) + 1
                    return True
                # Sampling resolution is the measurement: a full-desktop EnumWindows took ~85 ms per sample (a one-frame flash then READ as 85-170 ms).
                # The app's own UI threads hold its windows and its flyouts: enumerating just those is ~100x cheaper (a few ms per sample).
                tids = self._tids()
                if tids:
                    for _tid in tids:
                        _u32.EnumThreadWindows(_tid, cb, 0)
                else:
                    _u32.EnumWindows(cb, 0)
                now = time.perf_counter()
                dt_ms = (now - getattr(self, "_last", now)) * 1000
                self._last = now
                self.samples += 1
                self.max_px = max(self.max_px, worst)
                period = self._period()
                if worst > 16:
                    self.exposed_samples += 1
                    # an EPISODE is first-sighting -> last-sighting (+ one sampling period), NOT the sum of raw sample gaps: a sample that was
                    # starved of the interpreter for 150 ms must not turn a one-frame flash into 150 ms of exposure
                    if self._ep_start is None:
                        self._ep_start = now
                    self.by_phase[self.phase] = round(self.by_phase.get(self.phase, 0.0) + min(dt_ms, 2 * period), 1)
                    self.run_ms = (now - self._ep_start) * 1000 + period
                    self.max_run_ms = max(self.max_run_ms, self.run_ms)
                else:
                    self._ep_start = None
                    self.run_ms = 0.0
                    self._dts.append(dt_ms)
            except Exception:
                pass
            time.sleep(0.02)

    def start(self):
        self._t.start()
        return self

    def stop(self):
        self._stop = True
        self._t.join(timeout=2)
        try:
            ctypes.windll.gdi32.DeleteObject(self._rgn)
        except Exception:
            pass


def run_min1(TestOutcome):
    """MIN1: a MINIMIZED app is scanned + operated without ever being shown or focused, with full-quality results"""
    bm = _bm()
    from core_organs import organ_50_layout_map as lm
    from core_organs import background_window as bw
    from core_organs import headless_input as hin
    db = _tmpdb()
    m = bm.BehaviorModel(db)
    rows, fails = [], []
    try:
        for app in ("notepad", "paint"):
            with LiveApp(app, park=False) as la:                 # truly minimized; entry points must park themselves
                if not la.ok:
                    return TestOutcome(passed=False, env_blocked=True, evidence=la.why)
                key = bm._app_key(app)
                orig = bw._placement(la.hwnd).rcNormalPosition
                orig_rect = (orig.left, orig.top, orig.right, orig.bottom)
                fg0 = _u32.GetForegroundWindow()
                mon = _ScreenMonitor(la.hwnd).start()
                t0 = time.time()
                mon.phase = "e0"
                e0 = bm.crawl_e0(m, app, la.hwnd)
                mon.phase = "layout"
                lay = lm.map_layout(m, app, la.hwnd)
                cand = next((c for c in m.commands(key, limit=500) if c["risk"] == "E1"
                             and "page setup" in c["name"].lower()), None)
                mon.phase = "e1-probe"
                probe = bm.probe_e1(m, app, la.hwnd, cand) if cand else {"skipped": "no page-setup in this app"}
                mon.phase = "capture"
                # OCR/vision precondition: PrintWindow only works on a non-minimized window
                with bw.BackgroundSession(la.hwnd):
                    # a window restored a moment ago has not repainted yet: poll (bounded) like the product's rung does
                    t_cap = time.time()
                    img, why = hin.capture_window(la.hwnd)
                    while img is None and time.time() - t_cap < 3.0:
                        time.sleep(0.2)
                        img, why = hin.capture_window(la.hwnd)
                tpl = {}
                mon.phase = "template"
                if app == "notepad":
                    m.load_pack_dir()
                    path = os.path.join(tempfile.gettempdir(), "hj_min1_" + uuid.uuid4().hex[:6] + ".txt")
                    text = "minimized-" + uuid.uuid4().hex[:5]
                    tpl = bm.TemplateRunner(m).run(app, "write text and save as file", {"text": text, "path": path},
                                                   hwnd_fn=lambda h=la.hwnd: h if _u32.IsWindow(h) else 0)
                    truth = os.path.exists(path) and text in open(path, encoding="utf-8", errors="replace").read()
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                else:
                    truth = True
                dt = time.time() - t0
                mon.stop()
                end_orig = bw._placement(la.hwnd).rcNormalPosition
                restored = (end_orig.left, end_orig.top, end_orig.right, end_orig.bottom) == orig_rect
                still_min = bool(_u32.IsIconic(la.hwnd))
                f = lm.where(m, key, "File")
                file_top = bool(f) and f[0]["center_rel"][1] < 0.2
                ok = (mon.max_fg_run_ms < 120 and mon.max_run_ms < 120 and still_min and restored
                      and e0["window_mode"] == "parked" and e0["ingested"] >= 25
                      and lay.get("controls", 0) >= 40 and file_top and img is not None
                      and (not cand or (probe.get("effect_observed") and probe.get("unwound")))
                      and (app != "notepad" or (tpl.get("completed") and truth)))
                rows.append(f"{app}: mode={e0['window_mode']} E0={e0['ingested']} cmds, layout={lay.get('controls')} controls "
                            f"(File@{f[0]['center_rel'] if f else None}), E1 probe effect={probe.get('effect_observed')} "
                            f"unwound={probe.get('unwound')}, capture={'ok' if img is not None else why}, "
                            + (f"template completed={tpl.get('completed')} truth={truth}, " if tpl else "")
                            + f"| FOCUS: target-held-foreground while-user-present longest={mon.max_fg_run_ms:.0f}ms (raw incl. idle {mon.max_fg_raw_ms:.0f}ms; {mon.fg_hits}/{mon.samples} samples), brief-exposure-samples(>16px)={mon.exposed_samples} "
                            f"longest-continuous-exposure={mon.max_run_ms:.0f}ms max-visible-px={mon.max_px} exposed-by={dict(sorted(mon.who.items(), key=lambda kv: -kv[1])[:4])} exposure-ms-by-phase={mon.by_phase} sampling-period~{mon._period():.0f}ms | ended minimized={still_min} placement-restored={restored} {dt:.0f}s"
                            + (f" | harness note: {la.launch_note}" if la.launch_note else ""))
                if not ok:
                    fails.append(app)
    finally:
        m.close()
        _rm_db(db)
    return TestOutcome(passed=not fails, evidence=" || ".join(rows) + (f" || FAILED: {fails}" if fails else ""),
                       metrics={"apps": 2})


def run_cap2(TestOutcome):
    """CAP2 (#4): a MINIMIZED window is captured anyway - blank/low-variance detection escalates the honest ladder
    (PrintWindow -> DAP print/BitBlt -> restore->capture->re-hide) - the rung used is REPORTED, and every window is
    left exactly as the user had it: still minimized, placement intact, focus handed back (law [6] in miniature)."""
    from core_organs import background_window as bw
    from core_organs import headless_input as hin
    from core_organs import organ_24_dap as o24

    rows, checks, rungs = [], {}, []
    for app in ("notepad", "paint"):
        with LiveApp(app, park=False) as la:
            if not la.ok:
                return TestOutcome(passed=False, env_blocked=True, evidence=f"{app}: {la.why}")
            hwnd = la.hwnd
            if not _u32.IsIconic(hwnd):
                return TestOutcome(passed=False, env_blocked=True, evidence=f"{app}: window did not stay minimized")
            fg0 = int(_u32.GetForegroundWindow() or 0)
            pl0 = bw._placement(hwnd)
            orig_rect = (pl0.rcNormalPosition.left, pl0.rcNormalPosition.top,
                         pl0.rcNormalPosition.right, pl0.rcNormalPosition.bottom)

            # the OLD wall, recorded honestly: the plain PrintWindow path refuses a minimized window
            naive_img, naive_why = hin.capture_window(hwnd)
            naive_wall = naive_img is None

            # the DAP bitmap consumer (capture_window_bitmap_bytes) used to hand back an all-zero blank here
            dw, dh, draw = o24.WIN32.capture_window_bitmap_bytes(hwnd)
            dap_pixels = dw > 50 and dh > 50 and any(draw[::256])

            # the ladder: succeeds where the naive path could not, and says WHICH rung made the pixels
            img, note, rung = hin.capture_window_robust(hwnd)
            good = img is not None and not hin._is_blank_render(img)
            if good:
                rungs.append(f"{app}:{rung}")
            time.sleep(0.35)                                     # let any restore/re-hide settle
            still_min = bool(_u32.IsIconic(hwnd))
            pl1 = bw._placement(hwnd)
            pos_ok = (pl1.rcNormalPosition.left, pl1.rcNormalPosition.top,
                      pl1.rcNormalPosition.right, pl1.rcNormalPosition.bottom) == orig_rect
            fg1 = int(_u32.GetForegroundWindow() or 0)
            focus_ok = fg1 != int(hwnd)                           # we never END owning the user's focus
            checks[f"{app}: real pixels captured although minimized"] = good and dap_pixels
            checks[f"{app}: left EXACTLY as found (still minimized, placement restored, focus not kept)"] = \
                still_min and pos_ok and focus_ok
            rows.append(f"{app}: naive={naive_why if naive_wall else 'captured'} ladder={rung} "
                        f"size={getattr(img, 'size', None)} dap={dw}x{dh} "
                        f"min_after={still_min} pos_restored={pos_ok} fg={fg0}->{fg1} | {str(note)[:90]}")

    checks["the wall was real: a minimized window needs a fallback rung (not plain PrintWindow)"] = \
        bool(rungs) and all(r != "printwindow-renderfull" for r in rungs)
    passed = all(checks.values())
    ev = "; ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()) + " | " + " || ".join(rows)
    return TestOutcome(passed=passed, evidence=ev[:2000],
                       metrics={"rungs_used": rungs, "checks": f"{sum(checks.values())}/{len(checks)}"})


def run_pro1(TestOutcome):
    """PRO1 (#5): the per-control capability probe reads the SURFACE structurally (framework classes, HMENU,
    native-tree reach - never an app-name table), informs the existing effector ladder (native tree first,
    pixel geometry last), demonstrates escalation on a live XAML app that rejects posted mouse, and returns an
    honest WALL with the full tiers_used trail when nothing actuates - never a faked pass."""
    from core_organs import capability_probe as cp
    from core_organs import fast_uia
    bm = _bm()
    db = _tmpdb()
    m = bm.BehaviorModel(db)
    try:
        with LiveApp("calc", park=True) as la:            # a real XAML-island app, fresh window, ours only
            if not la.ok:
                return TestOutcome(passed=False, env_blocked=True, evidence=f"calc: {la.why}")
            hwnd = la.hwnd
            prof = cp.probe(hwnd)
            checks: Dict[str, bool] = {}

            # (a) STRUCTURAL classification: the probe saw the framework's own window classes
            structural = (prof["surface"] not in ("unknown", "probe-error")) \
                and bool(prof["evidence_classes"] or prof["flags"]["classic_menu"])
            checks["probe classified the surface from STRUCTURE only (framework child classes, no app-name table)"] = \
                structural
            # (b) the app really is one of these walls (posted mouse does not reach XAML islands)
            checks["the live app IS a posted-input-rejecting surface (probe: surface flags xaml island)"] = \
                bool(prof["flags"]["xaml_island"]) and prof["posted_mouse_expectation"] == "unlikely"

            # (c) the informed ladder: native tiers ahead of pixel geometry, rationale kept
            order, rationale = cp.order_routes(list(bm.EffectorLadder.DEFAULTS["invoke"]), prof, "invoke")
            geo_after_native = all(order.index(g) > order.index("snapshot_invoke")
                                   for g in cp.GEOMETRY_TIERS if g in order)
            ladder = bm.EffectorLadder(m)
            key = bm._app_key("calc")
            ok_a, eff_a, note_a = ladder.perform(key, hwnd, {"verb": "invoke", "label": "7"})
            wired = getattr(ladder, "last_probe", None) or {}
            checks["probe informs the EXISTING ladder (native tree first, pixels last; rationale recorded)"] = \
                bool(rationale) and geo_after_native and bool(wired.get("profile"))

            # (d) escalation demonstrated WITH an independent effect postcondition: the display reads back 7
            snap = fast_uia.snapshot(hwnd, timeout_ms=4000) or []
            disp = [str(n.name or "") for n in snap if n.name]
            effect = any(d.strip() == "7" or d.startswith("Display is 7") or " 7" in d for d in disp)
            checks["actuation escalated to a tier that WORKS on the wall app, and the effect is PROVEN "
                   "independently (display reads 7)"] = bool(ok_a) and effect

            # (e) no false PASS: an unreachable control returns the WALL, success=False, full tiers trail
            ok_b, eff_b, note_b = ladder.perform(key, hwnd, {"verb": "invoke", "label": "Zeta-Photon-9000"})
            wall = (not ok_b) and str(note_b).startswith("WALL") and "tiers_used=[" in str(note_b) and \
                "not faked" in str(note_b)
            checks["an un-actuable control returns an honest WALL (tiers_used trail, NO success claim)"] = wall

            extra = (f"surface={prof['surface']} evidence={prof['evidence_classes'][:3]} "
                     f"native_tree={prof['native_tree']} tiers={order} delivered_via={eff_a} "
                     f"note={str(note_a)[:70]} | wall_note={str(note_b)[:120]}")
            passed = all(checks.values())
            ev = "; ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()) + " | " + extra
            return TestOutcome(passed=passed, evidence=ev[:2000],
                               metrics={"surface": prof["surface"], "tiers_used": order,
                                        "delivered_via": eff_a, "checks": f"{sum(checks.values())}/{len(checks)}"})
    finally:
        m.close()
        _rm_db(db)


# --------------------------------------------------------------------------- RST1: restore-state law

def _open_file_menu(hwnd: int) -> Dict[str, Any]:
    """Open the app's own File/menu entry through UIA patterns only (headless: expand, else invoke).
    Returns what WE created, so the law is judged on a side effect the test genuinely caused."""
    from core_organs import fast_uia
    rows = fast_uia.snapshot(hwnd, timeout_ms=6000) or []
    for n in rows:
        if (n.name or "").strip().lower() in ("file", "menu", "main menu"):
            if "expand" in (n.pats or []):
                try:
                    n.ctrl.GetExpandCollapsePattern().Expand()
                    time.sleep(0.7)
                    return {"attempted": True, "via": "expand", "label": n.name}
                except Exception:
                    pass
            if "invoke" in (n.pats or []):
                try:
                    n.ctrl.GetInvokePattern().Invoke()
                    time.sleep(0.7)
                    return {"attempted": True, "via": "invoke", "label": n.name}
                except Exception:
                    pass
    return {"attempted": False, "via": None, "label": None}


def run_rst1(TestOutcome):
    """RST1 (#6): the RESTORE-APP-UI-TO-ORIGINAL-STATE law - after an edit+save the app is returned to the
    interface the user left, not reset and not left mid-flight. Proves all four faces: OUR dialogs get closed,
    PRE-EXISTING dialogs are refused (left untouched), a mid-run ABORT is held to the same bar, and a window
    that was never observed gets an honest 'not-observed', never a guessed restore. Real app: fresh minimized
    Notepad edits + saves a file (the change survives) and the File menu WE opened is put back."""
    from core_organs import state_keeper as sk
    from core_organs import si_test_support as sup
    bm = _bm()
    t0 = time.time()
    rows, checks = [], {}
    saved_ok = content_after = False
    sk.reset()                                   # deterministic registry, whatever ran before
    fx_a = fx_c = None
    our_idx = base_c = -1
    db = _tmpdb()
    m = None
    path = ""
    try:
        # ---- Phase A: ownership discrimination on a real (fixture) window: ours close, the user's refuse
        fx_a = sup.FrameWithPopups().start()
        base_idx = fx_a.open_popup()              # the user's dialog: existed BEFORE first sight
        time.sleep(0.25)
        pre_a = sk.observe(fx_a.hwnd)
        ours = [fx_a.open_popup(), fx_a.open_popup()]   # dialogs WE opened after first sight
        time.sleep(0.3)
        rep_a = sk.restore(fx_a.hwnd)
        checks["A: closed BOTH dialogs we opened after the snapshot"] = all(not fx_a.alive(i) for i in ours)
        checks["A: LEFT the pre-existing dialog untouched (refused, never closed)"] = fx_a.alive(base_idx)
        checks["A: report says the frame matches its pre-state"] = \
            rep_a.get("status") == "restored" and rep_a.get("matches_pre_state") is True
        rows.append(f"A(fixtures): base={base_idx} survived, ours={ours} closed, status={rep_a.get('status')}, "
                    f"refused={len(rep_a.get('refused') or [])}, base_popups={len(pre_a.get('popups') or [])}")
        fx_a.stop()

        # ---- Phase B: real app edit+save; saved content SURVIVES, our UI side effects get unwound
        # (Win11 Notepad sometimes consolidates/destroys a second, test-owned window mid-run: the APP ended
        # our session's window - the law says 'window-gone' honestly instead of faking it. Retried once, then
        # reported ENV-BLOCKED, never PASS, never silently swallowed.)
        m = bm.BehaviorModel(db)
        m.load_pack_dir()
        rep_b = {"status": "no-attempt"}
        for b_try in (1, 2):
            with LiveApp("notepad", park=False) as la:
                if not la.ok:
                    return TestOutcome(passed=False, env_blocked=True, evidence=f"notepad: {la.why}")
                hwnd = la.hwnd
                pre_b = sk.observe(hwnd)              # the law records the user's state at first sight
                path = os.path.join(tempfile.gettempdir(), "hj_rst1_" + uuid.uuid4().hex[:6] + ".txt")
                text = "rst1-" + uuid.uuid4().hex[:5]
                tpl = bm.TemplateRunner(m).run("notepad", "write text and save as file",
                                              {"text": text, "path": path},
                                              hwnd_fn=lambda h=hwnd: h if _u32.IsWindow(h) else 0)
                saved_ok = bool(tpl.get("completed")) and os.path.exists(path) and \
                    text in open(path, encoding="utf-8", errors="replace").read()
                opened = _open_file_menu(hwnd)        # a side effect WE caused on the real app
                mid = sk.snapshot(hwnd)
                mid_new = sk.diff(pre_b, mid)["new_popups"]
                rep_b = sk.restore(hwnd)              # the law: unwind ours, keep the user's, save survives
                if rep_b.get("status") == "window-gone":
                    rows.append(f"B(attempt {b_try}): window-gone - {str(rep_b.get('note'))[:80]}")
                    continue
                post_b = sk.snapshot(hwnd)
                d_after = sk.diff(pre_b, post_b)
                content_after = os.path.exists(path) and \
                    text in open(path, encoding="utf-8", errors="replace").read()
                still_min = bool(_u32.IsIconic(hwnd))
                pos_ok = post_b.get("placement") == pre_b.get("placement")
                checks["B: the edit+save happened (intended change real, on disk)"] = saved_ok
                checks["B: saved content SURVIVED the unwind (law never reverts user data)"] = content_after
                checks["B: the File menu WE opened is gone (no new popups/expanded nodes remain)"] = \
                    bool(opened["attempted"]) and not d_after["new_popups"] and not d_after["expanded_new"]
                checks["B: post-run UI matches the user's pre-run state (report: restored + matches_pre)"] = \
                    rep_b.get("status") == "restored" and rep_b.get("matches_pre_state") is True
                checks["B: window left exactly where the user had it (still minimized, placement intact)"] = \
                    bool(pre_b.get("iconic")) and still_min and pos_ok
                rows.append(f"B(notepad,try{b_try}): tpl={tpl.get('completed')} our_menu={opened['via']}:{opened['label']} "
                            f"menu_popups_at_mid={len(mid_new)} closed_to_baseline="
                            f"{rep_b.get('restored', {}).get('popups_closed_to_baseline')} "
                            f"menus_collapsed={rep_b.get('restored', {}).get('menus_collapsed')} "
                            f"tab={rep_b.get('restored', {}).get('active_tab') or rep_b.get('restored', {}).get('active_tab_renamed_by_saved_change')} "
                            f"status={rep_b.get('status')} matches={rep_b.get('matches_pre_state')} "
                            f"residual={dict(rep_b.get('residual') or {})} "
                            f"focus_final={dict(rep_b.get('focus_final') or {})} "
                            f"min={still_min} pos={pos_ok} degraded={str(rep_b.get('degraded'))[:200]}")
                break
        if rep_b.get("status") == "window-gone":
            return TestOutcome(passed=False, env_blocked=True,
                               evidence="B: notepad destroyed our test window twice mid-run (app consolidation, "
                                        "not the law): " + " | ".join(rows),
                               metrics={"phases": "A(env-early-exit)", "seconds": round(time.time() - t0, 1)})

        # ---- Phase C: the ABORT path is held to the same bar (with preserve(): body raises mid-run)
        fx_c = sup.FrameWithPopups(title="HJ-StateLaw-Abort").start()
        base_c = fx_c.open_popup()                 # pre-existing at first sight (inside preserve)
        keeper_box = []
        raised = False
        try:
            with sk.preserve(fx_c.hwnd) as keeper:
                keeper_box.append(keeper)
                our_idx = fx_c.open_popup()        # what WE opened before dying mid-run
                time.sleep(0.3)
                raise RuntimeError("injected mid-run failure")
        except RuntimeError:
            raised = True
        krep = keeper_box[0]["report"] if keeper_box else {}
        checks["C: the body's exception propagated (law never swallows failures)"] = raised
        checks["C: on ABORT our popup was still closed and the user's left alive"] = \
            (not fx_c.alive(our_idx)) and fx_c.alive(base_c)
        checks["C: abort report flagged itself aborted AND still reached restored/matches"] = \
            bool(krep.get("aborted")) and krep.get("status") == "restored" and \
            krep.get("matches_pre_state") is True
        rows.append(f"C(abort): propagated={raised} ours_closed={not fx_c.alive(our_idx)} "
                    f"base_alive={fx_c.alive(base_c)} report={krep.get('status')}/aborted={krep.get('aborted')}")

        # ---- Phase D: never-observed window gets an honest refusal, never a guessed restore
        rep_d = sk.restore(fx_c.hwnd)               # session was dropped by C's restore -> unobserved
        checks["D: an unobserved window gets honest 'not-observed' (no state guessed)"] = \
            rep_d.get("status") == "not-observed"
        rows.append(f"D(no-snapshot): status={rep_d.get('status')} note={str(rep_d.get('note'))[:60]}")
        fx_c.stop()

        passed = all(checks.values())
        ev = "; ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()) + " | " + " || ".join(rows)
        return TestOutcome(passed=passed, evidence=ev[:2400],
                           metrics={"phases": "A/B/C/D",
                                    "checks": f"{sum(1 for v in checks.values() if v)}/{len(checks)}",
                                    "notepad_saved": saved_ok,
                                    "seconds": round(time.time() - t0, 1)})
    finally:
        try:
            sk.close_sessions()                     # any session left behind by a mid-test raise gets the law too
        except Exception:
            pass
        sk.reset()
        for fx in (fx_a, fx_c):
            try:
                if fx:
                    fx.stop()
            except Exception:
                pass
        if m is not None:
            try:
                m.close()
            except Exception:
                pass
        _rm_db(db)
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
