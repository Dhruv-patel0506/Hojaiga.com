"""
si_tests_agent -- Checkpoint 5: the closed loop (agent_executor). EX = the executor loop, TU = the tutor (advise). Everything offline: the screen, the model and the hands are fakes; the RAG is a real
Rag over a temp store, so "the graph learns an edge after a verified step" is checked against the real graph tables.

  EX1  the full loop on a real RAG: query RAG -> scan (Set-of-Marks) -> the adapter's action -> safety guard -> act -> verify -> the topology graph learns src -(command)-> dst
  EX2  the guard: a destructive goal, a destructive / financial target name, a closing chord, an unknown target, an invalid answer -> nothing is executed and nothing is learned; an unnamed icon is judged by its goal
  EX3  a verified RAG hotkey beats the model (the model is not even asked); a probe or an unreliable one does not
  EX4  a step that did not change the screen is 'no_effect', is reported to the graph as a failure, and stops a run
  EX5  an answer that is not an action, an actor that did not deliver: reported, not learned
  EX6  the adapter's prompt is the TRAINING prompt, byte for byte, and its reply parser
  EX7  state transitions: the same labels = the same state; a different screen = a new state and a distinct edge; a repeat of the step credits the same edge
  EX8  cold start: universal_scan runs only for an app nothing is known about, and only when asked
  EX9  the live click-accuracy evaluator (UIA ground truth, seen vs unseen controls, baselines)
  EX10 goal-aware verification (toggle flips / the right dialog / no unexpected dialog / the named control)
  EX11 the UIA-name assist for dense icon strips
  EX12 wrong click -> failed, undone, retried without the wrong target; the graph hears both
  EX13 unrestorable stops; no_effect is never rolled back; the assist makes attempt 1 right
  EX14 latency: the post-step screen is the next step's start
  EX15 short generation that stops at the expectation
  TU1  advise(): says what to do, where (the box), a keyboard alternative from the RAG -- and does nothing and learns nothing
  TU2  advise() refuses what the guard refuses, in words
"""
from __future__ import annotations

import json
import os
import sys
import time

for _p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except Exception:                                        # pragma: no cover
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore

APP = "padx"
MENU_LABELS = ["File", "Edit", "View", "Help", "Format", "Window"]
DIALOG_LABELS = ["Save As", "File name", "Cancel", "Save", "Browse Folders"]


def _som(labels, extra=None):
    els = [{"id": i + 1, "label": lab, "role": "button", "box": [10 + 90 * i, 10, 80, 24], "conf": 0.9, "sources": ["fake"]} for i, lab in enumerate(labels)]
    els += extra or []
    return {"elements": els, "seconds": 0.0, "size": [800, 400], "tiers_used": [], "tiers_skipped": []}


def _image(shade: int, boxes: int = 0):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (400, 200), (shade, shade, shade))
    d = ImageDraw.Draw(im)
    for i in range(boxes):
        d.rectangle([10 + 30 * i, 60, 30 + 30 * i, 120], fill=(255 - shade, 20, 20))
    return im


class Screen:
    """A scripted application: observe() returns the current frame; act() moves to the next one when the action is the expected 'effective' one."""

    def __init__(self, frames, effective=True, deliver=True):
        self.frames, self.i, self.effective, self.deliver, self.acted = frames, 0, effective, deliver, []

    def observe(self):
        f = self.frames[self.i]
        return {"image": f["image"], "som": f["som"]}

    def act(self, action, som):
        self.acted.append(action)
        if not self.deliver:
            return False, "not delivered"
        if self.effective and self.i < len(self.frames) - 1:
            self.i += 1
        return True, "ok"


def _frames():
    return [{"image": _image(40, 0), "som": _som(MENU_LABELS)}, {"image": _image(200, 4), "som": _som(DIALOG_LABELS)}]


class Ground:
    def __init__(self, action):
        self.action, self.calls = action, 0

    def __call__(self, image, som, app_key, goal):
        self.calls += 1
        return self.action, json.dumps([self.action]) if self.action else "no idea"


CLICK_FILE = {"step": 1, "action": "click", "target_id": 1, "hotkey": None, "text": None, "verify_expectation": "a dialog opens"}


def run_ex1() -> "TestOutcome":
    """EX1: the full loop on a real RAG -- retrieve, Set-of-Marks, the adapter's action, guard, act, verify, and the graph learns the edge"""
    from si_tests_rag import _Env
    from core_organs import agent_executor as AE
    with _Env() as R:
        scr = Screen(_frames())
        ground = Ground(CLICK_FILE)
        before = R.graph.stats(APP)
        ag = AE.Agent(APP, scr.observe, ground, scr.act, rag=R, settle_s=0, sleep=lambda s: None)
        rec = ag.step("Click the File menu")
        after = R.graph.stats(APP)
        v = R.graph.view(APP)
        edges = [e for es in v["by_cmd"].values() for e in es]
        obs = R.graph.db.rows("SELECT ok, effect, command_id, route FROM observations WHERE app_key=?", (APP,))
    checks = {"the_model_was_asked_once_with_the_scanned_screen": ground.calls == 1 and rec.source == "model",
              "the_guard_passed_and_the_actor_clicked_the_target": rec.status == "done" and scr.acted == [CLICK_FILE],
              "verified_by_the_screen_changing": rec.effect.startswith("new on screen") and "Save As" in rec.effect,
              "the_two_screens_are_two_different_states": bool(rec.src_state) and bool(rec.dst_state) and rec.src_state != rec.dst_state,
              "the_graph_learned_one_edge_between_them": before["edges"] == 0 and after["edges"] == 1 and len(edges) == 1 and edges[0]["src"] == rec.src_state and edges[0]["dst"] == rec.dst_state,
              "the_observation_is_logged_as_a_success_by_control_click": len(obs) == 1 and obs[0]["ok"] == 1 and obs[0]["route"] == "control_click",
              "the_record_says_it_learned": rec.learned is True}
    return _verdict(checks, f"status={rec.status} effect={rec.effect!r} edges={after['edges']} src={str(rec.src_state)[:8]} dst={str(rec.dst_state)[:8]}")


