"""
si_tests_apprun -- offline tests of the app-run architecture (PR49+): state protection, toolkit classification, guide policies, flyout reading, the DevTools route against a FAKE browser that
speaks the real protocol, the guide ledger, the run report. No desktop window, no network, no model; registered into the Professor suite (si_tests_professor.OFFLINE).
"""

from __future__ import annotations

import http
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path[:0] = [p for p in ("D:/new_automation", "D:/new_automation/All codes") if p not in sys.path]
import logging
logging.getLogger("websockets").setLevel(logging.CRITICAL)


@dataclass
class TestOutcome:
    passed: bool
    evidence: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    env_blocked: bool = False


def _verdict(checks: Dict[str, bool], extra: str = "", metrics: Optional[Dict[str, Any]] = None) -> TestOutcome:
    ok = all(checks.values())
    ev = "; ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()) + (f" | {extra}" if extra else "")
    m = {"checks": f"{sum(1 for v in checks.values() if v)}/{len(checks)}"}
    m.update(metrics or {})
    return TestOutcome(ok, ev, m)


def _tmp(name: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"aprun_{name}_{uuid.uuid4().hex[:8]}")


class N:
    """A stand-in for a fast_uia node."""
    def __init__(self, ctype="ButtonControl", name="", rect=(0, 0, 50, 20), pats=("invoke",), depth=1, parent=-1, idx=0, expand_state=-1, enabled=True, accel="", aid="", offscreen=False):
        self.ctype, self.name, self.rect, self.pats, self.depth, self.parent, self.idx = ctype, name, rect, list(pats), depth, parent, idx
        self.expand_state, self.enabled, self.accel, self.aid, self.offscreen = expand_state, enabled, accel, aid, offscreen
        self.selected, self.toggle_state, self.help, self.cls = None, -1, "", ""
        self._ctrl = None

    @property
    def role(self) -> str:
        return self.ctype.replace("Control", "").lower()


# ====================================================================================================================== PR49 state protection
def run_pr49() -> TestOutcome:
    """PR49: state protection works from the system's launch id alone - a packaged app's data folder is copied aside, restored-session files are removed so the instance starts fresh, everything is put back
    byte for byte afterwards, a run that died halfway is repaired by the next one (journal), throw-away directories vanish"""
    from core_organs.professor import state_protect as SPT
    root = _tmp("localapp")
    fam = "Demo.Editor_abcdefghijklm"
    ls = os.path.join(root, "Packages", fam, "LocalState")
    os.makedirs(os.path.join(ls, "TabState"))
    os.makedirs(os.path.join(ls, "Settings"))
    files = {"TabState/a.bin": b"user tab one", "TabState/b.bin": b"user tab two", "Settings/prefs.json": b'{"theme":"dark"}', "WindowState.bin": b"window geometry"}
    for rel, data in files.items():
        with open(os.path.join(ls, rel), "wb") as fh:
            fh.write(data)
    old_env, old_j = os.environ.get("LOCALAPPDATA"), SPT.JOURNAL
    os.environ["LOCALAPPDATA"] = root
    SPT.JOURNAL = _tmp("journal") + ".json"
    try:
        fam_ok = SPT.package_family_of(f"{fam}!App") == fam and SPT.package_family_of(r"C:\Program Files\x\y.exe") == "" and SPT.package_family_of("Chrome") == ""
        g = SPT.StateGuard("demo", f"{fam}!App")
        rep = g.before()
        left = sorted(os.listdir(os.path.join(ls, "TabState")))
        fresh = not os.path.exists(os.path.join(ls, "WindowState.bin")) and left == [] and os.path.exists(os.path.join(ls, "Settings", "prefs.json"))
        with open(os.path.join(ls, "Settings", "prefs.json"), "wb") as fh:                     # the app changes a setting and writes new session files during the run
            fh.write(b'{"theme":"light"}')
        with open(os.path.join(ls, "TabState", "new.bin"), "wb") as fh:
            fh.write(b"test tab")
        g.after()
        back = all(open(os.path.join(ls, rel), "rb").read() == data for rel, data in files.items()) and not os.path.exists(os.path.join(ls, "TabState", "new.bin"))
        # a run that dies halfway: before() without after(), then the next run's recover()
        g2 = SPT.StateGuard("demo", f"{fam}!App")
        g2.before()
        with open(os.path.join(ls, "Settings", "prefs.json"), "wb") as fh:
            fh.write(b"corrupted by a crashed run")
        n = SPT.recover()
        repaired = n >= 1 and open(os.path.join(ls, "Settings", "prefs.json"), "rb").read() == b'{"theme":"dark"}' and not SPT._journal()
        # a throw-away directory
        g3 = SPT.StateGuard("x", "")
        d = g3.new_temp_dir()
        open(os.path.join(d, "f"), "w").write("x")
        g3.after()
        checks = {"family_from_launch_id": fam_ok, "packaged_detected": rep.get("packaged") is True and bool(rep.get("backed_up")), "session_files_removed_fresh_start": fresh, "restored_byte_for_byte": back,
                  "crashed_run_repaired_by_journal": repaired, "temp_dir_removed": not os.path.exists(d)}
        return _verdict(checks, f"cleared {rep.get('session_files_cleared')} session file(s)")
    finally:
        if old_env is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_env
        SPT.JOURNAL = old_j
        shutil.rmtree(root, ignore_errors=True)


# ====================================================================================================================== PR50 guide policies
def run_pr50() -> TestOutcome:
    """PR50: the guide's words become steps without app-specific rules - menu phrases are one path, 'the X' is a field, an unquoted literal is typed text, alternatives are tried in turn, context-only
    clauses are not steps, the control NEXT TO the previous step wins ('Select' then 'Rectangle'), and steps no headless run may take are named (files, accounts, OS chords, gestures)"""
    from core_organs.professor.knowledge import guide_steps as GS
    from core_organs.professor.harvest import Catalog, Verb

    def V(label, path=(), role="button", trust="measured", sources=("uia",)):
        return Verb(f"{'|'.join(path)}/{label}", label, list(path), "", "", True, False, "", 0, "", role, list(sources), trust, "safe")
    st = GS.parse_steps("3. On the **File**menu, select**Save As**, type a descriptive name for your file in the **File name**box, and then select **OK**.")
    paths = [s.path for s in st]
    p2 = GS.parse_steps("- Select **Page Setup**from the**File**menu and enter the desired command(s) in the**Header**and**Footer**text boxes.")
    lit = GS.parse_steps("1. Type .LOG on the first line, and then press ENTER to move to the next line.")
    fld = GS.parse_steps("3. Enter the desired **Width**and**Height**.")
    ctx = GS.parse_steps("1. At the bottom right of a New Tab page, click Customize Chrome .")
    alt = GS.parse_steps("4. Choose **Pixels**, **Inches**, or **Centimeters**.")
    cat = Catalog(app_key="demo", verbs=[V("Inches", role="radio"), V("Select", ["Selection"], "radio"), V("Rectangle", ["Shapes"], "list_item"), V("Rectangle", ["Selection", "Select"], "menu_item"),
                                          V("Rectangle", [], "button", "inferred", ("vision",)), V("Setting", [], "button"), V("Customize Chrome", [], "button")])
    g_alt = GS.ground_step(alt[0], cat)
    g_seq = GS.ground(GS.parse_steps("1. Click **Select**.\n2. Choose **Rectangle**."), cat)
    human = [GS.ground_step(s, cat).how for t in ("3. Choose an image from your PC.", "2. Press Windows + Shift + S.", "1. Click and drag on the canvas to draw.") for s in GS.parse_steps(t)]
    plain = GS.ground_step(GS.parse_steps("2. Select **Image properties**.")[0], cat).how
    stem = GS.resolve_label(cat, "Settings")
    keys = GS.ground_step(GS.parse_steps("2. Press ENTER.")[0], cat).how
    checks = {"menu_phrase_is_one_path": ["File", "Save As"] in paths and ["File", "Page Setup"] in [s.path for s in p2],
              "typed_text_not_the_field": all(s.text == "" for s in st if s.target == "File name") and any(s.target == "File name" for s in st),
              "two_fields_two_steps": [s.target for s in p2 if s.action == "type"] == ["Header", "Footer"],
              "unquoted_literal_is_typed": any(s.text == ".LOG" for s in lit), "the_X_is_a_field_not_text": [s.target for s in fld] == ["Width", "Height"] and all(not s.text for s in fld),
              "context_clause_is_not_a_step": [s.target for s in ctx] == ["Customize Chrome"], "alternatives_tried_in_turn": g_alt.how == "label" and g_alt.verb is not None and g_alt.verb.label == "Inches",
              "control_next_to_previous_step_wins": g_seq[1].verb is not None and g_seq[1].verb.path == ["Selection", "Select"], "files_accounts_os_chords_gestures_named": human == ["human", "outside", "gesture"],
              "menu_name_is_not_a_file_policy_hit": plain != "human", "plural_is_the_same_word": stem[0] is not None and stem[0].label == "Setting" and stem[1] >= 0.66, "editing_key_is_a_key": keys == "key"}
    return _verdict(checks)


