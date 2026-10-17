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


TESTS = [("EX1", run_ex1), ("EX2", run_ex2), ("EX3", run_ex3), ("EX4", run_ex4), ("EX5", run_ex5), ("EX6", run_ex6), ("EX7", run_ex7), ("EX8", run_ex8), ("TU1", run_tu1), ("TU2", run_tu2)]

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