def run_ex2() -> "TestOutcome":
    """EX2: the guard -- unsafe goals / targets / chords, an unknown target and an invalid answer execute nothing and learn nothing; an unnamed icon is judged by its goal"""
    from si_tests_rag import _Env
    from core_organs import agent_executor as AE
    cases = {}
    with _Env() as R:
        def attempt(goal, action, labels=MENU_LABELS, extra=None):
            frames = [{"image": _image(40), "som": _som(labels, extra)}, {"image": _image(200, 4), "som": _som(DIALOG_LABELS)}]
            scr = Screen(frames)
            ag = AE.Agent(APP, scr.observe, Ground(action), scr.act, rag=R, settle_s=0, sleep=lambda s: None)
            rec = ag.step(goal)
            return rec, scr
        cases["destructive_goal"] = attempt("Delete all my files", CLICK_FILE)
        cases["financial_target"] = attempt("Click the button", CLICK_FILE, ["Buy now", "Edit"])
        cases["format_target"] = attempt("Click the button", CLICK_FILE, ["Format disk", "Edit"])
        cases["closing_chord"] = attempt("Open the menu", {"step": 1, "action": "hotkey", "hotkey": "Alt+F4", "target_id": None, "text": None})
        cases["unknown_target"] = attempt("Click the File menu", dict(CLICK_FILE, target_id=99))
        cases["no_answer"] = attempt("Click the File menu", None)
        cases["unnamed_icon_safe_goal"] = attempt("Click the Memory add button", CLICK_FILE, [""], [])
        cases["unnamed_icon_unsafe_goal"] = attempt("Click the Uninstall button", CLICK_FILE, [""], [])
        edges = R.graph.stats(APP)["edges"]
    blocked = ["destructive_goal", "financial_target", "format_target", "closing_chord", "unknown_target", "unnamed_icon_unsafe_goal"]
    checks = {"nothing_unsafe_is_acted_on": all(cases[k][1].acted == [] for k in blocked + ["no_answer"]),
              "each_is_reported_as_blocked_with_a_reason": all(cases[k][0].status == "blocked" and cases[k][0].why for k in blocked),
              "no_answer_is_no_action": cases["no_answer"][0].status == "no_action",
              "an_unnamed_icon_asked_for_by_a_safe_goal_is_clicked": cases["unnamed_icon_safe_goal"][0].status == "done" and len(cases["unnamed_icon_safe_goal"][1].acted) == 1,
              "only_the_safe_step_taught_the_graph": edges == 1,
              "the_reasons_name_the_category": "destructive" in cases["destructive_goal"][0].why and "financial" in cases["financial_target"][0].why and "chord" in cases["closing_chord"][0].why}
    return _verdict(checks, "; ".join(f"{k}={cases[k][0].status}" for k in cases))


class _FakeRag:
    """Stands in for the RAG: a canned retrieval, and a record of what the loop learned."""

    def __init__(self, plan_step=None):
        from core_organs.rag import Plan, Retrieval, Query
        self.plan_step, self.outcomes, self._ret = plan_step, [], None
        self.Plan, self.Retrieval, self.Query = Plan, Retrieval, Query

        class _Lex:
            def add_command(s, *a, **k):
                return "c"
        self.lex = _Lex()

    def retrieve(self, q):
        plans = [self.Plan(steps=[self.plan_step], p_success=0.9)] if self.plan_step else []
        return self.Retrieval(query=q, plans=plans)

    def localize(self, app, snap):
        class L:
            state_id = "S" + str(abs(hash(tuple(snap["ocr"]))) % 10 ** 6)
        return L()

    def observe(self, o):
        self.outcomes.append(o)
        return {}


def run_ex3() -> "TestOutcome":
    """EX3: a verified, reliable RAG hotkey beats the model; a probe or an unreliable one does not"""
    from core_organs.rag import PlanStep
    from core_organs import agent_executor as AE

    def go(step):
        scr = Screen(_frames())
        ground = Ground(CLICK_FILE)
        rag = _FakeRag(step)
        rec = AE.Agent(APP, scr.observe, ground, scr.act, rag=rag, settle_s=0, sleep=lambda s: None).step("Open the file menu")
        return rec, ground, scr, rag
    good = PlanStep("padx:file", "hotkey", {"keys": "Alt+F"}, None, "menu opens", 0.95, "allow", [], False)
    probe = PlanStep("padx:file", "hotkey", {"keys": "alt+f"}, None, "", 0.95, "allow", [], True)
    weak = PlanStep("padx:file", "hotkey", {"keys": "alt+f"}, None, "", 0.5, "allow", [], False)
    unsafe = PlanStep("padx:file", "hotkey", {"keys": "alt+f"}, None, "", 0.95, "destructive", [], False)
    r_good, g_good, s_good, rag_good = go(good)
    r_probe, g_probe, *_ = go(probe)
    r_weak, g_weak, *_ = go(weak)
    r_unsafe, g_unsafe, *_ = go(unsafe)
    checks = {"the_verified_shortcut_is_used_and_the_model_is_not_asked": r_good.source == "rag" and g_good.calls == 0 and s_good.acted[0]["hotkey"] == "alt+f",
              "its_result_is_learned_as_a_hotkey_route": len(rag_good.outcomes) == 1 and rag_good.outcomes[0].step.route == "hotkey" and rag_good.outcomes[0].step.args["keys"] == "alt+f",
              "a_probe_is_not_trusted": r_probe.source == "model" and g_probe.calls == 1,
              "an_unreliable_shortcut_is_not_trusted": r_weak.source == "model" and g_weak.calls == 1,
              "a_flagged_shortcut_is_not_used": r_unsafe.source == "model" and g_unsafe.calls == 1}
    return _verdict(checks, f"sources: good={r_good.source} probe={r_probe.source} weak={r_weak.source} unsafe={r_unsafe.source}")