# ====================================================================================================================== PR51 toolkit classification of a launch target
def run_pr51() -> TestOutcome:
    """PR51: a program is classified from what is on disk, not from its name in a list of apps - a Chromium browser by its image, an Electron shell by its resources / runtime files, anything else not at all"""
    from core_organs.professor import launcher as LN
    root = _tmp("exes")
    try:
        def mk(path, files=()):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(b"MZ")
            for f in files:
                p = os.path.join(os.path.dirname(path), f)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "wb").write(b"x")
        mk(os.path.join(root, "a", "chrome.exe"))
        mk(os.path.join(root, "b", "msedge.exe"))
        mk(os.path.join(root, "c", "Editor.exe"), ["resources/app.asar", "chrome_100_percent.pak"])
        mk(os.path.join(root, "d", "Client.exe"), ["libcef.dll"])
        mk(os.path.join(root, "e", "Notes.exe"), ["help.chm"])
        mk(os.path.join(root, "f", "Ide.exe"), ["2a59476c9b/resources/app/package.json"])
        mk(os.path.join(root, "g", "Modeller.exe"), ["5.2/scripts/x.py", "Some Editor/resources/app/package.json"])   # a general folder: other apps' folders beside it
        k = {n: LN.chromium_kind(os.path.join(root, d, n)) for d, n in (("a", "chrome.exe"), ("b", "msedge.exe"), ("c", "Editor.exe"), ("d", "Client.exe"), ("e", "Notes.exe"), ("f", "Ide.exe"), ("g", "Modeller.exe"))}
        args = LN._chromium_args(LN.Target("x", exe="X.exe", chromium="browser"), "C:/tmp/prof", 9333)
        eargs = LN._chromium_args(LN.Target("x", exe="X.exe", chromium="electron"), "C:/tmp/prof", 9333)
        checks = {"browser_by_image": k["chrome.exe"] == "browser" and k["msedge.exe"] == "browser", "electron_by_resources": k["Editor.exe"] == "electron" and k["Client.exe"] == "electron",
                  "electron_resources_one_versioned_folder_down": k["Ide.exe"] == "electron",
                  "plain_program_is_nothing": k["Notes.exe"] == "", "neighbour_apps_folders_are_not_its_resources": k["Modeller.exe"] == "", "missing_file_is_nothing": LN.chromium_kind(os.path.join(root, "zzz.exe")) == "",
                  "throwaway_profile_and_debug_port": "--user-data-dir=C:/tmp/prof" in args and "--remote-debugging-port=9333" in args and "--remote-allow-origins=*" in args,
                  "browser_only_flags_stay_off_electron": "--no-first-run" in args and "--no-first-run" not in eargs}
        return _verdict(checks, str(k))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ====================================================================================================================== PR52 flyouts (the deep tree)
def run_pr52() -> TestOutcome:
    """PR52: the menus a tree cannot show are read - every opener (also two with the SAME name in different groups, radio buttons that expand, ribbon tabs but not document tabs) is opened through
    ExpandCollapse, its items join the catalog under the group and opener they live in, the flyout is collapsed again, a callback sees it open and each opener is a history row"""
    from core_organs.professor import menus as MN, probe as PB, history as HS
    from core_organs.professor.harvest import Catalog
    base = [N("GroupControl", "Selection", (0, 0, 120, 100), (), 1, idx=0), N("RadioButtonControl", "Select", (5, 5, 50, 50), ("select", "expand"), 2, 0, 1, 0), N("ButtonControl", "More Options", (5, 60, 50, 90), ("invoke", "expand"), 2, 0, 2, 0),
            N("GroupControl", "Brushes", (130, 0, 250, 100), (), 1, idx=3), N("ButtonControl", "More Options", (135, 60, 180, 90), ("invoke", "expand"), 2, 3, 4, 0),
            N("MenuItemControl", "File", (400, 400, 430, 410), ("invoke", "expand"), 1, idx=5, expand_state=0), N("TabItemControl", "Untitled. Unmodified.", (0, 0, 10, 10), ("select",), 1, idx=6),
            N("ButtonControl", "Close", (0, 0, 10, 10), ("invoke",), 1, idx=7)]
    state = {"open": None}
    flyouts = {"Select": [("Rectangle", ""), ("Free-form", ""), ("Select all", "Ctrl+A")], "File": [("New tab", "Ctrl+N"), ("Page setup\u2026", "")], "More Options@135": [("Airbrush", ""), ("Crayon", "")], "More Options@5": [("Opacity", "")]}

    def key_of(n):
        return n.name + ("@" + str(n.rect[0]) if n.name == "More Options" else "")

    def all_nodes():
        out = list(base)
        if state["open"]:
            for i, (nm, acc) in enumerate(flyouts[state["open"]]):
                out.append(N("MenuItemControl", nm, (6, 6 + 40 * i, 283, 40 + 40 * i), ("invoke",), 1, idx=100 + i, accel=acc))
        return out

    class FX:
        allowed = True
        def key(self, k): return True, "ok"
        def close_popups(self, before): return 0
        def why_not(self): return ""
    orig_expand, orig_collapse, orig_snap, orig_delta = MN._expand, MN.collapse, PB.snapshot, PB.delta
    collapsed, seen_cb = [], []

    def fake_expand(fx, n, deadline_s=2.0):
        k = key_of(n)
        for kk in flyouts:
            if kk == k:
                state["open"] = kk
        return True, "UIA Expand"

    def fake_collapse(n, deadline_s=1.5):
        collapsed.append(n.name)
        state["open"] = None
        return True

    class S:
        def __init__(self, k): self.names, self.texts, self.states, self.containers, self.windows, self.image, self.sig = {k: k}, {}, {}, {}, (1,), None, str(k)
    MN._expand, MN.collapse = fake_expand, fake_collapse
    PB.snapshot = lambda hwnd, **kw: S(state["open"] or "closed")
    h = HS.History(_tmp("hist") + ".db")
    try:
        cat = Catalog(app_key="demo")
        rep = MN.expand_menus(FX(), 1, cat, all_nodes, budget_s=30, history=h, toolkit="winui", on_items=lambda op, new: seen_cb.append((op.name, len(new))))
        paths = {(tuple(v.path), v.label): v for v in cat.verbs}
        op_names = [(n.name) for n in MN.find_openers(base)]
        # a ribbon is recognised by STRUCTURE (tabs over named groups of controls), never by tab names: non-English tab names must work; document tabs (each with a Close button) never count
        rib = [N("TabControl", "Ribbon Tabs", (0, 0, 600, 30), (), 1, idx=0)] + [N("TabItemControl", nm, (i * 80, 0, i * 80 + 70, 28), ("select",), 2, 0, idx=1 + i) for i, nm in enumerate(["Start", "Einfuegen", "Entwurf"])]
        rib += [N("GroupControl", "Zwischenablage", (0, 32, 200, 120), (), 2, idx=4), N("ButtonControl", "Kopieren", (5, 40, 60, 70), ("invoke",), 3, 4, idx=5), N("ButtonControl", "Ausschneiden", (70, 40, 120, 70), ("invoke",), 3, 4, idx=6),
                N("GroupControl", "Schriftart", (210, 32, 400, 120), (), 2, idx=7), N("ButtonControl", "Fett", (215, 40, 250, 70), ("invoke",), 3, 7, idx=8), N("ButtonControl", "Kursiv", (260, 40, 300, 70), ("invoke",), 3, 7, idx=9)]
        docs = [N("TabControl", "Tabs", (0, 0, 600, 30), (), 1, idx=0)]
        for i, nm in enumerate(["report.docx", "Home", "notes"]):
            docs += [N("TabItemControl", nm, (i * 90, 0, i * 90 + 80, 28), ("select",), 2, 0, idx=len(docs)), N("ButtonControl", "Close", (i * 90 + 60, 4, i * 90 + 76, 20), ("invoke",), 3, len(docs), idx=len(docs) + 1)]
        tabs = [t for t in MN.find_openers(rib) if t.role == "tabitem"] + [t for t in MN.find_openers(docs) if t.role == "tabitem"]
        label, chord = MN._item_label(N("MenuItemControl", "Open\tCtrl+O"))
        checks = {"same_name_two_groups_two_openers": op_names.count("More Options") == 2, "document_tab_and_close_not_openers": "Untitled. Unmodified." not in op_names and "Close" not in op_names,
                  "ribbon_tabs_yes_document_tabs_no": [t.name for t in tabs] == ["Start", "Einfuegen", "Entwurf"], "radio_button_that_expands_is_read": ("Selection", "Select") == tuple(paths[(("Selection", "Select"), "Rectangle")].path),
                  "items_filed_under_group_and_opener": (("Brushes", "More Options"), "Crayon") in paths and (("Selection", "More Options"), "Opacity") in paths and (("File",), "New tab") in paths,
                  "accelerator_kept": paths[(("File",), "New tab")].shortcut == "Ctrl+N" and paths[(("Selection", "Select"), "Select all")].shortcut == "Ctrl+A",
                  "dialog_items_marked": paths[(("File",), "Page setup")].leads_to == "opens a dialog", "every_flyout_collapsed_again": len(collapsed) >= 4 and state["open"] is None,
                  "callback_saw_each_open_flyout": len(seen_cb) >= 4 and all(c > 0 for _n, c in seen_cb), "item_label_splits_accelerator": label == "Open" and chord == "Ctrl+O",
                  "each_opener_is_a_history_row": h.stats("demo").get("transitions", 0) >= 4 and rep["opened"] == rep["openers"]}
        return _verdict(checks, f"{rep['openers']} openers, {rep['opened']} opened, {rep['items']} items; history {h.stats('demo')}; failed {rep['failed']}")
    finally:
        MN._expand, MN.collapse, PB.snapshot, PB.delta = orig_expand, orig_collapse, orig_snap, orig_delta
        h.close()


