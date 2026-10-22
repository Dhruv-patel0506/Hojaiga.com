"""
test_offline_rag_replay.py -- offline, CPU-only replay of saved scan traces (Calculator, Paint, WhatsApp) through the scan gate, the Stage 2 -> 3 queue, the explanation layer,
live-rectangle re-normalisation and the RAG self-healing memory. No window, no GPU, no model, no network; HOJAIGA_ALLOW_LIVE stays 0 and every database is a temp file.

    python test_offline_rag_replay.py            (or: python -m unittest test_offline_rag_replay -v)

  T1 gate        calculator/paint/whatsapp traces judged by their archetype's core controls; a scan of the wrong window is INCOMPLETE_SCAN
  T2 rescan      INCOMPLETE_SCAN -> recursive_scan heals once a later scan holds the missing component; the best attempt is kept when none does
  T3 store       COMPLETE is retrievable (FTS), INCOMPLETE_SCAN is not and is listed for re-scan, a re-save replaces instead of duplicating, the master db is never opened
  T4 queue       no cap: every named non-chrome control reaches Stage 3, queue_audit balances, Undo/Redo/Status/Channels-style controls are present
  T5 explain     VLM sentence used when good; static template never emitted; fallback labelled; prompt carries container + siblings; cache avoids repeat calls
  T6 geometry    window moved / resized / focus-shifted -> the point is re-derived from the live rectangle; minimised / off-window / trap / credential are refused
  T7 crash-free  malformed traces, a corrupt / missing / directory database, and the real federated RAG (temp root, deterministic embedder) under replayed outcomes never raise
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["HOJAIGA_ALLOW_LIVE"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
ROOT = Path(r"D:\new_automation")
for _p in (str(ROOT), str(ROOT / "All codes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core_organs import scan_gate as G            # noqa: E402
from core_organs import tutor_logic as TL         # noqa: E402

TRACES = {"Calculator": ROOT / "calculator_scan_result.json", "Calculator (deep)": ROOT / "calculator_deep_scan_result.json",
          "Paint": ROOT / "paint_scan_result.json", "WhatsApp": ROOT / "whatsapp_scan_result.json", "WhatsApp (deep)": ROOT / "whatsapp_deep_scan_result.json"}
MASTER_DB = ROOT / "data" / "hojaiga_master_rag.db"


def load(label: str) -> dict:
    return json.loads(TRACES[label].read_text(encoding="utf-8"))


def surface(label: str) -> dict:
    return TL.controls_from_trace(load(label))


def app_of(label: str) -> str:
    return label.split(" (")[0]


class FakeWin:
    """A window whose rectangle can move between calls, like a real one when a panel opens or the user drags it."""

    def __init__(self, rect, minimized=False):
        self.l, self.t, self.w, self.h = rect
        self.minimized = minimized
        self.on_focus = None
        self.focused = 0

    def is_minimized(self):
        return self.minimized

    def rectangle(self):
        class R:
            pass
        r = R()
        r.left, r.top, r.right, r.bottom = self.l, self.t, self.l + self.w, self.t + self.h
        return r

    def set_focus(self):
        self.focused += 1
        if self.on_focus:
            self.on_focus(self)


class Rec:
    def __init__(self):
        self.calls = []

    def move(self, coords):
        self.calls.append(("move", tuple(coords)))

    def click(self, coords):
        self.calls.append(("click", tuple(coords)))

    def send_keys(self, text, with_spaces=True):
        self.calls.append(("keys", text))


class T1Gate(unittest.TestCase):
    def test_verdicts_follow_the_archetype_core(self):
        want = {"Calculator": (G.COMPLETE, []), "Calculator (deep)": (G.INCOMPLETE, ["display"]), "Paint": (G.INCOMPLETE, ["canvas"]),
                "WhatsApp": (G.COMPLETE, []), "WhatsApp (deep)": (G.COMPLETE, [])}
        for label, (status, missing) in want.items():
            v = G.validate_scan(load(label)["elements"], app_of(label))
            self.assertEqual(v["status"], status, f"{label}: {v['reason']}")
            self.assertEqual(v["missing"], missing, label)
            self.assertEqual(v["archetype_source"], "name")
            self.assertTrue(v["verified"])

    def test_expected_components_named(self):
        v = G.validate_scan(load("Calculator")["elements"], "Calculator")
        self.assertEqual({c["id"] for c in v["components"]}, {"keypad", "display"})
        v = G.validate_scan(load("Paint")["elements"], "Paint")
        self.assertEqual({c["id"] for c in v["components"]}, {"canvas", "tools"})
        v = G.validate_scan(load("WhatsApp")["elements"], "WhatsApp")
        self.assertEqual({c["id"] for c in v["components"]}, {"conversations", "input"})

    def test_import_to_canvas_is_not_a_canvas(self):
        v = G.validate_scan(load("Paint")["elements"], "Paint")
        canvas = next(c for c in v["components"] if c["id"] == "canvas")
        self.assertFalse(canvas["ok"])

    def test_wrong_window_is_incomplete_and_flagged(self):
        # a calculator scan that captured only the Windows Settings page (as the first calculator trace nearly did)
        settings = [{"name": n, "type": "ListItemControl"} for n in ["Home", "Bluetooth & devices", "Network & internet", "Personalization", "Apps", "Accounts",
                                                                       "Time & language", "Gaming", "Accessibility", "Privacy & security", "Windows Update"]]
        v = G.validate_scan(settings, "Calculator")
        self.assertEqual(v["status"], G.INCOMPLETE)
        self.assertIn("keypad", v["missing"])
        self.assertTrue(v.get("window_mismatch"))

    def test_too_few_and_unresolved(self):
        self.assertEqual(G.validate_scan([{"name": "OK", "type": "ButtonControl"}], "Calculator")["reason"], "too_few_controls")
        junk = [{"name": f"zzq{i}", "type": "ButtonControl"} for i in range(6)]
        self.assertEqual(G.validate_scan(junk, "")["reason"], "archetype_unresolved")


class T2Rescan(unittest.TestCase):
    def test_heals_on_a_later_scan(self):
        deep, full = load("Calculator (deep)"), load("Calculator")
        seq = [deep, full]
        scan = lambda a: {"controls": TL.controls_from_trace(seq[min(a, 1)])["controls"], "title": "Calculator"}
        got, v, hist = G.recursive_scan(scan, "Calculator", max_rescans=2)
        self.assertEqual(v["status"], G.COMPLETE)
        self.assertEqual([h["status"] for h in hist], [G.INCOMPLETE, G.COMPLETE])
        self.assertEqual(hist[0]["missing"], ["display"])

    def test_paint_heals_when_the_rescan_reads_the_canvas_surface(self):
        trace = load("Paint")
        base = TL.controls_from_trace(trace)["controls"]
        canvas = {"role": "Pane", "name": "Canvas", "bbox": [300, 300, 1500, 900]}      # what a wider (context-role) discovery adds; synthetic, labelled as such

        def scan(a):
            ctrls = base + ([canvas] if a >= 1 else [])
            return {"controls": base, "gate_controls": ctrls, "title": "Paint"}
        _, v, hist = G.recursive_scan(scan, "Paint", max_rescans=2)
        self.assertEqual(v["status"], G.COMPLETE)
        self.assertEqual(len(hist), 2)

    def test_keeps_best_and_stays_incomplete_when_nothing_heals(self):
        deep = TL.controls_from_trace(load("Calculator (deep)"))
        poor = {"controls": deep["controls"][:6], "title": "Calculator"}
        seq = [poor, deep, deep]
        got, v, hist = G.recursive_scan(lambda a: dict(seq[a], title="Calculator"), "Calculator", max_rescans=2)
        self.assertEqual(v["status"], G.INCOMPLETE)
        self.assertEqual(len(hist), 3)
        self.assertGreater(v["n_controls"], 6)               # the richest attempt, not the last or the first

    def test_scan_errors_do_not_escape(self):
        def boom(a):
            raise RuntimeError("uia hang")
        got, v, hist = G.recursive_scan(boom, "Calculator", max_rescans=1)
        self.assertIsNone(got)
        self.assertEqual(v["status"], G.INCOMPLETE)
        self.assertEqual(len(hist), 2)


class T3Store(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="replay_db_")
        self.db = os.path.join(self.dir, "rag.db")
        self.assertNotEqual(Path(self.db).resolve(), MASTER_DB.resolve())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def fts(self, q):
        c = sqlite3.connect(self.db)
        try:
            return c.execute("SELECT goal FROM causal_procedures_fts WHERE causal_procedures_fts MATCH ?", (q,)).fetchall()
        finally:
            c.close()

    def test_complete_is_retrievable_incomplete_is_not(self):
        vc = G.validate_scan(load("Calculator")["elements"], "Calculator")
        vp = G.validate_scan(load("Paint")["elements"], "Paint")
        self.assertTrue(G.record_scan(self.db, "calculator", "Calculator", vc, "does arithmetic", [{"step_num": 1}])["saved"])
        self.assertTrue(G.record_scan(self.db, "paint", "Paint", vp, "draws", [{"step_num": 1}])["saved"])
        self.assertEqual(len(self.fts("Calculator")), 1)
        self.assertEqual(self.fts("Paint"), [])
        self.assertEqual(G.get_status(self.db, "paint")["status"], G.INCOMPLETE)
        self.assertEqual(G.get_status(self.db, "paint")["missing"], ["canvas"])
        self.assertEqual(G.get_status(self.db, "calculator")["status"], G.COMPLETE)
        self.assertEqual(G.pending_rescans(self.db), ["paint"])

    def test_rescan_promotes_without_duplicates(self):
        bad = G.validate_scan(load("Calculator (deep)")["elements"], "Calculator")
        good = G.validate_scan(load("Calculator")["elements"], "Calculator")
        G.record_scan(self.db, "calculator", "Calculator", bad)
        self.assertEqual(self.fts("Calculator"), [])
        G.record_scan(self.db, "calculator", "Calculator", good, "p1", [])
        G.record_scan(self.db, "calculator", "Calculator", good, "p2", [])
        self.assertEqual(len(self.fts("Calculator")), 1)
        st = G.get_status(self.db, "calculator")
        self.assertEqual((st["status"], st["attempts"]), (G.COMPLETE, 3))
        self.assertEqual(G.pending_rescans(self.db), [])

    def test_a_good_scan_is_not_erased_by_a_later_bad_one(self):
        good = G.validate_scan(load("Calculator")["elements"], "Calculator")
        bad = G.validate_scan(load("Calculator (deep)")["elements"], "Calculator")
        G.record_scan(self.db, "calculator", "Calculator", good, "p", [])
        G.record_scan(self.db, "calculator", "Calculator", bad)
        self.assertEqual(len(self.fts("Calculator")), 1)       # the earlier workflow stays retrievable; the status shows the new scan was incomplete
        self.assertEqual(G.get_status(self.db, "calculator")["status"], G.INCOMPLETE)

    def test_master_schema_is_used(self):
        G.record_scan(self.db, "calculator", "Calculator", G.validate_scan(load("Calculator")["elements"], "Calculator"), "p", [])
        c = sqlite3.connect(self.db)
        cols = [r[1] for r in c.execute("PRAGMA table_info(causal_procedures_fts)")]
        row = c.execute("SELECT arch_id, domain, trap_guard FROM causal_procedures_fts").fetchone()
        c.close()
        self.assertEqual(cols, ["arch_id", "domain", "goal", "steps_json", "trap_guard"])
        self.assertEqual(row, ("UI_CALCULATOR", "desktop_app", "AUTO_DISCOVERY_VERIFIED"))


class T4Queue(unittest.TestCase):
    def test_no_cap_and_balanced(self):
        for label in TRACES:
            s = surface(label)
            a = TL.queue_audit(s["controls"], win_size=(s["rect"][2], s["rect"][3]), rect=s["rect"])
            self.assertTrue(a["balanced"], label)
            named = {TL._key(c) for c in s["controls"] if c["name"] and not TL.NOISE_NAMES.match(c["name"])}
            queued_keys = {TL._key(c) for c in a["queued"]}
            chrome_keys = {TL._key(c) for c in s["controls"] if TL._chrome.is_window_chrome(c["name"], "", None, None)}
            self.assertEqual(named - queued_keys - chrome_keys, set(), f"{label}: a named control was lost between Stage 2 and 3")

    def test_old_caps_are_gone(self):
        s = surface("Paint")
        q = TL.build_action_queue(s["controls"], (s["rect"][2], s["rect"][3]), s["rect"])
        self.assertGreater(len(q), 50)                 # the old queue held at most 1 + 4 + 3 = 8 steps
        wa = surface("WhatsApp")
        qa = TL.build_action_queue(wa["controls"])
        self.assertGreater(len(qa), 8)

    def test_edit_buttons_and_listitems_reach_the_queue(self):
        s = surface("WhatsApp")
        q = TL.build_action_queue(s["controls"])
        roles = {c["role"] for c in q}
        self.assertTrue({"Edit", "Button", "TabItem", "ListItem"} <= roles)       # ListItem was never queued before
        names = {c["name"] for c in q}
        self.assertIn("Status", names)

    def test_every_named_control_by_name_is_queued(self):
        for label in ("Calculator", "Paint", "WhatsApp"):
            s = surface(label)
            q = {c["name"] for c in TL.build_action_queue(s["controls"], (s["rect"][2], s["rect"][3]), s["rect"])}
            for c in s["controls"]:
                nm = c["name"]
                if nm and not TL.NOISE_NAMES.match(nm) and not TL._chrome.is_window_chrome(nm):
                    self.assertIn(nm, q, f"{label}: '{nm}' vanished between Stage 2 and 3")

    def test_chrome_and_duplicates_are_dropped_and_counted(self):
        ctrls = [{"role": "Button", "name": "Close", "bbox": [1500, 5, 1550, 40]}, {"role": "Button", "name": "Undo", "bbox": [100, 100, 140, 130]},
                 {"role": "Button", "name": "Undo", "bbox": [100, 100, 140, 130]}, {"role": "Button", "name": "Close", "bbox": [700, 500, 780, 530]},
                 {"role": "Button", "name": "", "bbox": [0, 0, 30, 30]}]
        a = TL.queue_audit(ctrls, win_size=(1600, 900), rect=(0, 0, 1600, 900))
        self.assertEqual([c["name"] for c in a["queued"]], ["Undo", "Close"])       # the app's own Close in a dialog stays; the caption Close goes
        self.assertEqual(a["dropped"], {"nameless": 1, "placeholder_name": 0, "window_chrome": 1, "duplicate": 1, "no_geometry": 0})
        self.assertTrue(a["balanced"])


class T5Explain(unittest.TestCase):
    def setUp(self):
        self.s = surface("WhatsApp")
        self.ctrls = self.s["controls"]
        self.ctrl = next(c for c in self.ctrls if c["name"] == "New chat")

    def test_vlm_sentence_is_used_and_cleaned(self):
        seen = {}

        def vlm(img, prompt):
            seen["prompt"] = prompt
            return "assistant\nOpens a blank conversation so you can message someone new. Extra words follow."
        r = TL.explain_control(self.ctrl, self.ctrls, vlm_fn=vlm, app_title="WhatsApp")
        self.assertEqual(r, {"text": "Opens a blank conversation so you can message someone new.", "source": "vlm"})
        self.assertIn("'New chat'", seen["prompt"])
        self.assertIn("Nearby controls", seen["prompt"])

    def test_static_template_is_never_emitted(self):
        for fn in (lambda i, p: "Here is the 'New chat' control for triggering commands in this view.", lambda i, p: "", lambda i, p: "ok", None):
            r = TL.explain_control(self.ctrl, self.ctrls, vlm_fn=fn)
            self.assertEqual(r["source"], "context_fallback")
            self.assertFalse(r["text"].lower().startswith("here is the"))
        for c in self.ctrls:
            t = TL.explain_control(c, self.ctrls, vlm_fn=None)["text"]
            self.assertNotIn("for triggering commands in this view", t)

    def test_model_errors_fall_back(self):
        def boom(i, p):
            raise RuntimeError("cpu oom")
        self.assertEqual(TL.explain_control(self.ctrl, self.ctrls, vlm_fn=boom)["source"], "context_fallback")

    def test_container_context_uses_enclosing_control(self):
        parent = {"role": "Pane", "name": "Calls panel", "bbox": [0, 0, 2000, 2000]}
        ctx = TL.container_context(self.ctrl, [parent] + self.ctrls)
        self.assertEqual(ctx["container"], "Calls panel")
        self.assertTrue(ctx["siblings"])
        self.assertNotIn("New chat", ctx["siblings"])
        self.assertIn("Calls panel", TL.build_explain_prompt(self.ctrl, ctx, "WhatsApp"))

    def test_cache_avoids_repeat_calls(self):
        n = []
        vlm = lambda i, p: (n.append(1), "Starts a new conversation with a contact.")[1]
        cache = {}
        TL.explain_control(self.ctrl, self.ctrls, vlm_fn=vlm, cache=cache)
        r = TL.explain_control(self.ctrl, self.ctrls, vlm_fn=vlm, cache=cache)
        self.assertEqual(len(n), 1)
        self.assertTrue(r.get("cached"))

    def test_long_answers_are_cut_to_one_sentence(self):
        s = TL.clean_sentence("Lets you pick the thickness of the brush stroke before you draw on the canvas, which is shown as a slider. Second sentence.")
        self.assertTrue(s.endswith(".") and s.count(".") == 1)


class T6Geometry(unittest.TestCase):
    def setUp(self):
        self.rect0 = (100, 100, 800, 600)
        self.ctrl = TL.normalise_controls([{"role": "Button", "name": "Undo", "bbox": [200, 150, 260, 190]}], self.rect0)[0]        # centre (230, 170) -> norm (0.1625, 0.1167)

    def test_window_moved(self):
        w = FakeWin((400, 300, 800, 600))
        r = TL.act_on_control(w, self.ctrl, "move", mouse=Rec())
        self.assertTrue(r["ok"])
        self.assertEqual(r["point"], [530, 370])               # followed the window by (+300, +200)

    def test_window_resized_scales_the_point(self):
        w = FakeWin((100, 100, 1600, 1200))
        r = TL.act_on_control(w, self.ctrl, "move", mouse=Rec())
        self.assertEqual(r["point"], [360, 240])               # 100 + 0.1625*1600, 100 + 0.1167*1200

    def test_rect_is_read_again_after_focus(self):
        w = FakeWin((100, 100, 800, 600))
        w.on_focus = lambda win: setattr(win, "l", 700)        # focusing restores / snaps the window elsewhere
        mouse = Rec()
        r = TL.act_on_control(w, self.ctrl, "click", mouse=mouse)
        self.assertEqual(r["rect"][0], 700)
        self.assertEqual(r["point"][0], 830)
        self.assertEqual(mouse.calls, [("move", (830, 170)), ("click", (830, 170))])

    def test_each_action_rereads_the_rectangle(self):
        w = FakeWin((100, 100, 800, 600))
        pts = []
        for shift in (0, 50, 300):
            w.l = 100 + shift
            pts.append(TL.act_on_control(w, self.ctrl, "move")["point"][0])
        self.assertEqual(pts, [230, 280, 530])

    def test_minimised_or_empty_window_is_refused(self):
        for w in (FakeWin((100, 100, 800, 600), minimized=True), FakeWin((-32000, -32000, 160, 28)), FakeWin((100, 100, 0, 0))):
            mouse = Rec()
            r = TL.act_on_control(w, self.ctrl, "click", mouse=mouse)
            self.assertFalse(r["ok"])
            self.assertEqual(mouse.calls, [])

    def test_point_outside_the_window_is_refused(self):
        far = dict(self.ctrl, norm={"cx": 1.4, "cy": 0.5, "w": 0.1, "h": 0.1})
        mouse = Rec()
        r = TL.act_on_control(FakeWin(self.rect0), far, "click", mouse=mouse)
        self.assertEqual(r["reason"], "point_outside_window")
        self.assertEqual(mouse.calls, [])

    def test_trap_click_and_credential_typing_refused(self):
        send = TL.normalise_controls([{"role": "Button", "name": "Send", "bbox": [200, 150, 260, 190]}], self.rect0)[0]
        mouse = Rec()
        self.assertEqual(TL.act_on_control(FakeWin(self.rect0), send, "click", archetype="chat_messenger", mouse=mouse)["reason"], "trap_control_refused")
        self.assertEqual(mouse.calls, [])
        pw = TL.normalise_controls([{"role": "Edit", "name": "Password", "bbox": [200, 150, 260, 190]}], self.rect0)[0]
        self.assertEqual(TL.act_on_control(FakeWin(self.rect0), pw, "type", "x", keyboard=mouse)["reason"], "credential_field_refused")

    def test_typing_clicks_then_types(self):
        edit = TL.normalise_controls([{"role": "Edit", "name": "Search", "bbox": [200, 150, 300, 190]}], self.rect0)[0]
        io = Rec()
        r = TL.act_on_control(FakeWin((150, 120, 800, 600)), edit, "type", "hello", mouse=io, keyboard=io)
        self.assertTrue(r["ok"])
        self.assertEqual([c[0] for c in io.calls], ["move", "click", "keys"])

    def test_every_trace_control_resolves_inside_a_shifted_window(self):
        for label in ("Calculator", "Paint", "WhatsApp"):
            s = surface(label)
            L, T, W, H = s["rect"]
            moved = (L + 37, T - 11, W, H)
            for c in s["controls"]:
                p = TL.resolve_point(c, moved)
                self.assertIsNotNone(p, f"{label}:{c['name']}")
                self.assertAlmostEqual(p[0] - 37, (c["bbox"][0] + c["bbox"][2]) / 2, delta=1)

    def test_dry_run_without_mouse(self):
        r = TL.act_on_control(FakeWin(self.rect0), self.ctrl, "move")
        self.assertEqual((r["ok"], r["reason"], r["drift_px"]), (True, "resolved_dry_run", 0.0))


class T7CrashFree(unittest.TestCase):
    BAD = [None, {}, [], "text", 7, {"elements": None}, {"elements": "x"}, {"elements": [None, 3, "a", {}, {"name": "x"}, {"name": "x", "coords": None}, {"name": "x", "coords": {"box": [1, 2]}},
                                                                                        {"name": None, "type": None, "coords": {"box": [0, 0, 10, 10]}},
                                                                                        {"name": "ä" * 5000, "type": "ButtonControl", "coords": {"box": [0, 0, 10, 10]}}]}]

    def test_malformed_traces(self):
        for bad in self.BAD:
            s = TL.controls_from_trace(bad)
            v = G.validate_scan(s["controls"], "Calculator")
            self.assertIn(v["status"], (G.COMPLETE, G.INCOMPLETE))
            TL.queue_audit(s["controls"])
            for c in s["controls"]:
                TL.explain_control(c, s["controls"], vlm_fn=None)
        for ctrls in ([None], [1, 2], [{"name": 5}], None):
            self.assertEqual(G.validate_scan(ctrls, "Paint")["status"] in (G.COMPLETE, G.INCOMPLETE), True)

    def test_bad_databases_return_a_result_not_an_exception(self):
        d = tempfile.mkdtemp(prefix="replay_bad_")
        try:
            v = G.validate_scan(load("Calculator")["elements"], "Calculator")
            garbage = os.path.join(d, "garbage.db")
            Path(garbage).write_bytes(b"this is not a sqlite file" * 100)
            for path in (garbage, d, os.path.join(d, "no_such_dir", "x.db")):
                r = G.record_scan(path, "calculator", "Calculator", v, "p", [])
                self.assertFalse(r["saved"])
                self.assertIn("error", r)
                self.assertIsNone(G.get_status(path, "calculator"))
                self.assertEqual(G.pending_rescans(path), [])
            # a database that has the FTS table but no side table / an older shape is healed, not crashed on
            old = os.path.join(d, "old.db")
            c = sqlite3.connect(old)
            c.execute("CREATE VIRTUAL TABLE causal_procedures_fts USING fts5(arch_id, domain, goal, steps_json, trap_guard, tokenize='porter unicode61')")
            c.commit()
            c.close()
            self.assertTrue(G.record_scan(old, "calculator", "Calculator", v, "p", [])["saved"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_full_tutor_pipeline_from_traces_into_a_temp_rag(self):
        import run_autonomous_app_tutor as T
        d = tempfile.mkdtemp(prefix="replay_pipe_")
        db = Path(d) / "rag.db"
        try:
            sqlite3.connect(str(db)).close()
            for label in ("Calculator", "Paint", "WhatsApp"):
                scan_fn = T.replay_scan_fn([str(TRACES[label])])
                surface_data, verdict, hist = G.recursive_scan(scan_fn, label, max_rescans=1)
                out = T.reverse_engineer_and_teach(label, surface_data, vlm_fn=None, actuate=False, speak_fn=lambda t: None, highlight_fn=lambda *a, **k: None, pause_sec=0.0)
                self.assertEqual(len(out["steps"]), len(TL.build_action_queue(surface_data["controls"], (surface_data["rect"][2], surface_data["rect"][3]), surface_data["rect"])))
                self.assertTrue(all(s["explanation_source"] == "context_fallback" and s["explanation"] for s in out["steps"]))
                self.assertTrue(out["queue_audit"]["balanced"])
                res = T.log_learned_workflow_to_rag(label, out["app_purpose"], out["steps"], verdict, db)
                self.assertTrue(res["saved"])
            self.assertEqual(G.get_status(str(db), "calculator")["status"], G.COMPLETE)
            self.assertEqual(G.get_status(str(db), "whatsapp")["status"], G.COMPLETE)
            self.assertEqual(G.get_status(str(db), "paint")["status"], G.INCOMPLETE)
            self.assertEqual(G.pending_rescans(str(db)), ["paint"])
            c = sqlite3.connect(str(db))
            steps = json.loads(c.execute("SELECT steps_json FROM causal_procedures_fts WHERE causal_procedures_fts MATCH 'Calculator'").fetchone()[0])
            c.close()
            self.assertTrue(steps and "norm" in steps[0] and steps[0]["explanation_source"] == "context_fallback")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_live_run_is_refused_without_the_flag(self):
        import run_autonomous_app_tutor as T
        self.assertEqual(os.environ.get("HOJAIGA_ALLOW_LIVE"), "0")
        old = sys.argv
        sys.argv = ["x", "Calculator"]
        try:
            T.main()                                          # must print REFUSED and return, never touch a window
        finally:
            sys.argv = old

    def test_real_federated_rag_self_heals_under_replayed_outcomes(self):
        from core_organs.rag import embed as E, storage as ST
        from core_organs.rag.router import Rag
        from core_organs.rag.types import Outcome, PlanStep, Query
        d = tempfile.mkdtemp(prefix="replay_rag_")
        R = Rag(ST.Storage(d, E.HashEmbedder()), icons=False)
        try:
            for label in ("Calculator", "Paint", "WhatsApp"):
                key = label.lower()
                s = surface(label)
                nodes = [{"ctype": c["role"], "name": c["name"]} for c in s["controls"][:80]]
                R.fast.upsert([{"app_key": key, "kind": "hotkey", "command_id": f"{key}:undo", "task_pattern": "undo the last action", "payload": "ctrl+z", "trust": "learned"}])
                before = R.retrieve(Query(text="undo the last action", app_key=key, snapshot=nodes, mode="tutor"))
                step = PlanStep(command_id=f"{key}:undo", route="hotkey", args={"payload": "ctrl+z"})
                for i in range(4):                                                   # the shortcut stops working: the RAG must learn that and keep answering
                    R.observe(Outcome(run_id=f"r{i}", app_key=key, step=step, ok=False, effect="no_effect", failure_code="no_effect"))
                after = R.retrieve(Query(text="undo the last action", app_key=key, snapshot=nodes, mode="tutor"))
                self.assertIsNotNone(before)
                self.assertIsNotNone(after)
                healed = R.rec.lookup(key, failure_code="no_effect")
                self.assertTrue(healed, "the seeded no_effect playbook must be retrievable for every replayed app")
                R.retrieve(Query(text="what does this do", app_key=key, snapshot=[], mode="tutor"))      # empty screen: degrade, do not raise
                R.retrieve(Query(text="", app_key=key, snapshot=None, mode="auto"))
                R.retrieve(Query(text="undo", app_key="never_scanned_app", snapshot=nodes, mode="auto"))
        finally:
            R.close()
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"\nOFFLINE REPLAY: {res.testsRun - len(res.failures) - len(res.errors)}/{res.testsRun} passed, {len(res.failures)} failed, {len(res.errors)} errors")
    sys.exit(0 if res.wasSuccessful() else 1)