def run_ex4() -> "TestOutcome":
    """EX4: nothing changed on screen -> no_effect, reported to the graph as a failure, and the run stops"""
    from si_tests_rag import _Env
    from core_organs import agent_executor as AE
    with _Env() as R:
        scr = Screen(_frames(), effective=False)
        ag = AE.Agent(APP, scr.observe, Ground(CLICK_FILE), scr.act, rag=R, settle_s=0, sleep=lambda s: None)
        recs = ag.run(["Click the File menu", "Click the Edit menu"])
        obs = R.graph.db.rows("SELECT ok, effect FROM observations WHERE app_key=?", (APP,))
        edge = R.graph.db.rows("SELECT n_ok, n_fail, n_noeffect FROM edges WHERE app_key=?", (APP,))
    checks = {"the_step_is_no_effect": recs[0].status == "no_effect" and recs[0].effect == "no_effect",
              "the_run_stops_after_a_failed_step": len(recs) == 1 and len(scr.acted) == 1,
              "the_graph_hears_about_the_failure": len(obs) == 1 and obs[0]["ok"] == 0 and obs[0]["effect"] == "no_effect",
              "the_edge_is_credited_as_no_effect_not_as_a_success": len(edge) == 1 and edge[0]["n_ok"] == 0 and edge[0]["n_noeffect"] == 1}
    return _verdict(checks, f"status={recs[0].status} observations={len(obs)} edge={edge}")


def run_ex5() -> "TestOutcome":
    """EX5: a reply that is not an action, and an actor that did not deliver -- reported, not learned"""
    from core_organs import agent_executor as AE
    rag1, rag2 = _FakeRag(), _FakeRag()
    scr1 = Screen(_frames())
    r1 = AE.Agent(APP, scr1.observe, Ground(None), scr1.act, rag=rag1, settle_s=0, sleep=lambda s: None).step("Click the File menu")
    scr2 = Screen(_frames(), deliver=False)
    r2 = AE.Agent(APP, scr2.observe, Ground(CLICK_FILE), scr2.act, rag=rag2, settle_s=0, sleep=lambda s: None).step("Click the File menu")
    scr3 = Screen(_frames())
    r3 = AE.Agent(APP, scr3.observe, Ground(CLICK_FILE), None, rag=_FakeRag(), settle_s=0, sleep=lambda s: None).step("Click the File menu")
    checks = {"no_action_is_reported_and_unlearned": r1.status == "no_action" and scr1.acted == [] and rag1.outcomes == [],
              "an_undelivered_action_is_reported_and_unlearned": r2.status == "not_delivered" and r2.why == "not delivered" and rag2.outcomes == [] and r2.learned is False,
              "without_an_actor_the_step_is_only_advised": r3.status == "advised"}
    return _verdict(checks, f"{r1.status} / {r2.status} / {r3.status}")


def run_ex6() -> "TestOutcome":
    """EX6: the adapter's prompt is the training prompt, byte for byte, and its replies parse the way the evaluation parses them"""
    import tempfile
    from PIL import Image
    from core_organs import agent_executor as AE, train_qlora as TQ
    from core_organs.harvest import video_explain as VE
    som = _som(["File", "Edit"])
    pair = VE.build_row(tempfile.gettempdir(), "padx", "v1", {"t": 0.0, "pre": "x.jpg", "bbox": None}, som, "Click the File menu", [CLICK_FILE], "pid", True, True)
    msgs = AE.AdapterGrounder.build_messages("IMG", som, "padx", "Click the File menu")
    train_texts = [[c["text"] for c in m["content"] if c["type"] == "text"] for m in pair["messages"][:2]]
    live_texts = [[c["text"] for c in m["content"] if c["type"] == "text"] for m in msgs]
    g = AE.AdapterGrounder("no/such/adapter")
    reply = '```json\n[{"step": 1, "action": "click", "target_id": 2, "hotkey": null, "text": null, "verify_expectation": "x"}]\n```'
    checks = {"system_and_user_text_equal_the_training_record": live_texts == train_texts,
              "roles_and_the_image_slot_match": [m["role"] for m in msgs] == ["system", "user"] and msgs[1]["content"][0] == {"type": "image", "image": "IMG"},
              "a_fenced_reply_parses_to_the_action": TQ.parse_action(reply)["target_id"] == 2,
              "the_model_is_not_loaded_until_asked": g._model is None}
    return _verdict(checks, f"user text={live_texts[1][0][:60]!r}")


def run_ex7() -> "TestOutcome":
    """EX7: state transitions -- the same screen is the same state, a different screen is a new state with its own edge, and repeating a step credits the same edge"""
    from si_tests_rag import _Env
    from core_organs import agent_executor as AE
    with _Env() as R:
        frames = [{"image": _image(40), "som": _som(MENU_LABELS)}, {"image": _image(200, 4), "som": _som(DIALOG_LABELS)}]
        s_same = AE.som_to_snapshot(frames[0]["som"])
        a = R.localize(APP, s_same).state_id
        b = R.localize(APP, AE.som_to_snapshot(_som(MENU_LABELS))).state_id
        c = R.localize(APP, AE.som_to_snapshot(frames[1]["som"])).state_id
        for _ in range(2):                                     # the same step twice from the same screen
            scr = Screen([dict(frames[0]), dict(frames[1])])
            AE.Agent(APP, scr.observe, Ground(CLICK_FILE), scr.act, rag=R, settle_s=0, sleep=lambda s: None).step("Click the File menu")
        edge = R.graph.db.rows("SELECT n_ok, src, dst FROM edges WHERE app_key=?", (APP,))
    checks = {"identical_screens_are_one_state": a == b,
              "a_different_screen_is_another_state": a != c,
              "the_repeat_credits_one_edge_not_two": len(edge) == 1 and edge[0]["n_ok"] == 2 and edge[0]["src"] == a and edge[0]["dst"] == c}
    return _verdict(checks, f"edge={edge}")