# ====================================================================================================================== PR53 the DevTools route against a fake browser
class FakeBrowser:
    """A browser that speaks the real DevTools protocol over HTTP + WebSocket on 127.0.0.1: tabs, an accessibility tree per page, navigation by link, a page that kills it."""

    PAGES = {
        "chrome://chrome-urls/": ("Chrome URLs", [("link", f"chrome://{x}") for x in ("settings", "history", "crash", "internals", "bookmarks", "bomb", "sync-optin")], []),
        "chrome://settings/": ("Settings", [("menuitem", "Appearance"), ("menuitem", "On startup"), ("button", "Reset settings"), ("textbox", "Search settings")], ["chrome://settings/appearance"]),
        "chrome://settings/appearance": ("Settings - Appearance", [("checkbox", "Show home button"), ("combobox", "Theme")], []),
        "chrome://history/": ("History", [("button", "Clear browsing data"), ("textbox", "Search history")], []),
        "chrome://bookmarks/": ("Bookmarks", [("button", "Add new bookmark")], []),
        "chrome://bomb/": ("Bomb", [("button", "Boom")], []),
    }

    def __init__(self):
        from websockets.sync.server import serve
        self.tabs: List[Dict[str, str]] = [{"id": "T0", "type": "page", "url": "about:blank", "title": "about:blank"}]
        self.visits: List[str] = []
        self.dead = False
        self.nav: Dict[str, List[str]] = {}
        self.clicks: List[str] = []
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.server = serve(self._handler, "127.0.0.1", self.port, process_request=self._http, ping_interval=None)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def kill(self) -> None:
        self.dead = True
        try:
            self.server.shutdown()
        except Exception:
            pass

    def _http(self, conn, request):
        if request.path.startswith("/json/version"):
            return conn.respond(http.HTTPStatus.OK, json.dumps({"Browser": "Chrome/154.0.0.0", "webSocketDebuggerUrl": f"ws://127.0.0.1:{self.port}/devtools/browser/B"}))
        if request.path.startswith("/json/list"):
            return conn.respond(http.HTTPStatus.OK, json.dumps([{**t, "webSocketDebuggerUrl": f"ws://127.0.0.1:{self.port}/devtools/page/{t['id']}"} for t in self.tabs]))
        return None

    def _open(self, url: str) -> str:
        if "bomb" in url:
            self.visits.append(url)
            self.kill()
            return ""
        tid = f"T{len(self.visits) + len(self.tabs) + 1}"
        title = self.PAGES.get(url, (url, [], []))[0]
        self.tabs.insert(0, {"id": tid, "type": "page", "url": url, "title": title})
        self.visits.append(url)
        return tid

    def _handler(self, ws):
        path = ws.request.path
        tid = path.rsplit("/", 1)[-1]
        for raw in ws:
            msg = json.loads(raw)
            m, p, i = msg["method"], msg.get("params", {}), msg["id"]
            tab = next((t for t in self.tabs if t["id"] == tid), None)
            res: Dict[str, Any] = {}
            if m == "Target.createTarget":
                res = {"targetId": self._open(p.get("url", "about:blank"))}
            elif m == "Target.closeTarget":
                self.tabs = [t for t in self.tabs if t["id"] != p["targetId"]]
                res = {"success": True}
            elif m == "Target.activateTarget":
                res = {}
            elif m == "Accessibility.getFullAXTree" and tab is not None:
                page = self.PAGES.get(tab["url"], (tab["title"], [], []))
                nodes = []
                for k, (role, name) in enumerate(page[1]):
                    nodes.append({"nodeId": str(k), "ignored": False, "role": {"value": role}, "name": {"value": name}, "backendDOMNodeId": 1000 + k, "properties": []})
                res = {"nodes": nodes}
            elif m == "Runtime.evaluate" and tab is not None:
                e = p.get("expression", "")
                if "readyState" in e:
                    res = {"result": {"value": "complete"}}
                elif "document.title" in e:
                    res = {"result": {"value": [tab["title"], tab["url"]]}}
                elif "a[href]" in e:
                    res = {"result": {"value": self.PAGES.get(tab["url"], ("", [], []))[2]}}
                else:
                    res = {"result": {"value": None}}
            elif m == "Page.navigate" and tab is not None:
                tab["url"] = p["url"]
                tab["title"] = self.PAGES.get(p["url"], (p["url"], [], []))[0]
                self.visits.append(p["url"])
                res = {}
            elif m == "DOM.getBoxModel":
                res = {"model": {"content": [10, 10, 60, 10, 60, 30, 10, 30]}}
            elif m == "Input.dispatchMouseEvent":
                if p.get("type") == "mousePressed" and tab is not None:
                    self.clicks.append(tab["url"])
                    if tab["url"].endswith("settings/") and p["x"] > 0:
                        pass
                res = {}
            else:
                res = {}
            ws.send(json.dumps({"id": i, "result": res}))


def run_pr53() -> TestOutcome:
    """PR53: the DevTools route learns its commands and pages from the application and its guide - commands are named in the guide's words and filed under the menus it names, only pages the guide talks
    about are opened, dangerous classes are never opened, a page that kills the browser is learnt as a hazard (and never opened again), destinations come from page titles, protocol actions change the state the executor sees"""
    from core_organs.professor.adapters import cdp, chromium
    from core_organs.professor.harvest import Catalog
    cache = _tmp("cdpcache") + ".json"
    fb = FakeBrowser()
    br = None
    try:
        br = cdp.CdpBrowser(fb.port)
        alive = br.wait(5)
        shortcuts = {"Ctrl+T": [{"label": "Open a new tab", "cite": "x"}], "Ctrl+R": [{"label": "Reload this page", "cite": "y"}]}
        ad = chromium.ChromiumAdapter(br, guide_shortcuts=shortcuts, guide_terms=["Settings", "History", "Bookmarks", "Appearance", "Tab"], guide_menus={"More": {"Settings": {}, "History": {}}}, cache_path=cache)
        cat = Catalog(app_key="demo")
        rep = ad.harvest_all(cat, budget_s=40)
        labels = {(tuple(v.path), v.label): v for v in cat.verbs}
        opened_urls = [u for u in fb.visits]
        # a destination is a verb that navigates; a page control carries its page
        goto = [v for v in cat.verbs if v.aid.startswith("cdp-browser:goto:")]
        before = ad.state_texts()
        nt = labels.get((("Browser",), "Open a new tab"))
        ok_new, how_new = ad.act(nt) if nt else (False, "missing")
        after_new = ad.state_texts()
        st = next((v for v in goto if v.label == "Settings"), None)
        ok_go, _h = ad.act(st) if st else (False, "")
        cur = ad.current()
        title_url = cur.title_url() if cur else ("", "")
        # the browser dies on a page the guide's vocabulary makes relevant: the hazard is written down first, the next adapter never opens it
        fb2 = FakeBrowser()
        PAGES2 = dict(FakeBrowser.PAGES)
        br2 = cdp.CdpBrowser(fb2.port)
        br2.wait(5)
        ad2 = chromium.ChromiumAdapter(br2, guide_terms=["Settings", "Bomb"], cache_path=cache)
        gone = None
        try:
            ad2.harvest_all(Catalog(app_key="demo"), budget_s=30)
        except chromium.BrowserGone as bg:
            gone = bg.url
        fb3 = FakeBrowser()
        br3 = cdp.CdpBrowser(fb3.port)
        br3.wait(5)
        ad3 = chromium.ChromiumAdapter(br3, guide_terms=["Settings", "Bomb"], cache_path=cache)
        r3 = ad3.harvest_all(Catalog(app_key="demo"), budget_s=30)
        hazard_cached = "bomb" in json.dumps(json.load(open(cache, "r", encoding="utf-8")).get("hazards", []))
        checks = {"browser_answers": alive and ad.scheme == "chrome", "commands_in_the_guides_words": (("Browser",), "Open a new tab") in labels and labels[(("Browser",), "Open a new tab")].shortcut == "Ctrl+T",
                  "default_name_when_guide_is_silent": (("Browser",), "Close tab") in labels, "filed_under_the_menu_the_guide_names": (("More",), "Settings") in labels or (("More",), "History") in labels,
                  "only_pages_the_guide_talks_about": any("settings" in u for u in opened_urls) and any("history" in u for u in opened_urls) and not any(("crash" in u or "internals" in u or "sync-optin" in u) for u in opened_urls),
                  "page_controls_read": any(v.label == "Appearance" and "cdp-page" in v.sources for v in cat.verbs), "destinations_from_titles": any(v.label == "History" for v in goto) and any(v.label == "Appearance" for v in goto),
                  "link_followed_to_a_subpage": any("appearance" in u for u in opened_urls), "command_changes_the_tab_list": ok_new and before.get("cdp|tabs") != after_new.get("cdp|tabs"),
                  "destination_navigates": ok_go and "settings" in title_url[1], "browser_death_raises_with_the_url": gone is not None and "bomb" in gone, "hazard_written_down": hazard_cached,
                  "next_run_never_opens_it": "bomb" not in " ".join(fb3.visits) and r3.get("pages", 0) >= 1}
        return _verdict(checks, f"{rep.get('pages')} pages, {rep.get('page_verbs')} controls, {rep.get('commands')} commands; opened {len(opened_urls)}")
    finally:
        try:
            if br is not None:
                br.close()
        except Exception:
            pass
        for f in ("fb", "fb2", "fb3"):
            try:
                locals()[f].kill()
            except Exception:
                pass
        try:
            os.remove(cache)
        except OSError:
            pass


