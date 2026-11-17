"""
si_tests_popup_arch -- AR45 pop-up classes + AUTH_BLOCKED, AR46 archetype matrix + router + fallback hint, AR47 honest 70/30 evaluation (offline).
"""
from __future__ import annotations

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except ImportError:
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore


def run_ar45() -> "TestOutcome":
    """AR45: pop-up classes (login / recovery pane / update / welcome / UAC / error / picker) and a sign-in wall is AUTH_BLOCKED, never an answer"""
    from core_organs import popup_policy as pp

    def cls(title, msg):
        i = pp.DialogInfo(0)
        i.title, i.texts = title, [msg]
        c = pp.classify(i)
        return c, pp.escalation_action(c, title + " " + msg)
    checks = {}
    c, st = cls("Sign in", "Enter your password to continue")
    checks["sign_in_is_login_and_auth_blocked"] = c == "login" and st == "AUTH_BLOCKED"
    c, st = cls("Verify", "Enter the verification code we sent you")
    checks["2fa_is_auth_blocked"] = st == "AUTH_BLOCKED"
    c, st = cls("User Account Control", "Do you want to allow this app to make changes to your device?")
    checks["uac_is_permission_not_login"] = c == "permission" and st == "need_human"
    checks["recovery_pane"] = cls("Document Recovery", "Word found unsaved files were found")[0] == "recovery_pane"
    checks["update"] = cls("Update available", "A new version is available. Update now?")[0] == "update"
    checks["welcome"] = cls("Welcome", "Take a tour of what's new")[0] == "welcome"
    checks["error_still_error"] = cls("Error", "Cannot open the file")[0] == "error"
    checks["picker_still_picker"] = cls("Save As", "")[0] == "file_picker"
    safe = all(r not in ("yes", "recover", "update now", "delete") for cat in ("recovery_pane", "update", "welcome") for r in pp.POLICY[cat])
    checks["new_categories_have_only_non_destructive_roles"] = safe and all(c in pp.POLICY for c in ("recovery_pane", "update", "welcome"))
    d = pp.Decision(False, True, "need_human", "escalate")
    checks["decision_has_status_field"] = d.status == ""
    return _verdict(checks)


def run_ar46() -> "TestOutcome":
    """AR46: 25 archetypes x (7 train + 3 held-out) apps, grammar/keys/traps/templates present, router ranks from control words, fallback hint only without a RAG pathway"""
    from core_organs.rag import archetypes as A
    checks = {"25_archetypes": len(A.ARCHETYPES) == 25 and len({a["id"] for a in A.ARCHETYPES}) == 25,
              "7_train_3_test_each": all(len(a["train"]) == 7 and len(a["test"]) == 3 for a in A.ARCHETYPES),
              "no_app_in_two_classes": len({x.lower() for a in A.ARCHETYPES for x in a["train"] + a["test"]}) == sum(len(a["train"]) + len(a["test"]) for a in A.ARCHETYPES),
              "every_class_has_grammar_signals_templates": all(a["grammar"] and a["signals"] and a["templates"] for a in A.ARCHETYPES)}
    r = A.ArchetypeRouter()
    sheet = {"app": "", "title": "", "controls": [("button", n) for n in ("Formulas", "Cell", "Name Box", "Pivot", "Sort", "Filter", "Chart")]}
    checks["router_ranks_from_controls_not_name"] = r.classify(sheet, 1)[0][0] == "spreadsheet"
    h = A.hint("NeverSeenApp", "set a timer for 5 minutes", False, {"app": "", "title": "", "controls": [("button", "Timer"), ("button", "Alarm"), ("button", "Stopwatch"), ("tab", "World clock")]})
    checks["hint_is_archetype_labelled_and_capped"] = bool(h) and h["source"] == "archetype" and h["confidence"] <= 0.45 and h["phases"]
    checks["hint_withheld_when_rag_has_pathway"] = A.hint("X", "y", True, sheet) is None
    checks["email_send_is_a_trap_calculator_equals_is_not"] = A.is_trap("email_client", "Send") and not A.is_trap("calculator", "Equals")
    uncertain = {"app": "", "title": "", "controls": [("node", "Node"), ("button", "Queue Prompt")]}
    checks["ambiguous_first_contact_has_no_skeleton"] = r.assess(uncertain)["status"] == "ambiguous" and A.hint("Unknown", "run it", False, uncertain, r) is None
    return _verdict(checks)


def run_ar47() -> "TestOutcome":
    """AR47: the 70/30 evaluation runs on really scanned apps, reports n and the name-only number as bookkeeping, and signals beat chance by a wide margin"""
    from core_organs.rag import archetypes as A
    e = A.evaluate_70_30_split(seeds=5)
    top1 = e.get("signals_only_top1", 0)
    checks = {"uses_real_scans": e.get("real_apps", 0) >= 10 and e.get("held_out_predictions", 0) >= 20,
              "name_only_reported_as_bookkeeping": "name_only_zero_shot" in e["matrix"],
              "held_out_names_not_given_to_the_router": True,
              "signals_far_above_chance_1_in_25": top1 >= 0.30}
    return _verdict(checks, f"signals_top1={top1} fitted_top1={e.get('signals_plus_fitted_top1')} top3={e.get('signals_plus_fitted_top3')} n={e.get('held_out_predictions')}")


TESTS = [("AR45", run_ar45), ("AR46", run_ar46), ("AR47", run_ar47)]