def run_ex8() -> "TestOutcome":
    """EX8: universal_scan is the cold start -- only for an app nothing is known about, only when called"""
    from si_tests_rag import _Env
    from core_organs import agent_executor as AE
    scans = []
    with _Env() as R:
        scr = Screen(_frames())
        ag = AE.Agent(APP, scr.observe, Ground(CLICK_FILE), scr.act, rag=R, settle_s=0, sleep=lambda s: None)
        ag.step("Click the File menu")
        n_before = len(scans)
        unknown = AE.Agent("brandnewapp", scr.observe, Ground(CLICK_FILE), scr.act, rag=R, settle_s=0, sleep=lambda s: None).ensure_known("brandnew", scan=lambda t: scans.append(t) or {"ok": 1})
        known = ag.ensure_known("padx", scan=lambda t: scans.append(t) or {"ok": 1})
    checks = {"stepping_never_runs_a_whole_app_scan": n_before == 0,
              "an_unknown_app_is_scanned_once_when_asked": unknown["scanned"] is True and scans == ["brandnew"],
              "an_app_with_learned_states_is_not_rescanned": known["scanned"] is False and scans == ["brandnew"]}
    return _verdict(checks, f"unknown={unknown} known={known}")


def run_tu1() -> "TestOutcome":
    """TU1: advise() -- what to do, where, a keyboard alternative from the RAG; nothing is clicked and nothing is learned"""
    from si_tests_rag import _Env
    from core_organs import agent_executor as AE
    from core_organs.rag import Evidence
    with _Env() as R:
        scr = Screen(_frames())
        ag = AE.Agent(APP, scr.observe, Ground(CLICK_FILE), scr.act, rag=R, settle_s=0, sleep=lambda s: None)
        real_retrieve = R.retrieve

        def retrieve(q):
            ret = real_retrieve(q)
            ret.evidence = [Evidence("fast", APP, "hotkey", "Open the File menu with Alt+F", safety="allow"), Evidence("fast", APP, "hotkey", "Delete the file with Delete", safety="destructive")]
            return ret
        R.retrieve = retrieve
        adv = ag.advise("Click the File menu")
        edges = R.graph.stats(APP)["edges"]
        obs = R.graph.stats(APP)["observations"]
    checks = {"says_what_to_click": adv["say"].startswith("Click File") and adv["allowed"] is True,
              "points_at_it": adv["point"] == [10, 10, 80, 24],
              "offers_the_safe_keyboard_alternative_only": adv["alternatives"] == ["Open the File menu with Alt+F"] and "Alt+F" in adv["say"],
              "nothing_was_clicked": scr.acted == [],
              "nothing_was_learned": edges == 0 and obs == 0,
              "the_action_is_returned_for_the_caller": adv["action"] == CLICK_FILE and adv["source"] == "model"}
    return _verdict(checks, f"say={adv['say']!r} point={adv['point']}")


def run_tu2() -> "TestOutcome":
    """TU2: advise() refuses what the guard refuses, in words, and offers no action"""
    from core_organs import agent_executor as AE
    scr = Screen([{"image": _image(40), "som": _som(["Buy now", "Edit"])}, {"image": _image(200), "som": _som(DIALOG_LABELS)}])
    adv = AE.Agent(APP, scr.observe, Ground(CLICK_FILE), scr.act, rag=None, settle_s=0, sleep=lambda s: None).advise("Click the Buy button")
    scr2 = Screen(_frames())
    adv2 = AE.Agent(APP, scr2.observe, Ground(None), scr2.act, rag=None).advise("Click the File menu")
    checks = {"it_says_it_will_not_and_why": adv["say"].startswith("I won't do that") and "financial" in adv["say"] and adv["allowed"] is False,
              "no_action_and_no_pointer_is_offered": adv["action"] is None and adv["point"] is None,
              "a_model_with_no_answer_is_refused_too": adv2["allowed"] is False and "no valid action" in adv2["say"]}
    return _verdict(checks, f"say={adv['say']!r} / {adv2['say']!r}")


class _EvalApp:
    """A parked app with four controls; two are named in the 'training set'."""

    def __init__(self):
        self.boxes = {"Alpha": (10, 10, 100, 40), "Beta": (120, 10, 100, 40), "Gamma": (230, 10, 100, 40), "Delete": (340, 10, 100, 40), "Close": (450, 10, 60, 40)}

    def grab(self, popups=False, stable=True):
        return _image(60, 2), (0, 0)

    def controls(self, origin, size):
        return [{"key": f"ButtonControl|{n}", "name": n, "type": "ButtonControl", "box": b, "ctl": None, "popup": False} for n, b in self.boxes.items()]