# ====================================================================================================================== PR54 the ledger
def run_pr54() -> TestOutcome:
    """PR54: every procedure of a guide is ACCOUNTED for - run, or set aside with the reason (launching the app, nothing in this interface, duplicate) or blocked by policy (needs an account) - and a
    scenario's interest orders the work; nothing in it names an application"""
    from core_organs.professor import apprun as AR, history as HS, skills as SK
    from core_organs.professor.harvest import Catalog, Verb
    from core_organs.professor.knowledge import manual_rag as MR

    class L:
        def attach(self, *a, **k): return {}
        def report(self): return {}

    ix = MR.ManualIndex(_tmp("ix") + ".db")
    ix.ingest_text("demo", "Demo guide", "# Demo Guide\n## Make text bold\n1. Click **Bold**.\n2. Click **Italic**.\n"
                   "## Open Demo from the Start menu\n1. Click the **Start** button.\n2. Type Demo.\n3. Press Enter.\n"
                   "## Rewrite text with AI\nSign in with your Microsoft account to use credits.\n1. Click **Rewrite**.\n"
                   "## Draw a line\n1. Click **Pencil**.\n2. Click and drag on the canvas.\n"
                   "## Zoom in\n1. Click **Zoom in**.\n## Bold text\n1. Click **Bold**.\n2. Click **Italic**.\n## Bold text\n1. Click **Bold**.\n2. Click **Colour wheel**.\n"
                   "## Print your work\n1. Click **Print**.\n## Tune the colours\n1. Click **Colour wheel**.\n", "test:demo", "md", embed=False)
    h, sk = HS.History(_tmp("h") + ".db"), SK.SkillLibrary(_tmp("s") + ".db")

    def V(l, role="button"):
        return Verb(l, l, [], "", "", True, False, "", 0, "", role, ["uia"], "measured", "safe")
    try:
        spec = AR.AppSpec(key="demo", name="demo app", tier=1, focus="colour|zoom")
        run = AR.AppRun(spec, history=h, skills=sk, index=ix, learner=L(), echo=False)
        run.cat = Catalog(app_key="demo", verbs=[V("Bold"), V("Italic"), V("Pencil"), V("Zoom in"), V("Print"), V("Colour wheel")])
        tasks = run.build_tasks()
        led = {r["goal"]: r for r in run.ledger}
        by = {}
        for r in run.ledger:
            by[r["disposition"]] = by.get(r["disposition"], 0) + 1
        checks = {"every_procedure_is_in_the_ledger": len(run.ledger) + len(tasks) >= 8, "launch_procedure_set_aside_with_reason": any("launching" in r["reason"] or "starting" in r["reason"] or "open" in r["reason"] for r in run.ledger if "Start menu" in r["goal"]),
                  "account_procedure_blocked_by_policy": led.get("Rewrite text with AI", {}).get("disposition") == "blocked" and "account" in led["Rewrite text with AI"]["reason"],
                  "duplicate_set_aside": any("duplicate" in r["reason"] for r in run.ledger), "scenario_focus_orders_the_work": bool(tasks) and re.search("colour|zoom", tasks[0]["goal"], re.I) is not None,
                  "rows_in_the_database": len(h.guide_runs("demo", 50)) >= 2, "gesture_procedure_still_listed_to_run_and_judged_there": any(t["goal"] == "Draw a line" for t in tasks)}
        return _verdict(checks, f"{by}")
    finally:
        h.close()
        ix.close()


# ====================================================================================================================== PR55 the run report
def run_pr55() -> TestOutcome:
    """PR55: a run is readable - the console log is one tidy line per fact, and the report is ONE self-contained HTML page (pictures embedded, every procedure with its outcome and reason, what was learnt)"""
    from core_organs.professor import runui
    from PIL import Image
    d = _tmp("run")
    os.makedirs(os.path.join(d, "evidence"))
    Image.new("RGB", (300, 200), (30, 30, 40)).save(os.path.join(d, "scan_1_first.png"))
    Image.new("RGB", (300, 200), (60, 30, 40)).save(os.path.join(d, "evidence", "01_fail.png"))
    rep = {"app": "demo", "tier": 1, "started": "now", "seconds": 12.3, "counts": {"ok": 1, "blocked": 1, "failed": 1}, "ledger_counts": {"skipped": 2},
           "phases": {"deep_scan": {"profile": {"family": "winui"}, "state": "rich", "nodes": 63, "depth": 7}, "vision_scan": {"elements": 30}, "catalog_after_menus": {"verbs": 88}},
           "ledger": [{"goal": "Make <b>bold</b>", "cite": "g", "source": "s", "steps": 2, "grounded": 1.0, "disposition": "ok", "reason": ""},
                      {"goal": "Save", "cite": "g", "source": "s", "steps": 3, "grounded": 0.5, "disposition": "blocked", "reason": "'Save as' is commit"},
                      {"goal": "Broken", "cite": "g", "source": "s", "steps": 1, "grounded": 1.0, "disposition": "failed", "reason": "no effect"}],
           "tasks": [{"goal": "Make bold", "cite": "g > h", "final": "ok", "attempts": [{"n": 1, "status": "ok", "why": "", "remedy": "", "results": [{"step": 1, "verb": "Bold", "status": "done", "route": "control:Bold", "effect": "state_change", "summary": "toggled", "vision_ok": True}]}]}],
           "ml": {"outcome": {"seen": 100, "ok_accuracy": 0.86, "ok_baseline": 0.73, "effect_accuracy": 0.76, "effect_baseline": 0.48}, "candidates": {"seen": 500, "prequential_auc": 0.99}}, "history": {"transitions": 12}}
    ui = runui.ConsoleUI("demo", 1, echo=False)
    ui.banner("demo", "x")
    ui.phase("scan", "30 controls")
    ui.task_start(1, 3, "Make bold", 2, 1.0)
    ui.attempt(1, "ok", 2, 2)
    ui.attempt(2, "failed", 0, 2, "no route produced a visible effect")
    ui.summary({"ok": 1, "blocked": 1, "failed": 1}, {"skipped": 2}, 12.3, "r.html")
    path = runui.write_html(rep, d)
    page = open(path, "r", encoding="utf-8").read()
    try:
        checks = {"console_has_glyphs_and_phases": any("✔" in l for l in ui.lines) and any("✖" in l for l in ui.lines) and any("scan" in l for l in ui.lines), "summary_counts_on_one_line": any("1 ok" in l and "1 blocked" in l and "1 failed" in l for l in ui.lines),
                  "html_is_one_file": path.endswith("report.html") and os.path.getsize(path) > 2000, "pictures_embedded": page.count("data:image/png;base64") >= 2, "every_procedure_listed": all(x in page for x in ("Make &lt;b&gt;bold", "Save", "Broken")),
                  "reasons_shown_and_escaped": "&#x27;Save as&#x27; is commit" in page or "'Save as' is commit" in page, "learning_numbers_shown": "0.86" in page and "0.99" in page, "toolkit_and_depth_shown": "winui" in page and "63" in page}
        return _verdict(checks, f"{len(page)} bytes")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ====================================================================================================================== PR56 the executor's generic rules
def run_pr56() -> TestOutcome:
    """PR56: the executor's generic rules - drop-downs are EXPANDED before they are invoked, a verb read out of a flyout is looked up in the flyout's own window, a button beats the label inside it, throw-away
    state makes settings-like verbs harmless while credentials stay human, a numeric field gets a number, a disabled control is a missing precondition, text with no editor falls through to the next route"""
    from core_organs.professor import executor as X, viz
    from core_organs.professor.effectors import Effector
    from core_organs.professor.harvest import Catalog, Verb

    def V(label, path=(), role="button", leads="", sources=("uia",), desc="", aid=""):
        return Verb(f"{'|'.join(path)}/{label}", label, list(path), "", desc, True, False, leads, 0, aid, role, list(sources), "measured", "safe")
    from core_organs.professor import safety
    cat = Catalog(app_key="demo", verbs=[V("Rotate", ["Image"], "button", "opens a menu"), V("Save", [], "button"), V("Profile", [], "button"), V("Sign in", [], "button"), V("Width", [], "field", desc="range 1..99999"), V("Name", [], "field"),
                                          V("Rectangle", ["Selection", "Select"], "menu_item", sources=("menu-expand",))])
    fx = Effector(0, allow_input=False)
    ex = X.Executor(0, fx, cat, owned=True)
    rot = ex._step_for_verb(cat.verbs[0], "g", 1.0, "guide").routes
    pr = next(v for v in cat.verbs if v.label == "Profile")
    si = next(v for v in cat.verbs if v.label == "Sign in")
    s_plain = ex._step_for_verb(pr, "g", 1.0, "guide")
    ex.sandboxed = True
    s_sand = ex._step_for_verb(pr, "g", 1.0, "guide")
    s_cred = ex._step_for_verb(si, "g", 1.0, "guide")
    ex.deny = re.compile(r"\bsave\b", re.I)
    s_deny = ex._step_for_verb(next(v for v in cat.verbs if v.label == "Save"), "g", 1.0, "guide")
    nodes_main = [N("TextControl", "Rotate", (1, 1, 5, 5), ("text",), idx=0), N("ButtonControl", "Rotate", (1, 1, 5, 5), ("invoke", "expand"), idx=1), N("ListItemControl", "Rectangle", (1, 1, 5, 5), ("select",), idx=2)]
    nodes_pop = [N("MenuItemControl", "Rectangle", (6, 6, 80, 30), ("invoke",), idx=0)]
    ex._all_nodes = lambda: (setattr(ex, "_main_n", len(nodes_main)) or nodes_main + nodes_pop)
    live_rot = ex._live_node(cat.verbs[0])
    live_rect = ex._live_node(cat.verbs[-1])
    field = next(v for v in cat.verbs if v.label == "Width")
    plain_field = next(v for v in cat.verbs if v.label == "Name")
    checks = {"dropdown_is_expanded_first": rot and rot[0].startswith("expand:") and any(r.startswith("control:") for r in rot), "button_beats_its_label": live_rot is not None and live_rot.ctype == "ButtonControl",
              "flyout_item_found_in_flyout_window": live_rect is not None and live_rect.ctype == "MenuItemControl", "sensitive_waits_normally": s_plain.need_human, "sensitive_harmless_in_throwaway_state": not s_sand.need_human,
              "credentials_still_human": s_cred.need_human, "deny_policy_always_human": s_deny.need_human, "numeric_field_gets_its_range": ex.placeholder_for(field) == "100" and ex.placeholder_for(plain_field) == ex.placeholder}
    img = viz.render_popup([N("MenuItemControl", "New tab", (6, 6, 283, 41), ("invoke",), accel="Ctrl+N")], (300, 200), "File flyout")
    img2 = viz.tree_overlay(img, (0, 0), [N("ButtonControl", "x", (10, 30, 80, 60), ("invoke",), depth=2)])
    checks["flyout_and_tree_pictures_drawn"] = img.size[0] >= 220 and img2.size[1] == img.size[1] + 34 and img2.getpixel((20, 30)) != img.getpixel((20, 30))
    return _verdict(checks)



