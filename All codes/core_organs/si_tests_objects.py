"""
si_tests_objects -- AR48: the object-knowledge compiler and its role critic (offline, no application needed).
"""
from __future__ import annotations

import json
import os
import tempfile

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except ImportError:
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore

SHAPES = ["cube", "cylinder", "cone", "sphere"]


def run_ar48() -> "TestOutcome":
    """AR48: part roles and real proportions as data -- every stored object compiles to a sound design (no floating / piercing / count problems), sizes follow the order's words and counts, a new object is a data entry, and a design built from the wrong forms or on the wrong side is caught"""
    from core_organs import brain_planner as BP
    from core_organs import object_knowledge as OK
    cats = OK.known_categories()
    bad: list = []
    for c in cats:
        r = OK.compile_design(f"build a {c}", SHAPES)
        if not r:
            bad.append(f"{c}: no design")
            continue
        d, p = BP.validate_design(r["design"], SHAPES)
        p += BP.critic(d) + OK.role_critic(f"build a {c}", d)
        if BP.settle(d):
            p.append("settle had to move something")
        if p:
            bad.append(f"{c}: {p[:2]}")
    shelf = OK.compile_design("a tall bookshelf with five shelves", SHAPES)
    sd, _p = BP.validate_design(shelf["design"], SHAPES)
    shelves = [x for x in sd["parts"] if x["name"].startswith("shelf")]
    gaps_ok = all(b["at"][2] - a["at"][2] >= 0.15 for a, b in zip(sorted(shelves, key=lambda x: x["at"][2]), sorted(shelves, key=lambda x: x["at"][2])[1:]))
    small = OK.compile_design("a small chair", SHAPES)["dims"]["H"]
    tall = OK.compile_design("a tall chair", SHAPES)["dims"]["H"]
    meas = OK.compile_design("a bookcase 1.9 m tall", SHAPES)["dims"]["H"]
    three = OK.compile_design("a three legged stool", SHAPES)["design"]["parts"]
    try:
        OK.evaluate("__import__('os').system('x')", {})
        unsafe_blocked = False
    except Exception:
        unsafe_blocked = True
    # a bookshelf of ovals and a chair whose back is at the front: both must be caught by the roles
    oval = {"object": "bookshelf", "parts": [{"name": "shelf1", "shape": "sphere", "size": [0.9, 0.3, 0.5], "at": [0, 0, 0.3]}, {"name": "shelf2", "shape": "sphere", "size": [0.9, 0.3, 0.5], "at": [0, 0, 1.0]},
                                              {"name": "side1", "shape": "cube", "size": [0.02, 0.3, 1.8], "at": [-0.45, 0, 0.9]}, {"name": "side2", "shape": "cube", "size": [0.02, 0.3, 1.8], "at": [0.45, 0, 0.9]}]}
    caught_oval = bool(OK.role_critic("build a bookshelf", oval))
    ch = OK.compile_design("build a chair", SHAPES)["design"]
    for x in ch["parts"]:
        if x["name"].startswith("backrest"):
            x["at"][1] = abs(x["at"][1])                                                    # the back moved to the front edge
    caught_back = any("rear" in m or "front" in m for m in OK.role_critic("build a chair", ch))
    # a new object is a data entry: no code change
    old = OK.STORE
    tmp = os.path.join(tempfile.mkdtemp(prefix="okstore_"), "ok.json")
    json.dump({"wood": [0.5, 0.4, 0.3], "categories": {"crate": {"keywords": ["crate", "box"], "dims": {"W": [0.4, 0.8, 0.6], "D": [0.3, 0.5, 0.4], "H": [0.25, 0.5, 0.35]}, "params": {"t": [0.015, 0.025, 0.02]},
              "parts": [{"name": "floor", "shape": "cube", "size": ["W", "D", "t"], "at": ["0", "0", "t/2"]}, {"name": "wall{i}", "repeat": "sides", "shape": "cube", "size": ["t", "D", "H"], "at": ["SX*(W/2 - t/2)", "0", "H/2"]}]}}}, open(tmp, "w"))
    try:
        OK.STORE = tmp
        OK._CACHE.clear()
        crate = OK.compile_design("make a wooden crate", SHAPES)
        new_ok = bool(crate) and len(crate["design"]["parts"]) == 3 and OK.category_of("make a wooden crate") == "crate"
    finally:
        OK.STORE = old
        OK._CACHE.clear()
    checks = {"every_stored_object_compiles_sound": not bad and len(cats) >= 9, "five_compartments_six_boards_apart": len(shelves) == 6 and gaps_ok, "size_words_move_inside_the_range": small < tall,
              "a_stated_measure_is_used": abs(meas - 1.9) < 0.01, "three_legged_has_three_legs": sum(1 for x in three if x["name"].startswith("leg")) == 3, "formulas_are_not_eval": unsafe_blocked,
              "ovals_as_shelves_caught": caught_oval, "back_at_the_front_caught": caught_back, "a_new_object_is_only_data": new_ok,
              "longest_keyword_wins": OK.category_of("a desk lamp") == "desk lamp" and OK.category_of("a coffee table") == "coffee table" and OK.category_of("a rocket") is None}
    return _verdict(checks, f"categories={len(cats)} problems={bad[:3]} small/tall chair H={small:.2f}/{tall:.2f}")


TESTS = [("AR48", run_ar48)]