def run_ex9() -> "TestOutcome":
    """EX9: the live click-accuracy evaluator -- UIA ground truth, seen vs unseen controls, unsafe controls never asked, honest baselines"""
    import tempfile
    from core_organs import live_eval as LE
    app = _EvalApp()
    som = {"elements": [{"id": i + 1, "label": n, "role": "button", "box": [b[0] + 30, b[1] + 15, 30, 10]} for i, (n, b) in enumerate(app.boxes.items())] + [{"id": 9, "label": "", "role": "button", "box": [700, 300, 20, 20]}],
           "seconds": 0.0, "size": [800, 400], "tiers_used": [], "tiers_skipped": []}
    asked = []

    def ground(image, s, app_key, goal):
        asked.append(goal)
        right = {"Click the Alpha button": 1, "Click the Beta button": 2}.get(goal)           # right on the two 'seen' controls, wrong (the unnamed icon) on Gamma
        return {"action": "click", "target_id": right if right else 9}, "reply"
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "train.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"meta": {"source": "local_uia", "app_key": "evalapp", "uia_name": "Alpha"}}) + "\n")
            f.write(json.dumps({"meta": {"source": "local_uia", "app_key": "evalapp", "uia_name": "Beta"}}) + "\n")
            f.write(json.dumps({"meta": {"source": "video", "app_key": "evalapp", "uia_name": "Gamma"}}) + "\n")                 # not a local pair: does not count as seen
        names = LE.trained_control_names(d)
    res = LE.click_accuracy(app, "evalapp", ground, names["evalapp"], lambda img: som, max_controls=10)
    sm = res["summary"]
    checks = {"seen_means_in_the_training_split_of_local_pairs_only": names == {"evalapp": {"Alpha", "Beta"}},
              "only_safe_controls_are_asked": asked == ["Click the Alpha button", "Click the Beta button", "Click the Gamma button"],
              "the_answer_is_the_element_inside_the_control": [r["gt"] for r in res["rows"]] == [1, 2, 3],
              "seen_and_unseen_are_scored_apart": {k: sm["seen"][k] for k in ("n", "exact", "lexical_baseline", "valid")} == {"n": 2, "exact": 1.0, "lexical_baseline": 1.0, "valid": 1.0} and sm["unseen"]["n"] == 1 and sm["unseen"]["exact"] == 0.0 and sm["unseen"]["assisted_exact"] == 1.0,
              "the_lexical_baseline_is_independent_of_the_model": sm["all"]["lexical_baseline"] == 1.0 and sm["all"]["exact"] == round(2 / 3, 3),
              "chance_is_one_over_the_elements": abs(sm["all"]["chance"] - 1 / 6) < 0.001}
    return _verdict(checks, f"summary={sm}")


# ---------------------------------------------------------------------------------------------------- goal-aware verification, rollback, assist, latency
TOOLBAR = ["Bold (Ctrl+B)", "Italic (Ctrl+I)", "Strikethrough (Ctrl+Shift+X)", "Link (Ctrl+K)"]


def _ctl(name, i, toggle=0):
    return {"name": name, "type": "ButtonControl", "box": (10 + 50 * i, 10, 40, 40), "toggle": toggle}


def _toolbar_obs(toggles=(0, 0, 0, 0), shade=40):
    """The toolbar screen: four toggle buttons, each with one unnamed icon element inside its rectangle (ids 1-4)."""
    som = {"elements": [{"id": i + 1, "label": "", "role": "button", "box": [20 + 50 * i, 20, 20, 20]} for i in range(4)], "seconds": 0.0, "size": [400, 200], "tiers_used": [], "tiers_skipped": []}
    return {"image": _image(shade, 0), "som": som, "controls": [_ctl(n, i, toggles[i]) for i, n in enumerate(TOOLBAR)]}


def _dialog_obs():
    names = ["Display text", "Address", "Insert", "Cancel"]
    som = {"elements": [{"id": i + 1, "label": n, "role": "button", "box": [20 + 90 * i, 120, 80, 24]} for i, n in enumerate(names)], "seconds": 0.0, "size": [400, 200], "tiers_used": [], "tiers_skipped": []}
    return {"image": _image(200, 4), "som": som, "controls": [{"name": n, "type": "ButtonControl", "box": (10 + 90 * i, 110, 80, 40), "toggle": None} for i, n in enumerate(names)]}