# ====================================================================================================================== PR57 toolkit families, corpus catalog, registry + virtual mouse
def run_pr57() -> TestOutcome:
    """PR57: what kind of window it is comes from the window, not from a name - toolkit families are recognised from classes / framework ids / processes; the corpus catalog resolves a process to its guide;
    the registry knows every application with its guide and action counts; the virtual mouse leaves a planned route as a database row linked to the action it preceded"""
    from core_organs.professor import interaction as IA, history as HS, virtual_mouse as VM
    from core_organs.professor.knowledge import guide_corpus as GC
    from core_organs.professor.schema import Box
    k = {"chrome": IA.classify_from("Chrome_WidgetWin_1", "chrome.exe").family, "electron": IA.classify_from("Chrome_WidgetWin_1", "Code.exe").family,
         "office": IA.classify_from("OpusApp", "WINWORD.EXE").family, "winui": IA.classify_from("WinUIDesktopWin32WindowClass", "Notepad.exe", "XAML").family,
         "uwp": IA.classify_from("ApplicationFrameWindow", "x.exe").family, "wpf": IA.classify_from("HwndWrapper[App;;1]", "x.exe").family, "winforms": IA.classify_from("WindowsForms10.Window.8.app", "x.exe").family,
         "qt": IA.classify_from("Qt5152QWindowIcon", "x.exe").family, "gl": IA.classify_from("GHOST_WindowClass", "blender.exe").family, "dialog": IA.classify_from("#32770", "x.exe").family}
    cat = GC.load_catalog()
    keys = {a["key"] for a in cat}
    h = HS.History(_tmp("reg") + ".db")
    try:
        h.register_app("demo", "Demo", "demo.exe", "winui", 1, 12, 88, "n")
        tid = h.log("demo", "guide", "invoke", "Bold", "control:Bold", "a", "n", "b", "s", "state_change", True)
        h.log_guide_run("demo", "src", "cite", "Make bold", 2, 1.0, True, True, "ok", 1)
        h.log_guide_run("demo", "src", "cite2", "Make red", 2, 1.0, True, False, "no effect", 1)
        mouse = VM.VirtualMouse(None, h, "demo", visible=False)
        tr = mouse.move_to(Box(100, 100, 160, 130), "Bold", "click", "Ctrl+B", 1, transition_id=tid)
        reg = h.registry("demo")[0]
        ps = h.pointer_stats("demo")
        checks = {"toolkit_families": k == {"chrome": "chromium-browser", "electron": "electron", "office": "office", "winui": "winui", "uwp": "uwp-xaml", "wpf": "wpf", "winforms": "winforms", "qt": "qt", "gl": "gl-canvas", "dialog": "win32-dialog"},
                  "catalog_lists_the_tier_apps": {"notepad", "mspaint", "chrome", "winword", "powerpnt"} <= keys and len(cat) >= 80, "process_resolves_to_its_guide_key": GC.canonical_key("chrome.exe") == "chrome" and GC.canonical_key("nothing.exe") == "",
                  "find_app_by_name_or_key": (GC.find_app("Google Chrome") or {}).get("key") == "chrome", "registry_row_per_app": reg["app"] == "demo" and reg["toolkit"] == "winui" and reg["guide_docs"] == 12 and reg["actions_performed"] == 1,
                  "guide_procedures_tried_and_passed": reg["guide_procedures_tried"] == 2 and reg["guide_procedures_passed"] == 1, "route_planned_and_recorded": tr["planned_s"] > 0 and tr["visible"] is False and ps.get("traces", ps.get("n", 0)) >= 1}
        return _verdict(checks, str(k))
    finally:
        h.close()


# ====================================================================================================================== PR58 vague steps
def run_pr58() -> TestOutcome:
    """PR58: a manual's vague steps are neither dropped nor forced - 'choose a color from the color palette' takes an item of the closest group of the live interface (and says so), 'if needed' steps are
    skipped as optional, a pointer gesture is named, a step that names nothing at all is UNDERSPECIFIED (so a half-run procedure can never look finished), and the executor performs / skips accordingly"""
    from core_organs.professor.knowledge import guide_steps as GS
    from core_organs.professor import executor as X
    from core_organs.professor.effectors import Effector
    from core_organs.professor.harvest import Catalog, Verb

    def V(l, path, role="button"):
        return Verb(l, l, list(path), "", "", True, False, "", 0, "", role, ["uia"], "measured", "safe")
    cat = Catalog(app_key="d", verbs=[V("Black", ["Colours"]), V("Red", ["Colours"]), V("Pencil", ["Tools"]), V("Size", ["Selection"], "field"), V("Delete all", ["Colours"])])
    t = "1. Select the **Pencil** tool.\n2. Choose a color from the color palette.\n3. Choose a line size if needed.\n4. Draw on the canvas.\n5. Click something suitable."
    steps = GS.parse_steps(t)
    g = GS.ground(steps, cat)
    hows = [x.how for x in g]
    ex = X.Executor(0, Effector(0, allow_input=False), cat, owned=True)
    rep = ex.plan_from_procedure("demo", "c", steps)
    kinds = [s.kind for s in rep.steps]
    checks = {"named_control_grounds": hows[0] == "label", "item_of_the_closest_group_taken": hows[1] == "group" and g[1].verb is not None and g[1].verb.label == "Black" and "Colours" in g[1].note,
              "unsafe_item_never_taken": g[1].verb.label != "Delete all", "optional_step_is_skipped": hows[2] == "optional", "gesture_is_named": hows[3] == "gesture", "nothing_named_is_underspecified": hows[4] == "none" and "names no control" in g[4].note,
              "grounded_share_counts_only_real_matches": sum(1 for x in hows if x in GS.GROUNDED_HOW) == 3, "executor_plans_verb_skip_unknown": kinds[:3] == ["verb", "verb", "skip"] and kinds[3] == "gesture" and rep.steps[3].text in ("stroke", "drag", "select_area")}
    return _verdict(checks, str(hows))