def run_ex10() -> "TestOutcome":
    """EX10: goal-aware verification -- a toggle must flip, a dialog opener must open the RIGHT dialog, a plain control must not open one, the operated control must carry the goal's name"""
    from core_organs import agent_verify as AV
    pre = _toolbar_obs()
    click = lambda i: {"action": "click", "target_id": i}
    strike_ok = AV.goal_verify("Click the Strikethrough button", click(3), pre, _toolbar_obs((0, 0, 1, 0), 60), True, "the screen changed")
    strike_same = AV.goal_verify("Click the Strikethrough button", click(3), pre, _toolbar_obs((0, 0, 0, 0), 60), True, "the screen changed")
    link_for_strike = AV.goal_verify("Click the Strikethrough button", click(4), pre, _dialog_obs(), True, "new on screen")
    bold_opens_dialog = AV.goal_verify("Click the Bold button", click(1), pre, _dialog_obs(), True, "new on screen")
    link_ok = AV.goal_verify("Click the Link button", click(4), pre, _dialog_obs(), True, "new on screen")
    para_link = AV.goal_verify("insert a hyperlink", click(4), pre, _dialog_obs(), True, "new on screen")
    para_wrong = AV.goal_verify("make the text italic", click(4), pre, _dialog_obs(), True, "new on screen")
    no_dialog = AV.goal_verify("Click the Link button", click(4), pre, _toolbar_obs((0, 0, 0, 1), 60), True, "the screen changed")
    unchanged = AV.goal_verify("Click the Bold button", click(1), pre, pre, False, "no_effect")
    no_uia = AV.goal_verify("Click the Strikethrough button", click(4), {"som": pre["som"]}, {"som": _dialog_obs()["som"]}, True, "the screen changed")
    plain_pre = _toolbar_obs()
    plain_pre["controls"][0]["toggle"] = None
    plain_dialog = AV.goal_verify("Click the Bold button", click(1), plain_pre, _dialog_obs(), True, "new on screen")
    over = _toolbar_obs((0, 0, 0, 0), 90)
    over["controls"] = over["controls"] + _dialog_obs()["controls"]                  # a XAML dialog: the toolbar is still listed behind it
    quiet = _toolbar_obs((0, 0, 0, 0), 90)
    quiet["controls"] = quiet["controls"] + [{"name": "Tip A", "type": "ButtonControl", "box": (300, 10, 40, 40), "toggle": None}, {"name": "Tip B", "type": "ButtonControl", "box": (350, 10, 40, 40), "toggle": None}]
    link_xaml = AV.goal_verify("Click the Link button", click(4), pre, over, True, "new on screen")
    bold_xaml = AV.goal_verify("Click the Bold button", click(1), pre, over, True, "new on screen")
    new_but_no_dismiss = AV.modal_change(pre, quiet)
    lone = _toolbar_obs((0, 0, 0, 0), 90)
    lone["controls"] = lone["controls"] + [{"name": "Cancel", "type": "ButtonControl", "box": (300, 110, 80, 40), "toggle": None}]
    lone_ok = AV.goal_verify("Click the Link button", click(4), pre, lone, True, "new on screen")
    only_insert = _toolbar_obs((0, 0, 0, 0), 90)
    only_insert["controls"] = only_insert["controls"] + [{"name": "Insert", "type": "ButtonControl", "box": (300, 110, 80, 40), "toggle": None}]
    checks = {"a_lone_new_cancel_button_is_a_dialog": lone_ok["worked"] and AV.modal_change(pre, lone)["modal"] is True and AV.modal_change(pre, only_insert)["modal"] is False,
              "a_dialog_over_a_still_listed_toolbar_is_detected_by_its_dismissal_button": link_xaml["worked"] and bold_xaml["reason"] == "unexpected_dialog" and AV.modal_change(pre, over)["dismiss"] == ["cancel", "insert"],
              "new_controls_without_a_dismissal_button_and_nothing_lost_are_not_a_modal": new_but_no_dismiss["modal"] is False,
              "a_toggle_that_flipped_is_verified": strike_ok["worked"] and strike_ok["intent"] == "toggle",
              "a_toggle_that_did_not_flip_fails": not strike_same["worked"] and strike_same["reason"] == "toggle_unchanged",
              "the_wrong_control_fails_even_though_the_screen_changed": not link_for_strike["worked"] and link_for_strike["reason"] == "wrong_control" and "Link" in link_for_strike["effect"],
              "a_toggle_that_opens_a_dialog_fails": not bold_opens_dialog["worked"] and bold_opens_dialog["reason"] == "unexpected_dialog",
              "a_dialog_opener_opening_its_dialog_is_verified": link_ok["worked"] and link_ok["intent"] == "dialog",
              "a_paraphrased_goal_names_no_control_so_the_name_rule_is_skipped": para_link["worked"] and para_wrong["worked"] is True or para_wrong["reason"] in ("", "unexpected_dialog"),
              "a_dialog_opener_that_opened_nothing_fails": not no_dialog["worked"] and no_dialog["reason"] == "no_dialog",
              "nothing_changed_is_no_effect": not unchanged["worked"] and unchanged["reason"] == "no_effect",
              "without_a_uia_tree_only_the_screen_change_is_checked": no_uia["worked"] and no_uia["checked"] == "screen",
              "a_plain_control_that_opens_a_dialog_fails": not plain_dialog["worked"] and plain_dialog["reason"] == "unexpected_dialog",
              "the_name_rule_reads_the_goal_and_ignores_shortcut_hints": AV.explicit_name("Click the Bold (Ctrl+B) button") == "Bold" and AV.explicit_name("Click the Cancel button") == "Cancel" and AV.explicit_name("insert a hyperlink") == ""}
    return _verdict(checks, f"strike_ok={strike_ok['reason']!r} wrong={link_for_strike['effect']!r} para_wrong={para_wrong['reason']!r}")


def run_ex11() -> "TestOutcome":
    """EX11: the UIA-name assist -- the model's neighbouring icon is replaced by the one control that carries the goal's name; left alone when right, ambiguous, or without UIA"""
    from core_organs import agent_verify as AV
    from core_organs.harvest.local_recorder import element_at
    pre = _toolbar_obs()
    fix = lambda goal, tid, p=pre: AV.uia_assist(goal, {"action": "click", "target_id": tid}, p, element_at)
    a_wrong, note = fix("Click the Italic button", 1)
    a_right, _ = fix("Click the Italic button", 2)
    a_para, _ = fix("make it italic", 1)
    dup = _toolbar_obs()
    dup["controls"].append(dict(dup["controls"][0], name="Italic (alt)", box=(300, 10, 40, 40)))
    a_dup, _ = fix("Click the Italic button", 1, dup)
    a_none, _ = fix("Click the Italic button", 1, {"som": pre["som"]})
    a_hot, _ = AV.uia_assist("Click the Italic button", {"action": "hotkey", "hotkey": "ctrl+i"}, pre, element_at)
    checks = {"the_neighbour_is_replaced_by_the_named_control": a_wrong is not None and a_wrong["target_id"] == 2 and "Bold" in note and "Italic" in note,
              "a_right_pick_is_left_alone": a_right is None,
              "a_paraphrased_goal_is_left_alone": a_para is None,
              "an_ambiguous_name_is_left_alone": a_dup is None,
              "no_uia_tree_means_no_assist": a_none is None,
              "only_clicks_are_corrected": a_hot is None}
    return _verdict(checks, f"note={note!r}")


class _Dev:
    """A scripted toolbar app with a Link dialog: clicking element 4 opens it, element 3 flips Strikethrough."""

    def __init__(self):
        self.state, self.toggles, self.acted, self.recovered, self.observed = "bar", [0, 0, 0, 0], [], [], 0

    def observe(self):
        self.observed += 1
        return _dialog_obs() if self.state == "dialog" else _toolbar_obs(tuple(self.toggles), 40 + 60 * sum(self.toggles))

    def act(self, action, som):
        self.acted.append(action["target_id"])
        if self.state == "dialog":
            return True, "ok"
        if action["target_id"] == 4:
            self.state = "dialog"
        else:
            self.toggles[action["target_id"] - 1] ^= 1
        return True, "ok"

    def recover(self, pre, post, verdict, names):
        self.recovered.append((verdict["reason"], list(names)))
        if self.state == "dialog":
            self.state = "bar"
        return {"restored": True, "how": "escape"}


class _Seq:
    """A model that answers from a script and remembers which element ids it was offered."""

    def __init__(self, ids):
        self.ids, self.offered = list(ids), []

    def __call__(self, image, som, app_key, goal):
        self.offered.append([e["id"] for e in som["elements"]])
        tid = self.ids.pop(0)
        return {"step": 1, "action": "click", "target_id": tid, "hotkey": None, "text": None, "verify_expectation": ""}, "reply"


def run_ex12() -> "TestOutcome":
    """EX12: a wrong click that opens a dialog is failed, undone, retried on the right control without re-offering the wrong one -- and the graph hears about both"""
    from si_tests_rag import _Env
    from core_organs import agent_executor as AE
    with _Env() as R:
        dev = _Dev()
        model = _Seq([4, 3])                                                   # first the neighbouring Link icon, then Strikethrough
        ag = AE.Agent(APP, dev.observe, model, dev.act, rag=R, settle_s=0, sleep=lambda s: None, recover=dev.recover, assist=False)
        rec = ag.step("Click the Strikethrough button")
        obs = R.graph.db.rows("SELECT ok, effect FROM observations WHERE app_key=? ORDER BY ts", (APP,))
    checks = {"the_first_attempt_is_failed_for_the_right_reason": rec.attempts[0]["reason"] == "wrong_control" and rec.attempts[0]["target_id"] == 4,
              "the_dialog_was_dismissed_with_the_safe_names": len(dev.recovered) == 1 and dev.recovered[0][1][-2:] == ["Cancel", "No"] and "OK" not in dev.recovered[0][1] and dev.state == "bar",
              "the_wrong_target_is_not_offered_again": model.offered[0] == [1, 2, 3, 4] and model.offered[1] == [1, 2, 3],
              "the_second_attempt_is_verified_and_the_step_is_done": rec.status == "done" and len(rec.attempts) == 2 and rec.attempts[1]["worked"] and rec.rolled_back and dev.toggles == [0, 0, 1, 0],
              "the_graph_heard_a_failure_and_then_a_success": [o["ok"] for o in obs] == [0, 1] and obs[0]["effect"] == "wrong_control",
              "timings_are_recorded": {"observe", "ground", "act", "verify", "recover", "total"} <= set(rec.timings)}
    return _verdict(checks, f"status={rec.status} attempts={[(a['target_id'], a['reason']) for a in rec.attempts]} obs={[(o['ok'], o['effect']) for o in obs]}")


def run_ex13() -> "TestOutcome":
    """EX13: when the wrong effect cannot be undone nothing else is tried; a 'no effect' is never 'rolled back'; with the assist the first attempt is already right"""
    from core_organs import agent_executor as AE
    dev = _Dev()
    dev.recover = lambda pre, post, verdict, names: {"restored": False, "how": "stuck"}
    model = _Seq([4, 3])
    ag = AE.Agent(APP, dev.observe, model, dev.act, rag=None, settle_s=0, sleep=lambda s: None, recover=dev.recover, assist=False)
    stuck = ag.step("Click the Strikethrough button")
    dev2 = _Dev()
    model2 = _Seq([4])
    ag2 = AE.Agent(APP, dev2.observe, model2, dev2.act, rag=None, settle_s=0, sleep=lambda s: None, recover=dev2.recover, assist=True)
    helped = ag2.step("Click the Strikethrough button")
    dev3 = _Dev()
    dev3.act = lambda action, som: (dev3.acted.append(action["target_id"]) or (True, "ok"))
    model3 = _Seq([2, 2])
    ag3 = AE.Agent(APP, dev3.observe, model3, dev3.act, rag=None, settle_s=0, sleep=lambda s: None, recover=dev3.recover, assist=False)
    noeff = ag3.step("Click the Italic button")
    checks = {"an_unrestorable_screen_stops_the_step": stuck.status == "wrong_effect" and len(stuck.attempts) == 1 and not stuck.rolled_back and len(model.offered) == 1,
              "the_assist_makes_the_first_attempt_right": helped.status == "done" and len(helped.attempts) == 1 and helped.assisted.startswith("UIA name assist") and dev2.toggles == [0, 0, 1, 0] and dev2.recovered == [],
              "no_effect_is_reported_and_not_rolled_back": noeff.status == "no_effect" and noeff.reason == "no_effect" and dev3.recovered == [] and len(noeff.attempts) == 1}
    return _verdict(checks, f"stuck={stuck.status} helped={helped.status}({helped.assisted}) noeff={noeff.status}")