# ====================================================================================================================== PR59 clicking through hidden options
def run_pr59() -> TestOutcome:
    """PR59: the scan goes below the first menu level - submenus are entered to a bounded depth (and the person's own recent files are not), a button is clicked to reveal a dialog / page only when its
    wording says so (never toggles, file pickers, web / account links, the document-changing verbs), and the hidden-options map lists every menu, submenu and dialog with its items"""
    from types import SimpleNamespace as NS
    from core_organs.professor import menus as MN, reveal as RV
    from core_organs.professor.harvest import Catalog

    J = lambda label, path=(), role="menuitem", pats=("invoke",): RV.judge(label, list(path), role, list(pats))
    ok_open = [J("Page setup", ["File"]), J("Font", ["Edit"]), J("Settings", [], "button"), J("Insert table...", ["Table"]), J("Resize and skew", [], "button"), J("About", ["Help"]), J("Go to", ["Edit"]), J("Find", ["Edit"])]
    refused = {"toggle": J("Word wrap", ["View"], pats=("toggle",)), "opener": J("Zoom", ["View"], pats=("expand",)), "web": J("Search with Bing", ["Edit"]), "picker": J("Open", ["File"]), "save": J("Save as...", ["File"]),
               "print": J("Print", ["File"]), "exit": J("Exit", ["File"]), "recent": J("Recent files", ["File"]), "undo": J("Undo", ["Edit"]), "next": J("Find next", ["Edit"]), "avatar": J("User avatar", [], "button"),
               "helplink": J("View help", ["Help"]), "plain": J("Banana", ["Edit"])}
    # a fake interface: View > Zoom > More > Deep item, View > Recent (the person's files), a toggle
    world = {"open": set()}
    ITEMS = {"View": ["Zoom", "Recent", "Status bar"], "Zoom": ["Zoom in", "Zoom out", "More"], "More": ["Deep item"], "Recent": ["secret-file.txt"]}
    EXP = {"Zoom", "Recent", "More"}
    n_counter = [0]

    def node(name):
        n_counter[0] += 1
        return NS(role="menuitem", name=name, pats=(["expand"] if name in EXP else (["toggle"] if name == "Status bar" else ["invoke"])), expand_state=(0 if name in EXP else -1), enabled=True, offscreen=False,
                  aid="", help="", accel="", selected=False, toggle_state=-1, rect=(0, n_counter[0] * 10, 50, n_counter[0] * 10 + 9), ctype="MenuItemControl", ctrl=None, idx=n_counter[0])

    def all_nodes():
        out = []
        for parent in ["View"] + sorted(world["open"] - {"View"}):
            if parent in world["open"]:
                out += [node(x) for x in ITEMS.get(parent, [])]
        return out
    real_expand, real_collapse, real_await = MN._expand, MN.collapse, MN._await_items
    MN._expand = lambda fx, n, deadline_s=2.0: (world["open"].add(n.name) or True, "UIA Expand")
    MN.collapse = lambda n, deadline_s=1.5: (world["open"].discard(n.name) or True)
    MN._await_items = lambda all_n, base, wait_s=2.0, step_s=0.25: (all_n(), [n for n in all_n() if MN._ident(n) not in base and n.name])
    try:
        world["open"].add("View")
        cat = Catalog(app_key="fake")
        rep = {"items": 0, "submenus": 0, "failed": [], "skipped": [], "by_opener": {}}
        have = set()
        top = all_nodes()
        for n in top:
            MN.add_item_verb(cat, have, ["View"], n)
        MN._descend(None, all_nodes, cat, have, NS(name="View"), top, ["View"], 1, 2, time.time() + 30, None, rep, lambda: world["open"].add("View"))
        deep2 = len(cat.verbs)
        cat2, rep2, have2 = Catalog(app_key="fake"), {"items": 0, "submenus": 0, "failed": [], "skipped": [], "by_opener": {}}, set()
        world["open"] = {"View"}
        for n in all_nodes():
            MN.add_item_verb(cat2, have2, ["View"], n)
        MN._descend(None, all_nodes, cat2, have2, NS(name="View"), all_nodes(), ["View"], 1, 1, time.time() + 30, None, rep2, lambda: world["open"].add("View"))
    finally:
        MN._expand, MN.collapse, MN._await_items = real_expand, real_collapse, real_await
    labels = {tuple(v.path): [x.label for x in cat.verbs if x.path == v.path] for v in cat.verbs}
    cands, skipped = RV.collect([{"path": ["File"], "label": "Page setup", "role": "menuitem", "pats": ["invoke"], "aid": "", "enabled": True}, {"path": ["File"], "label": "Open", "role": "menuitem", "pats": ["invoke"], "aid": "", "enabled": True},
                                 {"path": ["Edit"], "label": "Insert picture...", "role": "menuitem", "pats": ["invoke"], "aid": "", "enabled": True}], [])
    mp = RV.build_map(cat, [{"path": "View > Zoom", "kind": "submenu"}])
    checks = {"dialog_wording_is_clicked": all(r[0] for r in ok_open), "toggles_openers_web_files_and_edits_are_not": not any(r[0] for r in refused.values()),
              "refusals_name_a_reason": all(r[1] for r in refused.values()), "only_look_alikes_are_listed_as_refused": refused["web"][2] and refused["picker"][2] and not refused["plain"][2] and not refused["undo"][2],
              "submenu_entered_two_levels": ["Deep item"] in [labels.get(("View", "Zoom", "More"))] and "Zoom in" in labels.get(("View", "Zoom"), []),
              "depth_is_bounded": ("View", "Zoom", "More") not in {tuple(v.path) for v in cat2.verbs} or "Deep item" not in [v.label for v in cat2.verbs],
              "the_persons_files_stay_closed": "secret-file.txt" not in [v.label for v in cat.verbs] and any("Recent" in s["path"] for s in rep["skipped"]),
              "candidates_exclude_file_pickers": [c.label for c in cands] == ["Page setup"] and any(s["path"].endswith("Open") for s in skipped) and any("Insert picture" in s["path"] for s in skipped),
              "map_lists_menu_and_submenus": {r["path"]: r["kind"] for r in mp}.get("View > Zoom") == "submenu" and any(r["path"] == "View" and r["kind"] == "menu" for r in mp)}
    return _verdict(checks, f"{deep2} verbs filed; skipped={rep['skipped']}; map={[(r['path'], r['kind']) for r in mp]}")


# ====================================================================================================================== PR60 checklist + bundle
def run_pr60() -> TestOutcome:
    """PR60: the manual run keeps a RESUMABLE checklist - stages are read from the finished report, an application whose checkpoint says done is not run again (unless asked), a crash in one application
    does not stop the next, and everything lands in one folder (pictures, INDEX.html, CHECKLIST.md, run.log, zip)"""
    import tempfile
    from core_organs.professor import checkpoints as CK, apprun as AR
    from PIL import Image
    good = {"phases": {"launch": {"launched": True}, "deep_scan": {"nodes": 60, "depth": 7, "state": "rich"}, "vision_scan": {"elements": 30, "vision_model": True}, "catalog_after_menus": {"verbs": 80},
                       "menus": {"openers": 7, "opened": 7, "items": 50, "submenus": 2}, "options": {"tried": 6, "opened": 4, "dialogs": 1, "pages": 3}, "guide": {"runnable_procedures": 2}, "close": {}, "state_after": {}},
            "ledger_counts": {"ok": 2, "blocked": 1, "skipped": 3}, "counts": {"ok": 2, "blocked": 1, "failed": 0}}
    bad = json.loads(json.dumps(good))
    bad["ledger_counts"] = {"ok": 1, "failed": 2}
    bad["phases"]["options"] = {"tried": 1, "opened": 1, "tainted": True, "stopped": "could not prove the application is back"}
    dead = {"result": "launch_failed", "phases": {"launch": {"launched": False, "notes": "no window"}}}
    with tempfile.TemporaryDirectory() as tmp:
        d1 = os.path.join(tmp, "a")
        os.makedirs(os.path.join(d1, "checkpoints"))
        for n in ("scan_1_first.png", "flyout_01_File.png", "option_01_page_Settings.png", os.path.join("checkpoints", "cp_01_launched.png")):
            Image.new("RGB", (8, 8), (10, 20, 30)).save(os.path.join(d1, n))
        s_good, s_bad, s_dead = CK.stage_states(good, d1), CK.stage_states(bad, d1), CK.stage_states(dead, d1)
        st_good, st_bad, st_dead = CK.app_status(s_good, good), CK.app_status(s_bad, bad), CK.app_status(s_dead, dead)
        # the run itself, with a fake AppRun: one application succeeds, one crashes, a second run skips the finished one
        calls = []

        class FakeRun:
            def __init__(self, spec, **kw):
                self.spec, self.kw = spec, kw

            def run(self):
                calls.append(self.spec.key)
                if self.spec.key == "mspaint":
                    raise RuntimeError("boom")
                d = self.kw["out_dir"]
                os.makedirs(os.path.join(d, "checkpoints"), exist_ok=True)
                for n in ("scan_1_first.png", "flyout_01_File.png", "option_01_page_Settings.png", os.path.join("checkpoints", "cp_01_launched.png")):
                    Image.new("RGB", (8, 8), (1, 2, 3)).save(os.path.join(d, n))
                with open(os.path.join(d, "report.html"), "w") as fh:
                    fh.write("<html></html>")
                return json.loads(json.dumps(good))
        real = (AR.AppRun, CK.STATE_PATH, CK.CHECKLIST_COPY, CK.DEFAULT_OUT)
        AR.AppRun, CK.STATE_PATH, CK.CHECKLIST_COPY, CK.DEFAULT_OUT = FakeRun, os.path.join(tmp, "state.json"), os.path.join(tmp, "copy.md"), os.path.join(tmp, "out")
        try:
            r1 = CK.run(["notepad", "mspaint"], vision=False, out=os.path.join(tmp, "run1"))
            st1 = CK.load_state()
            r2 = CK.run(["notepad", "mspaint"], vision=False, out=os.path.join(tmp, "run2"))
            r3 = CK.run(["notepad"], vision=False, again=True, out=os.path.join(tmp, "run3"), zip_it=False)
        finally:
            AR.AppRun, CK.STATE_PATH, CK.CHECKLIST_COPY, CK.DEFAULT_OUT = real
        files1 = set(os.listdir(os.path.join(tmp, "run1")))
        index = open(os.path.join(tmp, "run1", "INDEX.html"), encoding="utf-8").read()
        md = open(os.path.join(tmp, "run1", "CHECKLIST.md"), encoding="utf-8").read()
        checks = {"stages_read_from_report": all(s_good[k]["state"] == "ok" for k in ("launched", "tree_scan", "vision_scan", "menus", "options", "guide", "pictures")) and st_good == "done",
                  "tainted_options_and_failed_guide_are_partial": s_bad["options"]["state"] == "partial" and s_bad["guide"]["state"] == "partial" and st_bad == "partial",
                  "launch_failure_is_failed": st_dead == "failed" and s_dead["launched"]["state"] == "fail",
                  "scan_only_is_not_done": CK.app_status(s_good, good, guide_expected=False) == "scanned",
                  "a_crash_does_not_stop_the_next_app": calls[:2] == ["notepad", "mspaint"] and st1["apps"]["notepad"]["status"] == "done" and st1["apps"]["mspaint"]["status"] == "failed",
                  "done_is_not_run_again_failed_is": calls[2:] == ["mspaint", "notepad"] and r2["ran"] == ["mspaint"],
                  "one_folder_with_everything": {"INDEX.html", "CHECKLIST.md", "run.log", "notepad", "mspaint"} <= files1 and bool(r1["zip"]) and os.path.basename(r1["zip"]) == "run1.zip",
                  "index_links_pictures_and_report": "notepad/scan_1_first.png" in index and "notepad/report.html" in index and "notepad/checkpoints/cp_01_launched.png" in index,
                  "checklist_shows_tiers_and_open_items": "| notepad | 0 |" in md and "What is still open" in md and "| winword | 1 |" in md}
    return _verdict(checks, f"calls={calls} statuses={st_good}/{st_bad}/{st_dead} files={sorted(files1)}")


# ====================================================================================================================== PR61 popups, file dialogs, clipboard
def run_pr61() -> TestOutcome:
    """PR61: dialogs are handled from what they CONTAIN - an Open dialog gets a fixture of the type its own filter asks for, a Save dialog is forced into the sandbox, a message box is answered by wording
    policy (never 'save my work', never 'allow'), an application form is left to the guide; nothing outside the sandbox is chosen; the person's clipboard is saved before the run writes and put back after
    (unless the person copied something else meanwhile, or it holds something that cannot be put back); document-local verbs (Remove background) may run in a throw-away editor, closing / files / accounts may not"""
    import tempfile
    from types import SimpleNamespace as NS
    from core_organs.professor import dialogs as DG, executor as X
    from core_organs.professor.effectors import Effector
    from core_organs.professor.harvest import Catalog, Verb
    from core_organs.professor.knowledge import guide_steps as GS
    from PIL import Image

    # ---- fixtures of every kind a dialog's filter can ask for
    with tempfile.TemporaryDirectory() as tmp:
        sb = DG.Sandbox("demo", "t", root=os.path.join(tmp, "sb"))
        made = {e: sb.fixture("open " + h, [e]) for e, h in (("csv", "passwords"), ("png", "picture"), ("docx", ""), ("xlsx", ""), ("pptx", ""), ("pdf", ""), ("wav", ""), ("html", "bookmarks"), ("json", ""), ("txt", ""))}
        from docx import Document
        from openpyxl import load_workbook
        valid = (Image.open(made["png"]).size == (320, 200) and bool(Document(made["docx"]).paragraphs) and load_workbook(made["xlsx"]).active.max_row == 3 and open(made["pdf"], "rb").read(4) == b"%PDF"
                 and "NETSCAPE-Bookmark" in open(made["html"], encoding="utf-8").read() and "password" in open(made["csv"], encoding="utf-8").read().split("\n")[0])
        guess = (sb.pick_ext("choose a picture"), sb.pick_ext("Import Passwords To Chrome"), sb.pick_ext("", ["PNG", "jpg"]), sb.pick_ext("anything"))
        t1, t2 = sb.save_target("Chrome Passwords", ["csv"]), sb.save_target("report.docx")
        open(t1, "w").write("x")
        t3 = sb.save_target("Chrome Passwords", ["csv"])
        inside = sb.inside(t1) and not sb.inside(os.path.join(tmp, "elsewhere", "x.txt")) and not sb.inside(os.path.join(tmp, "sb", "..", "x.txt"))
        # ---- reading dialogs
        real_value = DG._value_of
        DG._value_of = lambda n: getattr(n, "value", "")

        def nd(i, parent, role, name, pats=(), value="", sel=False):
            return NS(idx=i, parent=parent, role=role, name=name, pats=list(pats), offscreen=False, enabled=True, selected=sel, value=value, rect=(0, 0, 10, 10), ctype=role.title() + "Control", ctrl=None)
        import core_organs.fast_uia as FU
        import core_organs.headless_input as HI
        real = (FU.snapshot, HI.safe_window_text, HI._class_name)
        dialogs = {
            1: ("Import Passwords To Chrome", [nd(0, -1, "window", ""), nd(1, 0, "combobox", "File name:"), nd(2, 1, "edit", "File name:", ["value"], "Chrome Passwords"), nd(3, 0, "combobox", "Files of type:"),
                                               nd(4, 3, "edit", "Files of type:", ["value"], "Microsoft Excel Comma Separated Values File (*.csv)"), nd(5, 0, "button", "Open"), nd(6, 0, "button", "Cancel")]),
            2: ("Save As", [nd(0, -1, "combobox", "File name:"), nd(1, 0, "edit", "File name:", ["value"], "Untitled.txt"), nd(2, -1, "combobox", "Save as type:"), nd(3, 2, "edit", "Save as type:", ["value"], "Text Documents (*.txt)"),
                            nd(4, -1, "button", "Save"), nd(5, -1, "button", "Cancel")]),
            3: ("Notepad", [nd(0, -1, "text", "Do you want to save changes to Untitled?"), nd(1, -1, "button", "Save"), nd(2, -1, "button", "Don't save"), nd(3, -1, "button", "Cancel")]),
            4: ("Page setup", [nd(0, -1, "edit", "Left:"), nd(1, -1, "edit", "Right:"), nd(2, -1, "edit", "Top:"), nd(3, -1, "checkbox", "Landscape"), nd(4, -1, "button", "OK"), nd(5, -1, "button", "Cancel")]),
            5: ("Print", [nd(0, -1, "combobox", "Select Printer"), nd(1, -1, "edit", "Pages"), nd(2, -1, "button", "Print"), nd(3, -1, "button", "Cancel")]),
            6: ("Confirm Save As", [nd(0, -1, "text", "Chrome Passwords.csv already exists. Do you want to replace it?"), nd(1, -1, "button", "Yes"), nd(2, -1, "button", "No")]),
            7: ("Notepad", [nd(0, -1, "text", "chrome.exe wants to use your camera. Allow access?"), nd(1, -1, "button", "Allow"), nd(2, -1, "button", "Block")]),
        }
        FU.snapshot = lambda h, timeout_ms=0: dialogs[h][1]
        HI.safe_window_text = lambda h, timeout_ms=150: dialogs[h][0]
        HI._class_name = lambda h: "#32770"
        try:
            infos = {h: DG.inspect(h) for h in dialogs}
        finally:
            FU.snapshot, HI.safe_window_text, HI._class_name = real
        kinds = {h: i.kind for h, i in infos.items()}
        pick = {h: DG.choose_button(infos[h], True)[0] for h in (3, 6, 7)}
        pick_outside = DG.choose_button(infos[6], False)[0]
        # ---- driving an Open dialog (the effector is a recorder)
        calls = []

        class FakeFx:
            allowed = True

            def set_value(self, n, text):
                calls.append(("set", text))
                n.value = text
                return True, "UIA SetValue"

            def insert_text(self, text):
                calls.append(("type", text))
                return True, "typed"

            def node(self, n):
                calls.append(("click", n.name))
                return True, "UIA Invoke"
        drv = DG.DialogDriver(FakeFx(), 0, sb, history=None)
        drv._closed = lambda h, max_s=6.0: True
        drv.windows = lambda: []
        drv._exists_soon = lambda p, max_s=3.0: True
        r_open = drv.drive(infos[1])
        r_save = drv.drive(infos[2])
        r_msg = drv.drive(infos[3])
        r_form = drv.drive(infos[4])
        r_print = drv.drive(infos[5])
        set_paths = [c[1] for c in calls if c[0] == "set"]
        # ---- the clipboard, on a fake
        store = {}

        class FakeWC:
            def EnumClipboardFormats(self, f):
                ks = sorted(store)
                return 0 if (not ks or f >= ks[-1]) else next(k for k in ks if k > f)

            def GetClipboardData(self, f):
                return store[f]

            def SetClipboardData(self, f, d):
                store[f] = d

            def EmptyClipboard(self):
                store.clear()

            def CloseClipboard(self):
                pass

            def GetClipboardFormatName(self, f):
                return {0xC001: "SomePrivateFormat"}.get(f, "")
        real_open = DG.ClipboardGuard._open
        DG.ClipboardGuard._open = staticmethod(lambda retries=15: FakeWC())
        try:
            store.clear()
            store[13] = "the person's text"
            g1 = DG.ClipboardGuard()
            g1.put_text("fixture")
            during = store.get(13)
            note1 = g1.end()
            restored = store.get(13) == "the person's text"
            store.clear()
            store[13] = "the person's text"
            g2 = DG.ClipboardGuard()
            g2.put_text("fixture")
            store[13] = "something the person copied meanwhile"
            note2 = g2.end()
            left_alone = store.get(13) == "something the person copied meanwhile"
            store.clear()
            store[13] = "text"
            store[0xC001] = b"private"
            g3 = DG.ClipboardGuard()
            try:
                g3.put_text("fixture")
                refused = False
            except DG.ClipboardBusy:
                refused = True
            untouched = store.get(13) == "text"
            store.clear()
            g4 = DG.ClipboardGuard()
            g4.put_text("fixture")
            g4.end()
            empty_again = not store
        finally:
            DG.ClipboardGuard._open = real_open
            DG._value_of = real_value
        # ---- policy: document-local verbs, file steps
        cat = Catalog(app_key="d", verbs=[])
        ex = X.Executor(0, Effector(0, allow_input=False), cat, owned=True, archetype="raster_editor")
        ex.sandboxed = True
        V = lambda l, p=(): Verb(l, l, list(p), "", "", True, False, "", 0, "", "button", ["uia"], "measured", "unsafe")
        local = [ex._doc_local(V(x)) for x in ("Remove background", "Delete", "Clear selection")]
        not_local = [ex._doc_local(V(x)) for x in ("Close tab", "Exit", "Delete browsing data", "Delete all files", "Sign out", "Uninstall")]
        ex.archetype = "browser_web"
        browser_local = ex._doc_local(V("Delete"))
        GS.SANDBOX_FILES = True
        g_on = GS.parse_steps("1. Select the image you want to open.\n2. Click Open.")
        how_on = [x.how for x in GS.ground(g_on, cat)]
        GS.SANDBOX_FILES = False
        how_off = [x.how for x in GS.ground(GS.parse_steps("1. Select the image you want to open."), cat)]
        st = lambda goal, kind="unknown": X.Step(0, goal, kind=kind, source="guide")
        file_steps = [ex._is_file_step(st(g)) for g in ("Select the image you want to open.", "Type a name for your file in the File name box.", "Click Save.", "In the Save As dialog, choose a folder.")]
        not_file_steps = [ex._is_file_step(st(g)) for g in ("Click File > Open.", "Select the Pencil tool.", "Rotate the picture.", "Select OK.", "Select Save as from the File menu.")]
        ex._file_followups = 2
        ok_while_following = ex._is_file_step(st("Select OK."))
        ex._file_followups = 0
        rx_ok = bool(DG.COPY_RX.search("Copy Ctrl+C")) and bool(DG.PASTE_RX.search("Paste Ctrl+V")) and DG.PASTE_RX.search("Pasteboard settings") is None
    checks = {"fixtures_are_real_files_of_the_asked_type": valid, "type_comes_from_the_filter_then_the_wording": guess == ("png", "csv", "png", "txt"),
              "save_target_is_unique_and_in_the_outbox": os.path.basename(t1) == "Chrome_Passwords.csv" and t3 != t1 and t2.endswith("report.docx") and "outbox" in t1 and inside,
              "dialogs_are_told_apart_by_content": kinds == {1: "file_open", 2: "file_save", 3: "message", 4: "other", 5: "print", 6: "message", 7: "message"},
              "filter_and_default_name_are_read": infos[1].filter_exts == ["csv"] and infos[1].default_name == "Chrome Passwords" and infos[2].filter_exts == ["txt"],
              "message_policy": pick == {3: "Don't save", 6: "Yes", 7: "Block"} and pick_outside == "No",
              "open_dialog_gets_a_csv_fixture_inside_the_sandbox": r_open["ok"] and r_open["path"].endswith(".csv") and sb.inside(r_open["path"]) and ("click", "Open") in calls,
              "save_dialog_is_forced_into_the_sandbox": r_save["ok"] and "outbox" in r_save["path"] and sb.inside(r_save["path"]) and ("click", "Save") in calls and all(sb.inside(p) for p in set_paths),
              "message_and_print_answered_form_left_alone": r_msg["ok"] and ("click", "Don't save") in calls and r_print["ok"] and ("click", "Cancel") in calls and r_form.get("left") is True,
              "clipboard_given_back": during == "fixture" and restored and "put back" in note1 and left_alone and "left alone" in note2 and refused and untouched and empty_again,
              "document_local_verbs_only_in_an_editor": all(local) and not any(not_local) and browser_local is False,
              "file_steps_become_dialog_steps_only_with_a_sandbox": how_on[0] == "dialog" and how_off == ["human"],
              "file_step_wording_vs_ordinary_steps": all(file_steps) and not any(not_file_steps) and ok_while_following, "copy_paste_wording": rx_ok}
    return _verdict(checks, f"kinds={kinds} pick={pick} calls={calls[:6]} file_steps={file_steps} not_file={not_file_steps} how_on={how_on}")