def run_ex14() -> "TestOutcome":
    """EX14: latency -- the screen seen after a step is the next step's starting screen (one Set-of-Marks scan saved per step); a rollback or a stale picture forces a fresh one"""
    from core_organs import agent_executor as AE
    dev = _Dev()
    ag = AE.Agent(APP, dev.observe, _Seq([3, 2]), dev.act, rag=None, settle_s=0, sleep=lambda s: None, assist=False)
    r1, r2 = ag.run(["Click the Strikethrough button", "Click the Italic button"], stop_on_fail=False)
    reused = dev.observed
    dev_b = _Dev()
    ag_b = AE.Agent(APP, dev_b.observe, _Seq([3, 2]), dev_b.act, rag=None, settle_s=0, sleep=lambda s: None, assist=False, reuse_post=False)
    ag_b.run(["Click the Strikethrough button", "Click the Italic button"], stop_on_fail=False)
    dev_c = _Dev()
    ag_c = AE.Agent(APP, dev_c.observe, _Seq([3, 2]), dev_c.act, rag=None, settle_s=0, sleep=lambda s: None, assist=False, reuse_max_age_s=-1)
    ag_c.run(["Click the Strikethrough button", "Click the Italic button"], stop_on_fail=False)
    checks = {"two_steps_cost_three_scans_not_four": reused == 3 and r2.timings.get("observe_reused") == 1 and "observe_reused" not in r1.timings,
              "without_reuse_it_is_four": dev_b.observed == 4,
              "a_stale_picture_is_not_reused": dev_c.observed == 4}
    return _verdict(checks, f"scans: reuse={reused} no-reuse={dev_b.observed} stale={dev_c.observed}")


def run_ex15() -> "TestOutcome":
    """EX15: the adapter's generation is short and stops where the free-text expectation begins; a reply cut there still gives its action"""
    import torch
    from PIL import Image
    from core_organs import agent_executor as AE
    seen = {}

    class FakeModel:
        device = "cpu"

        def generate(self, **kw):
            seen.update(kw)
            return torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8]])

    class FakeProc:
        tokenizer = "TOK"

        def apply_chat_template(self, msgs, **kw):
            return {"input_ids": torch.tensor([[1, 2, 3, 4, 5]])}

        def batch_decode(self, out, skip_special_tokens=True):
            return ['[{"step": 1, "action": "click", "target_id": 20, "hotkey": null, "text": null, "verify_expectation']

    g = AE.AdapterGrounder("no/such/adapter")
    g._model, g._proc = FakeModel(), FakeProc()
    action, reply = g(Image.new("RGB", (64, 64)), _som(["File", "Edit"]), "padx", "Click the File menu")
    checks = {"the_budget_is_about_seventy_tokens": g.max_new_tokens == 72 and seen["max_new_tokens"] == 72 and seen["do_sample"] is False,
              "generation_stops_at_the_expectation": seen["stop_strings"] == ['"verify_expectation"'] and seen["tokenizer"] == "TOK",
              "the_input_size_is_the_training_size": g.max_pixels == 448 * 448,
              "a_reply_cut_at_the_stop_string_still_parses": action is not None and action["action"] == "click" and action["target_id"] == 20}
    return _verdict(checks, f"kwargs={sorted(seen)} action={action}")


def run_ex16() -> "TestOutcome":
    """EX16: a retry never repeats a target that was just undone -- the assist's pick included"""
    from core_organs import agent_executor as AE

    class NoDialogDev(_Dev):
        def act(self, action, som):                              # the Link click toggles the button but opens no dialog (the verdict will be 'no_dialog')
            self.acted.append(action["target_id"])
            self.toggles[action["target_id"] - 1] ^= 1
            return True, "ok"
    dev = NoDialogDev()
    model = _Seq([4, 3, 3])
    ag = AE.Agent(APP, dev.observe, model, dev.act, rag=None, settle_s=0, sleep=lambda s: None, recover=dev.recover, assist=True, max_attempts=3)
    rec = ag.step("Click the Link button")
    d2 = _Dev()
    r3 = AE.Agent(APP, d2.observe, _Seq([4, 4, 4]), d2.act, rag=None, settle_s=0, sleep=lambda s: None, recover=d2.recover, assist=True, max_attempts=3).step("Click the Strikethrough button")
    checks = {"the_undone_target_is_clicked_once_only": dev.acted == [4] and len(rec.attempts) == 1 and rec.attempts[0]["reason"] == "no_dialog",
              "the_step_ends_as_a_wrong_effect_with_the_reason": rec.status == "wrong_effect" and "already tried" in rec.why and rec.rolled_back,
              "the_model_was_asked_again_without_that_element": len(model.offered) == 2 and 4 not in model.offered[1],
              "the_assist_fixes_the_first_attempt_so_no_retry_is_needed": r3.status == "done" and len(r3.attempts) == 1 and r3.assisted.startswith("UIA name assist")}
    return _verdict(checks, f"clicks={dev.acted} status={rec.status} why={rec.why!r} attempts={[(a['target_id'], a['reason']) for a in rec.attempts]}")


TESTS = [("EX1", run_ex1), ("EX2", run_ex2), ("EX3", run_ex3), ("EX4", run_ex4), ("EX5", run_ex5), ("EX6", run_ex6), ("EX7", run_ex7), ("EX8", run_ex8), ("EX9", run_ex9), ("EX10", run_ex10), ("EX11", run_ex11), ("EX12", run_ex12), ("EX13", run_ex13), ("EX14", run_ex14), ("EX15", run_ex15), ("EX16", run_ex16), ("TU1", run_tu1), ("TU2", run_tu2)]

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
            r = TestOutcome(False, "EXCEPTION " + traceback.format_exc()[-1800:])
        print(f"[{'PASS' if r.passed else 'FAIL'}] {name} {time.time() - t0:5.1f}s  {(fn.__doc__ or '').strip().splitlines()[0][:90]}\n        {r.evidence[:1700]}")
        rc |= 0 if r.passed else 1
    sys.exit(rc)