# ====================================================================================================================== PR62 the workflow library
def run_pr62() -> TestOutcome:
    """PR62: the guides become a LIBRARY - every procedure is analysed against the application's controls (path / label / chord / typed / file dialog / pointer gesture / human), written as readable
    markdown and fetchable json (one format for every application), found again by a plain request, given a last-run result, and turned back into a task the executor performs"""
    import tempfile
    from core_organs.professor import workflows as WF
    from core_organs.professor.harvest import Catalog, Verb
    from core_organs.professor.knowledge import manual_rag as MR
    guide = ("# Header and footer\n\n1. Select **File** > **Page setup**.\n2. In the **Header** box, type &f.\n3. Select **OK**.\n\n"
             "# Open a picture\n\n1. Select **File** > **Open**.\n2. Select the picture you want to open.\n3. Click **Open**.\n\n"
             "# Draw a line\n\n1. Select the **Pencil** tool.\n2. Click and drag on the canvas.\n\n"
             "# Copy and paste\n\n1. Select **Edit** > **Copy**.\n2. Press Ctrl+V.\n")

    def V(label, path=(), role="menu_item", sc=""):
        return Verb(label, label, list(path), sc, "", True, False, "", 0, "", role, ["uia"], "measured", "safe")
    cat = Catalog(app_key="demo", verbs=[V("Page setup", ["File"]), V("Header", ["File", "Page setup"], "field"), V("OK", ["File", "Page setup"], "button"), V("Open", ["File"], sc="Ctrl+O"), V("Pencil", ["Tools"], "button"),
                                         V("Copy", ["Edit"], sc="Ctrl+C"), V("Paste", ["Edit"], sc="Ctrl+V")])
    with tempfile.TemporaryDirectory() as tmp:
        ix = MR.ManualIndex(os.path.join(tmp, "m.db"))
        ix.ingest_text("demo", "Guide", guide, "https://example.test/guide", "md", embed=False)
        real = WF.WF_DIR
        WF.WF_DIR = os.path.join(tmp, "wf")
        GS = __import__("core_organs.professor.knowledge.guide_steps", fromlist=["x"])
        GS.SANDBOX_FILES = True
        try:
            doc = WF.build("demo", ix=ix, catalog=cat)
            ws = {w["goal"]: w for w in doc["workflows"]}
            md = open(WF.path_of("demo", "md"), encoding="utf-8").read()
            idx = open(os.path.join(WF.WF_DIR, "INDEX.md"), encoding="utf-8").read()
            again = WF.load("demo")
            found = WF.fetch("demo", "how do I rotate... open a picture file")
            by_id = WF.get(next(iter(ws.values()))["id"])
            hdr, opn, drw, cpy = ws.get("Header and footer"), ws.get("Open a picture"), ws.get("Draw a line"), ws.get("Copy and paste")
            WF.record_run("demo", {"started": "2026-10-10 12:00:00", "html": "x.html", "ledger": [{"goal": "Header and footer", "cite": hdr["cite"], "disposition": "ok", "reason": ""},
                                                                                                    {"goal": "Draw a line", "cite": drw["cite"], "disposition": "blocked", "reason": "needs a pointer gesture"}], "tasks": []})
            rec = WF.load("demo")
            rw = {w["goal"]: w for w in rec["workflows"]}
            task = WF.to_task(hdr)
        finally:
            WF.WF_DIR = real
            GS.SANDBOX_FILES = False
        ix.close()
    checks = {"every_procedure_is_a_workflow": len(ws) == 4 and doc["summary"]["workflows"] == 4,
              "ids_are_stable_and_unique": len({w["id"] for w in ws.values()}) == 4 and all(w["id"].startswith("demo.") for w in ws.values()),
              "path_steps_are_grounded_to_controls": hdr and [s["how"] for s in hdr["steps"]][:1] == ["path"] and hdr["steps"][0]["verb"] == "Page setup" and hdr["grounded_share"] >= 0.66,
              "file_choosing_needs_the_dialog_handler": opn and opn["status"] == "needs-file-dialog" and "file_dialog" in opn["requires"] and any(s["how"] == "dialog" for s in opn["steps"]),
              "pointer_gesture_is_named_not_run": drw and drw["status"] == "needs-pointer" and any(s["how"] == "gesture" for s in drw["steps"]),
              "clipboard_use_is_named": cpy and "clipboard" in cpy["requires"],
              "markdown_is_readable": "## Header and footer" in md and "| # | what the guide says |" in md and "Page setup" in md and "https://example.test/guide" in md,
              "index_lists_the_application": "| [demo](demo.md) |" in idx,
              "json_roundtrips": again and again["app"] == "demo" and len(again["workflows"]) == 4,
              "a_request_finds_its_workflow": bool(found) and found[0]["goal"] == "Open a picture" and by_id is not None,
              "last_run_is_recorded": rw["Header and footer"]["last_run"]["result"] == "ok" and rw["Draw a line"]["last_run"]["result"] == "blocked" and rw["Open a picture"]["last_run"]["result"] == "never",
              "functions_explained_by_the_guide": doc["summary"]["functions_explained_by_a_guide"] >= 3 and any(f["label"] == "Page setup" and f["explained_by"] for f in doc["functions"]),
              "workflow_becomes_a_task": task["goal"] == "Header and footer" and len(task["steps"]) == hdr["step_count"] and task["source"] == "https://example.test/guide"}
    return _verdict(checks, f"statuses={ {g: w['status'] for g, w in ws.items()} } requires={ {g: w['requires'] for g, w in ws.items()} } found={[w['goal'] for w in found]} task={task['goal']!r}/{len(task['steps'])}/{task['source']!r}")


TESTS = [("PR49", run_pr49), ("PR50", run_pr50), ("PR51", run_pr51), ("PR52", run_pr52), ("PR53", run_pr53), ("PR54", run_pr54), ("PR55", run_pr55), ("PR56", run_pr56), ("PR57", run_pr57), ("PR58", run_pr58), ("PR59", run_pr59), ("PR60", run_pr60), ("PR61", run_pr61), ("PR62", run_pr62)]


if __name__ == "__main__":
    only = [a.upper() for a in sys.argv[1:]]
    rc = 0
    for name, fn in TESTS:
        if only and name not in only:
            continue
        t0 = time.time()
        try:
            r = fn()
        except Exception:
            import traceback
            r = TestOutcome(False, "EXCEPTION " + traceback.format_exc()[-900:])
        print(f"[{'PASS' if r.passed else 'FAIL':4}] {name} {time.time() - t0:5.1f}s  {(fn.__doc__ or '').strip().splitlines()[0][:100]}\n        {r.evidence[:900]}")
        rc |= 0 if r.passed else 1
    sys.exit(rc)
