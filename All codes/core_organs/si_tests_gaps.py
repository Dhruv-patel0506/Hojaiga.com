"""
si_tests_gaps -- offline tests for the Oct-10 gap fixes (registered into the Professor suite through si_tests_apprun.TESTS):

  PR63  version fit + step scope: 'Applies To' lists, Mac / web / phone passages, OS / launch / content / dialog-button / choice steps, a page quality gate
  PR64  grounding: location clauses, prose glued to a path, a skipped ribbon group, a group named as a path, dialog buttons never bound early, content / choice / bare list items, coverage
  PR65  vendor command manifest -> catalog (no COM): tab > group > menu paths, labels THIS build shows, ids it does not know dropped, backstage / context menus / contextual tabs
  PR66  every step checked against its expectation (verify) + hybrid supervision decisions
  PR67  labelled answer set: scoring of 'where' / 'shortcut' / 'howto' answers, the set built from measured facts only
  PR68  the dialog walker on a fake interface: dialog tabs, drop-down lists, nested dialogs to depth 3 (never 4), every level left through its own Cancel and proved back
No desktop window, no network, no model.
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from types import SimpleNamespace as NS
from typing import Any, Dict, List

for _p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except Exception:                                        # pragma: no cover
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore


def _cat(rows):
    from core_organs.professor.harvest import Catalog, Verb, verb_id
    c = Catalog(app_key="demo")
    for path, label, role, extra in rows:
        v = Verb(verb_id(path, label), label, list(path), extra.get("shortcut", ""), "", True, False, extra.get("leads_to", ""), 0, extra.get("aid", ""), role, extra.get("sources", ["uia"]))
        c.verbs.append(v)
    return c


# ====================================================================================================================== PR63
def run_pr63() -> TestOutcome:
    """PR63: a guide passage is checked against the INSTALLED edition before it counts - 'Applies To' lists, Mac / web / phone passages; each step is classified (ui / launch / content / dialog
    button / choice / outside) by general wording, never by application name; a page of boiler-plate fails the quality gate"""
    from core_organs.professor.knowledge import version_fit as VF, guide_finder as GF
    mac_only = VF.document_fit("Applies To\nWord for Microsoft 365 for Mac Word 2021 for Mac\n\nSome text.")
    both = VF.document_fit("Applies To\nWord for Microsoft 365 Word 2021 Word for Microsoft 365 for Mac\n\nSome text.")
    win_chunk = VF.chunk_platform("Change margins", "Applies To\nWord for Microsoft 365 for Mac Word 2021 for Mac\n1. Select **Layout** > **Margins**.")
    mac_chunk = VF.chunk_platform("Insert pictures > Replace", "Hold down the control key and select the picture, then choose **Change Picture**. Use Finder.")
    web_head = VF.chunk_platform("Share > Word for the web", "1. Select **Share**.")
    S = lambda t, w=("powerpoint",): VF.step_scope(t, "any", w)[0]
    scopes = {"os": S("Press the Windows button on the taskbar."), "launch": S("Open PowerPoint."), "tab_is_not_launch": S("Open the Options tab."), "content": S("Select the text you want to format."),
              "caret": S("Click where you want to insert the picture."), "dialog": S("Select **OK**."), "choice": S("Select the layout you want from the menu."), "ui": S("Select **New Slide**."),
              "mac_keys": S("Press Control+Option+M."), "noise": S("Enable JavaScript to use the app."), "account": S("Enter names or email addresses of the people you want to share with.")}
    q_good = VF.procedural_quality("1. Select **Layout** > **Margins**.\n2. Select **Custom Margins**.\nTip: margins.")
    q_bad = VF.procedural_quality("Skip to main content\nWas this page helpful?\nThank you for your feedback!\nSubscribe to our newsletter\nCookies")
    checks = {"mac_only_page_is_other_platform": mac_only["fit"] == "other_platform", "multi_edition_page_fits": both["fit"] == "fits",
              "applies_to_list_does_not_make_a_windows_passage_mac": win_chunk == "any", "strong_mac_cues_make_a_mac_passage": mac_chunk == "mac", "heading_names_the_web_edition": web_head == "web",
              "scopes": scopes == {"os": "outside", "launch": "launch", "tab_is_not_launch": "ui", "content": "content", "caret": "content", "dialog": "dialog", "choice": "choice", "ui": "ui",
                                   "mac_keys": "outside", "noise": "outside", "account": "outside"},
              "quality_gate": q_good["score"] > 0.5 and q_bad["score"] < 0.08,
              "allow_list": [GF.allowed_host(u, ["microsoft.com"])[0] for u in ("https://support.microsoft.com/en-us/word/x", "https://account.microsoft.com/account", "https://seo-howto.example.com/tips",
                                                                                  "https://github.com/blender/blender/wiki/x", "https://github.com/foo/bar")] == [True, False, False, True, False]}
    return _verdict(checks, f"scopes={scopes}; fits={mac_only['fit']}/{both['fit']}; chunk={win_chunk}/{mac_chunk}/{web_head}; quality {q_good['score']}/{q_bad['score']}")


# ====================================================================================================================== PR64
def run_pr64() -> TestOutcome:
    """PR64: grounding the way manuals write - a location clause is not a step but tells where the next one happens; prose glued to a path element is cut; a path that skips a ribbon GROUP still
    grounds (Layout > Margins = Layout > Page Setup > Margins); a group named as a path element grounds to its tab; 'Select OK' is the OPEN dialog's button (never bound early); content,
    choice and bare-list steps are named; steps outside the application leave the coverage denominator"""
    from core_organs.professor.knowledge import guide_steps as GS
    cat = _cat([([], "Layout", "tab", {}), (["Layout", "Page Setup"], "Margins", "dropdown", {"leads_to": "opens a menu"}), (["Layout", "Page Setup", "Margins"], "Custom Margins", "menu_item", {}),
                (["Layout", "Page Setup", "Margins"], "Narrow", "menu_item", {}), ([], "Review", "tab", {}), (["Review", "Tracking"], "Track Changes", "toggle", {}),
                (["Insert", "Illustrations", "Pictures"], "This Device", "menu_item", {}), (["Context menu: Text"], "Paste", "menu_item", {}), (["Home", "Clipboard"], "Paste", "button", {}),
                (["Edit"], "Select All", "menu_item", {"shortcut": "Ctrl+A"}), (["Page Setup"], "Header", "field", {})])
    loc = GS.parse_steps("1. On the **Review** tab, in the **Tracking** group, select **Track Changes**.", "c")
    fieldloc = GS.parse_steps("In the **Header** box, type \"Report\".", "c")
    trimmed = GS.parse_steps("1. Select **Insert** > **Pictures** > **This Device** for a picture on your PC.", "c")
    g_skip = GS.ground(GS.parse_steps("1. Select **Layout** > **Margins**.\n2. Select the margin configuration you want, or select **Custom Margins** to define your own margins.", "c"), cat)
    g_group = GS.ground_step(GS.parse_line("select Review > Tracking", 1), cat)
    g_ok = GS.ground_step(GS.parse_line("Select **OK**.", 1), _cat([(["Font"], "OK", "button", {})]))
    g_content = GS.ground_step(GS.parse_line("Select the text you want to change.", 1), cat)
    g_choice = GS.ground(GS.parse_steps("1. Select **Layout** > **Margins**.\n2. Select the option you want.", "c"), cat)
    rc = GS.ground(GS.parse_steps("1. Right-click the text.\n2. Select **Paste**.", "c"), cat)
    bare = GS.parse_steps("- Select All\n- Write and format documents", "c")
    g_bare = GS.ground(bare, cat)
    out = GS.ground(GS.parse_steps("1. Press the Windows button on the taskbar.\n2. Select **Layout** > **Margins**.", "c"), cat)
    checks = {"location_clause_becomes_the_path": len(loc) == 1 and loc[0].path == ["Review", "Tracking", "Track Changes"] and GS.ground(loc, cat)[0].verb.label == "Track Changes",
              "field_clause_names_the_target": len(fieldloc) == 1 and fieldloc[0].target == "Header" and fieldloc[0].text == "Report",
              "prose_cut_from_path": trimmed[0].path == ["Insert", "Pictures", "This Device"] and GS.ground(trimmed, cat)[0].how == "path",
              "skipped_group_still_grounds": g_skip[0].how == "path" and g_skip[0].verb.label == "Margins" and g_skip[1].verb is not None and g_skip[1].verb.label == "Custom Margins",
              "group_as_path_grounds_to_tab": g_group.how == "path" and g_group.verb is not None and g_group.verb.label == "Review",
              "dialog_button_is_live_not_bound": g_ok.how == "dialog_button" and g_ok.verb is None, "content_named": g_content.how == "content",
              "choice_takes_first_child": g_choice[1].how == "choice" and g_choice[1].verb is not None and g_choice[1].verb.label in ("Custom Margins", "Narrow"),
              "after_right_click_the_context_menu_item_wins": rc[1].verb is not None and rc[1].verb.path == ["Context menu: Text"],
              "bare_item_named_like_a_control_grounds": g_bare[0].how == "label" and g_bare[0].verb.label == "Select All", "bare_topic_is_outside": g_bare[1].how == "outside",
              "outside_leaves_the_denominator": GS.coverage(out) == (1, 1)}
    return _verdict(checks, f"loc={[s.path for s in loc]}; skip={[(g.how, g.verb.label if g.verb else None) for g in g_skip]}; group={g_group.how}; rc={[(g.how, g.verb.path if g.verb else None) for g in rc]}; "
                            f"bare={[g.how for g in g_bare]}; cov={GS.coverage(out)}")


# ====================================================================================================================== PR65
def run_pr65() -> TestOutcome:
    """PR65: the vendor's command manifest becomes catalog verbs with the labels the INSTALLED build shows - tab > group > menu paths, ids the build does not know are dropped (counted), backstage under
    File, context menus kept apart, contextual tabs marked, dialog launchers lead to a dialog; no COM needed for the conversion itself"""
    from core_organs.professor import vendor_commands as VC
    LBL = {"TabHome": "Home", "GroupFont": "Font", "Bold": "Bold", "FontDialog": "Font...", "TabPageLayoutWord": "Layout", "GroupPageLayoutSetup": "Page Setup", "PageMarginsGallery": "Margins",
           "MarginsCustomMargins": "Custom Margins...", "TabSetTableTools": "Table Tools", "TabTableToolsLayout": "Table Layout", "GroupTableRowsAndColumns": "Rows & Columns",
           "TableInsertRowsAbove": "Insert Above", "Paste": "Paste", "FilePrint": "Print"}

    class L:
        def label(self, ident):
            return (LBL[ident], "desc of " + ident) if ident in LBL else (None, "")
    rows = [{"Control Name": "Bold", "Control Type": "toggleButton", "Tab Set": "None (Core Tab)", "Tab": "TabHome", "Group/Context Menu Name": "GroupFont"},
            {"Control Name": "FontDialog", "Control Type": "button (dialogBoxLauncher)", "Tab Set": "None (Core Tab)", "Tab": "TabHome", "Group/Context Menu Name": "GroupFont"},
            {"Control Name": "PageMarginsGallery", "Control Type": "gallery", "Tab Set": "None (Core Tab)", "Tab": "TabPageLayoutWord", "Group/Context Menu Name": "GroupPageLayoutSetup"},
            {"Control Name": "MarginsCustomMargins", "Control Type": "button", "Tab Set": "None (Core Tab)", "Tab": "TabPageLayoutWord", "Group/Context Menu Name": "GroupPageLayoutSetup", "Parent Control": "PageMarginsGallery"},
            {"Control Name": "TableInsertRowsAbove", "Control Type": "button", "Tab Set": "TabSetTableTools", "Tab": "TabTableToolsLayout", "Group/Context Menu Name": "GroupTableRowsAndColumns"},
            {"Control Name": "Paste", "Control Type": "button", "Tab Set": "None (Context Menu)", "Group/Context Menu Name": "ContextMenuText"},
            {"Control Name": "FilePrint", "Control Type": "button", "Tab Set": "None (Backstage View)", "Tab": "TabPrint"},
            {"Control Name": "RemovedInThisBuild", "Control Type": "button", "Tab Set": "None (Core Tab)", "Tab": "TabHome", "Group/Context Menu Name": "GroupFont"},
            {"Control Name": "GroupFont", "Control Type": "group", "Tab Set": "None (Core Tab)", "Tab": "TabHome"},
            {"Control Name": "SomeHiddenCommand", "Control Type": "button", "Tab Set": "None (Not in the Ribbon)"}]
    verbs, rep = VC.office_catalog(rows, L(), "demo")
    by = {v.label: v for v in verbs}
    checks = {"tab_group_path": by["Bold"].path == ["Home", "Font"] and by["Bold"].role == "toggle" and by["Bold"].aid == "mso:Bold",
              "dialog_launcher_leads_to_dialog": by["Font"].leads_to == "opens a dialog" and by["Font"].path == ["Home", "Font"],
              "gallery_item_under_its_gallery": by["Custom Margins"].path == ["Layout", "Page Setup", "Margins"] and by["Margins"].leads_to == "opens a menu",
              "contextual_tab_marked": by["Insert Above"].path == ["Table Layout", "Rows & Columns"] and "contextual" in by["Insert Above"].desc,
              "context_menu_kept_apart": by["Paste"].path == ["Context menu: Text"], "backstage_under_file": by["Print"].path == ["File", "Print"],
              "unknown_to_this_build_dropped": "RemovedInThisBuild" not in by and rep["not_in_this_version"] == 1, "containers_and_hidden_commands_not_verbs": rep["skipped_types"] == 1 and rep["not_in_ribbon"] == 1,
              "every_kept_verb_says_where_it_came_from": all(v.sources == ["vendor-manifest"] for v in verbs)}
    return _verdict(checks, f"{len(verbs)} verbs: {[(v.path, v.label) for v in verbs]}; rep={ {k: rep[k] for k in ('kept', 'not_in_this_version', 'skipped_types', 'not_in_ribbon')} }")


# ====================================================================================================================== PR66
def run_pr66() -> TestOutcome:
    """PR66: every step has a STATED expectation (the manual's own result sentence first, else what the control is known to do) and the screen is checked for exactly that; the hybrid supervision
    policy runs owned sandboxed work autonomously and pauses for sending / accounts / OS commands / a messenger's Enter"""
    from core_organs.professor import verify as VF, supervision as SV
    from core_organs.professor.harvest import Verb
    st = NS(kind="verb", goal="Select **Font** dialog launcher.", text="", want="", verb="Font", path=["Home", "Font"])
    v_dialog = Verb("x", "Font", ["Home", "Font"], leads_to="opens a dialog", role="button")
    guide = "1. Select **Home** > **Font**.\nThe **Font** dialog box opens.\n2. Choose a size."
    st_g = NS(kind="verb", goal="Select **Home** > **Font**.", text="", want="", verb="Font")
    e_guide = VF.expectation_for(st_g, None, guide)
    e_ctl = VF.expectation_for(st, v_dialog, "")
    e_text = VF.expectation_for(NS(kind="text", goal="type", text="Hello"), None, "")
    d_win = NS(new_windows=[5], added=["a", "b"], changed_state=[], changed_text=[], effect=lambda: "opens_dialog", summary=lambda: "1 new window")
    d_none = NS(new_windows=[], added=[], changed_state=[], changed_text=[], effect=lambda: "no_effect", summary=lambda: "nothing changed")
    s1 = NS(texts={"doc": "Hello world"})
    ok_dialog = VF.check(e_ctl, None, None, d_win, [NS(name="Font")])[0]
    bad_dialog = VF.check(e_ctl, None, None, d_none, [])[0]
    ok_text = VF.check(e_text, None, s1, NS(new_windows=[], added=[], changed_state=[], changed_text=[("doc", "", "Hello world")], effect=lambda: "state_change", summary=lambda: ""), [])[0]
    sup = SV.Supervisor(owned=True, sandboxed=True, sandbox_dir="C:/sb")
    msg = SV.Supervisor(owned=True, sandboxed=True, sandbox_dir="C:/sb", messaging=True)
    asked = SV.Supervisor(owned=True, sandboxed=True, sandbox_dir="C:/sb", ask=lambda step, why: True)
    D = lambda **k: NS(**{"verb": "", "text": "", "goal": "", "path": [], "kind": "verb", **k})
    checks = {"guide_sentence_is_the_expectation": e_guide.source == "guide" and e_guide.kind == "dialog_opens", "control_knowledge_is_the_fallback": e_ctl.kind == "dialog_opens" and e_ctl.source == "control",
              "typed_text_expected_on_screen": e_text.kind == "text_appears", "dialog_seen_is_confirmed": ok_dialog is True, "nothing_happening_contradicts": bad_dialog is False, "text_found": ok_text is True,
              "sandboxed_owned_work_is_autonomous": sup.check(D(verb="Bold"))[0] == "autonomous", "send_needs_a_yes": sup.check(D(verb="Send"))[0] == "approval",
              "os_command_needs_a_yes": sup.check(D(verb="Run", goal="open PowerShell and type"))[0] == "approval", "messenger_enter_needs_a_yes": msg.check(D(kind="key", text="enter"))[0] == "approval",
              "not_owned_needs_a_yes": SV.Supervisor(owned=False).check(D(verb="Bold"))[0] == "approval", "a_person_can_say_yes": asked.allow(D(verb="Send"))[0] is True,
              "decisions_are_kept": len(asked.decisions) == 1 and asked.decisions[0]["asked"] is True}
    return _verdict(checks, f"guide={e_guide.kind}/{e_guide.said[:40]}; ctl={e_ctl.kind}; checks {ok_dialog}/{bad_dialog}/{ok_text}")


# ====================================================================================================================== PR67
def run_pr67() -> TestOutcome:
    """PR67: answers are scored against LABELLED facts - a 'where' answer must name the tab and the parent, a 'shortcut' answer the chord, a 'howto' answer at least half of the procedure's controls
    with the first one; labels come only from measured / vendor-verified facts, a label in two places is left out"""
    from core_organs.professor import answer_eval as AE
    w = {"kind": "where", "facts": ["Layout", "Margins"], "need": "all"}
    sc = {"kind": "shortcut", "facts": ["Ctrl+B"], "need": "all"}
    h = {"kind": "howto", "facts": ["Insert", "Table", "Insert Table"], "need": "half_with_first"}
    cat = _cat([(["Layout", "Page Setup", "Margins"], "Custom Margins", "button", {"sources": ["vendor-manifest"]}), (["Home", "Font"], "Bold", "toggle", {"sources": ["uia"], "shortcut": "Ctrl+B"}),
                (["Home"], "Copy", "button", {"sources": ["uia"]}), (["Edit"], "Copy", "menu_item", {"sources": ["win32-menu"]}), (["Home", "Font"], "Guess", "button", {"sources": ["vision"]})])
    import core_organs.professor.workflows as WF
    real = WF.build
    WF.build = lambda *a, **k: {"workflows": []}
    try:
        items = AE.build_set("demo", 5, catalog=cat)
    finally:
        WF.build = real
    kinds = {(i["kind"], i["target"]) for i in items}
    checks = {"where_needs_tab_and_parent": AE.score("Go to Layout, then open Margins.", w)[0] and not AE.score("It is in the Layout tab.", w)[0],
              "shortcut_chord": AE.score("Press Ctrl + B.", sc)[0] and not AE.score("Use the Bold button.", sc)[0],
              "howto_half_with_first": AE.score("On the Insert tab click Table.", h)[0] and not AE.score("Click Table.", h)[0],
              "plural_insensitive": AE.score("Open the Layouts tab and the Margin gallery.", w)[0],
              "labels_only_from_measured_facts": ("where", "Guess") not in kinds, "ambiguous_label_left_out": ("where", "Copy") not in kinds,
              "set_has_where_and_shortcut": ("where", "Custom Margins") in kinds and ("shortcut", "Bold") in kinds}
    return _verdict(checks, f"items={sorted(kinds)}")


# ====================================================================================================================== PR68
def run_pr68() -> TestOutcome:
    """PR68: a clicked option that opens a DIALOG is explored inside: its tabs are read (and the first tab selected again), its drop-down lists are read, the dialogs IT opens are explored to depth 3
    and never deeper, every level is left through its own Cancel and the parent is proved back - the whole interface ends where it started"""
    from core_organs.professor import reveal as RV, menus as MN
    from core_organs.professor.harvest import Catalog
    DLG = {"Page Setup": {"tabs": ["Margins", "Paper", "Layout"], "per_tab": {"Margins": ["Top", "Bottom"], "Paper": ["Paper size"], "Layout": ["Header", "Footer"]}, "combo": ("Orientation", ["Portrait", "Landscape"]),
                          "opens": ["Options..."]},
           "Options": {"tabs": [], "per_tab": {"": ["Mirror margins"]}, "combo": None, "opens": ["Advanced..."]},
           "Advanced": {"tabs": [], "per_tab": {"": ["Gutter position"]}, "combo": None, "opens": ["Deeper..."]},
           "Deeper": {"tabs": [], "per_tab": {"": ["Too deep"]}, "combo": None, "opens": []}}
    w: Dict[str, Any] = {"stack": [], "tab": {}, "combo": None, "events": []}
    ctr = [0]

    def nd(role, name, dlg="", pats=("invoke",), sel=None):
        ctr[0] += 1
        return NS(role=role, name=name, pats=list(pats), expand_state=(0 if "expand" in pats else -1), enabled=True, offscreen=False, aid=f"{dlg}:{role}:{name}", help="", accel="", selected=sel,
                  toggle_state=-1, rect=(0, ctr[0], 50, ctr[0] + 9), ctype=role.capitalize() + "Control", ctrl=None, idx=ctr[0], parent=-1)

    def nodes():
        out = [nd("button", "Page Setup...", "main"), nd("button", "Bold", "main")]
        main_n = len(out)
        for d in w["stack"]:
            spec = DLG[d]
            tab = w["tab"].get(d, (spec["tabs"] or [""])[0])
            out += [nd("tabitem", t, d, ("select",), sel=(t == tab)) for t in spec["tabs"]]
            out += [nd("edit", x, d) for x in spec["per_tab"].get(tab, [])]
            if spec["combo"]:
                out.append(nd("combobox", spec["combo"][0], d, ("expand",)))
                if w["combo"] == (d, spec["combo"][0]):
                    out += [nd("listitem", x, d, ("select",)) for x in spec["combo"][1]]
            out += [nd("button", o, d) for o in spec["opens"]] + [nd("button", "Cancel", d), nd("button", "OK", d)]
        ex.main_n = main_n
        return out

    class FX:
        allowed = True

        def node(self, n):
            name = n.name.rstrip(".").rstrip("…")
            if n.name.endswith("...") and name in DLG:
                w["stack"].append(name)
                w["events"].append("open " + name)
            elif n.name == "Cancel" and w["stack"]:
                w["events"].append("cancel " + w["stack"].pop())
            return True, "UIA Invoke"

        def key(self, k):
            if k == "escape" and w["stack"]:
                w["events"].append("escape " + w["stack"].pop())
            return True, "key"

        def close_popups(self, keep):
            n = 0
            while len(w["stack"]) > len(keep or ()):
                w["stack"].pop()
                n += 1
            return n

        def holding(self):
            return contextlib.nullcontext()

        def focus_watch(self):
            return contextlib.nullcontext()

        def why_not(self):
            return ""

    class EX:
        main_n = 2

        @property
        def _main_n(self):
            return self.main_n

        def _all_nodes(self):
            return nodes()

        def _live_node(self, v):
            return next((n for n in nodes() if MN._item_label(n)[0] == v.label or n.name == v.label + "..."), None)

        def _open_path(self, v):
            return False

    ex = EX()

    def snap(h, **k):
        st = (tuple(w["stack"]), tuple(sorted(w["tab"].items())), w["combo"])
        return NS(sig=str(st), windows=tuple(range(len(w["stack"]))), names={}, texts={}, image=None)

    def fake_delta(a, b):
        nw = list(range(len(a.windows), len(b.windows)))
        return NS(new_windows=nw, added=[], effect=lambda: "no_effect" if a.sig == b.sig else ("opens_dialog" if nw else "state_change"), summary=lambda: "")

    def fake_expand(fx, n, deadline_s=2.0):
        d = n.aid.split(":")[0]
        if n.role == "tabitem":
            w["tab"][d] = n.name
        elif n.role == "combobox":
            w["combo"] = (d, n.name)
        return True, "UIA Expand"

    def fake_collapse(n, deadline_s=1.5):
        w["combo"] = None
        return True
    saved = (RV.snapshot, RV.delta, RV.diff_state, MN._expand, MN.collapse, MN._await_items, time.sleep)
    RV.snapshot, RV.delta = snap, fake_delta
    RV.diff_state = lambda a, b, tol=0.0: [] if a.sig.split("),")[0] == b.sig.split("),")[0] else ["windows differ"]
    MN._expand, MN.collapse = fake_expand, fake_collapse
    MN._await_items = lambda all_n, base, wait_s=2.0, step_s=0.25: (all_n(), [n for n in all_n() if MN._ident(n) not in base and n.name])
    time.sleep = lambda s: None
    try:
        cat = Catalog(app_key="fake")
        rv = RV.Revealer(ex, FX(), 1, cat, reset=lambda: None, max_depth=3, per_surface_s=60.0)
        out = rv._try(RV.Cand([], "Page Setup...", "button", "", True, 2.0))
    finally:
        RV.snapshot, RV.delta, RV.diff_state, MN._expand, MN.collapse, MN._await_items, time.sleep = saved
    paths = {(tuple(v.path), v.label) for v in cat.verbs}
    inside = out.get("inside", {})
    checks = {"surface_is_a_dialog": out["kind"] == "dialog", "every_tab_read": (("Page Setup", "Paper"), "Paper size") in paths and (("Page Setup", "Layout"), "Header") in paths and (("Page Setup", "Margins"), "Top") in paths,
              "first_tab_selected_again": w["tab"].get("Page Setup") == "Margins", "drop_down_options_read": (("Page Setup", "Orientation"), "Landscape") in paths,
              "nested_dialog_depth_2_and_3_read": (("Page Setup", "Options"), "Mirror margins") in paths and (("Page Setup", "Options", "Advanced"), "Gutter position") in paths,
              "never_deeper_than_3": not any(lbl == "Too deep" for _p, lbl in paths) and "open Deeper" not in w["events"],
              "each_level_left_by_its_own_cancel": w["events"].count("cancel Advanced") == 1 and w["events"].count("cancel Options") == 1,
              "everything_closed_again": w["stack"] == [] and out["restored"] is True, "depth_reported": rv.deepest == 3 and inside.get("nested") == 1}
    return _verdict(checks, f"events={w['events']}; kind={out['kind']}; inside tabs={inside.get('tabs')} lists={inside.get('lists')} nested={inside.get('nested')}; deepest={rv.deepest}; left_by={out.get('left_by')}")


# ====================================================================================================================== PR69
def run_pr69() -> TestOutcome:
    """PR69: what the person has open never enters the Professor's data (a gallery item that is the title of an open window is not filed); a control that made an application stop responding
    is remembered as a hazard and never clicked again; a live name with '...' or an accelerator is the same control as its catalog label"""
    import tempfile
    from core_organs.professor import privacy as PV, reveal as RV, menus as MN
    from core_organs.professor.executor import _nl
    from core_organs.professor.harvest import Catalog
    from core_organs.professor.schema import fold
    PV._cache.update(t=time.time() + 3600, titles={fold("Quarterly results - draft notes - Notepad"), fold("My bank statement October - Google Chrome")})
    try:
        cat, have = Catalog(app_key="demo"), set()
        filed_private = MN.add_item_verb(cat, have, ["Insert", "Screenshot"], NS(name="Quarterly results - draft notes - Notepad", role="listitem", accel="", help="", enabled=True, selected=False, toggle_state=-1, aid="", pats=[]))
        filed_plain = MN.add_item_verb(cat, have, ["Insert", "Screenshot"], NS(name="Screen Clipping", role="menuitem", accel="", help="", enabled=True, selected=False, toggle_state=-1, aid="", pats=[]))
    finally:
        PV._cache.update(t=0.0, titles=set())
    tmp = tempfile.mkdtemp()
    real = RV._hazards_path
    RV._hazards_path = lambda: os.path.join(tmp, "hazards.json")
    try:
        RV.record_hazard("demo", "Edit colours", "stopped responding")
        hz = RV.load_hazards("demo")
        other = RV.load_hazards("other")
    finally:
        RV._hazards_path = real
    checks = {"open_window_title_not_filed": filed_private is False and not any("Quarterly" in v.label for v in cat.verbs), "ordinary_item_filed": filed_plain is True,
              "browser_title_pattern_private": PV.looks_private("Some page about something - Google Chrome"), "command_not_private": not PV.looks_private("Insert Above"),
              "hazard_remembered_per_app": "Edit colours" in hz and not other, "live_name_equals_label": _nl("This Device...") == _nl("This Device") and _nl("Open\tCtrl+O") == _nl("Open")}
    return _verdict(checks, f"hazards={hz}")


# ====================================================================================================================== PR70
def run_pr70() -> TestOutcome:
    """PR70: the SAME command through another form - a verb the vendor manifest identifies gets the application's object model as its last route rung (also a live verb of the same name),
    a context-menu id is never used, a verb with no id gets no such rung; a disabled step's precondition is matched to a 'create' procedure of the same guide by the object it names"""
    from core_organs.professor.executor import Executor
    from core_organs.professor import apprun as AR
    cat = _cat([(["Home", "Font"], "Bold", "toggle", {"aid": "mso:Bold", "sources": ["vendor-manifest"]}), (["Home", "Font"], "Bold", "button", {"aid": "", "sources": ["uia"]}),
                (["Context menu: Text"], "Paste", "menu_item", {"aid": "mso:PasteMenu", "sources": ["vendor-manifest"]}), (["Home"], "Paste", "button", {"aid": "", "sources": ["uia"]}),
                (["Tools"], "Frobnicate", "button", {"aid": "", "sources": ["uia"]})])
    fx = NS(allowed=True, why_not=lambda: "")
    ex = Executor(1, fx, cat, owned=True)
    ex.object_model = NS(execute=lambda i: (True, "om " + i))
    live_bold = next(v for v in cat.verbs if v.label == "Bold" and not v.aid)
    r_live = [r.kind for r in ex.routes_for(live_bold)]
    r_paste = [r.kind for r in ex.routes_for(next(v for v in cat.verbs if v.label == "Paste" and not v.aid))]
    r_none = [r.kind for r in ex.routes_for(next(v for v in cat.verbs if v.label == "Frobnicate"))]
    ok, how = ex._deliver(live_bold, next(r for r in ex.routes_for(live_bold) if r.kind == "object_model"))
    words = {m.group(1).lower().replace(" ", "") for m in AR.AppRun.OBJECT_WORDS_RX.finditer("Change the color of WordArt text")}
    checks = {"live_verb_gets_object_model_rung_last": r_live[-1] == "object_model" and ex._mso_for(live_bold) == "Bold", "context_menu_id_never_used": "object_model" not in r_paste,
              "no_id_no_rung": "object_model" not in r_none, "delivered_through_model": ok and how == "om Bold",
              "create_procedure_recognised": bool(AR.AppRun.CREATE_RX.search("Insert WordArt in Word")) and not AR.AppRun.CREATE_RX.search("Delete WordArt"), "object_word_found": "wordart" in words}
    return _verdict(checks, f"routes live={r_live} paste={r_paste} none={r_none}")


# ====================================================================================================================== PR71
def run_pr71() -> TestOutcome:
    """PR71: pointer gestures and files - a guide sentence's gesture kind is read from its words; the path stays inside the surface; a path that crosses a link / button (or leaves the run's
    own window) is refused (measured: a stroke ending on a splash-screen link opened the browser); the route comes from MEASURED traits (scripting > posted > touch, touch never where it
    moved the person's cursor); an application's scripting registry becomes catalog verbs; only files the person names are ever chosen; a dialog that takes no type the sandbox can make is
    cancelled, 'All files' is not"""
    import tempfile
    from core_organs.professor import gestures as GE, dialogs as DG
    from core_organs.professor.adapters import script_bridge as SB
    kinds = [GE.kind_of(t) for t in ("Draw on the canvas.", "Orbit the view with the middle mouse button.", "Scroll to zoom in.", "Drag around the area you want to select.",
                                      "Pan the view.", "Drag the layer to the top.")]
    surf = (100, 100, 900, 700)
    pts = GE.path_for("stroke", surf)
    inside = all(surf[0] <= x <= surf[2] and surf[1] <= y <= surf[3] for x, y in pts)
    link = NS(role="hyperlink", name="Get Involved", offscreen=False, rect=(int(pts[10][0]) - 5, int(pts[10][1]) - 5, int(pts[10][0]) + 5, int(pts[10][1]) + 5))
    real_wfp = GE._u
    GE._u = NS(GetAncestor=lambda h, f: 777, WindowFromPoint=lambda p: 1, GetCursorPos=real_wfp.GetCursorPos, GetWindowRect=real_wfp.GetWindowRect)
    try:
        clear_ok, _ = GE.path_is_clear(pts, 777, [], surf)
        link_ok, link_why = GE.path_is_clear(pts, 777, [link], surf)
        other_ok, other_why = GE.path_is_clear(pts, 555, [], surf)
    finally:
        GE._u = real_wfp
    tmp = tempfile.mkdtemp()
    real_tp = GE.TRAITS_PATH
    GE.TRAITS_PATH = os.path.join(tmp, "traits.json")
    try:
        GE.save_trait("a", "scripting", True)
        GE.save_trait("b", "posted_pointer", False)
        GE.save_trait("b", "touch_moves_cursor", True)
        GE.save_trait("c", "touch_moves_cursor", False)
        routes = (GE.gesture_route("a"), GE.gesture_route("b"), GE.gesture_route("c"))
    finally:
        GE.TRAITS_PATH = real_tp
    verbs = SB.registry_verbs([{"id": "mesh.primitive_cube_add", "label": "Add Cube", "desc": "Construct a cube mesh", "module": "mesh"},
                               {"id": "view3d.view_orbit", "label": "Orbit View", "desc": "Orbit the view", "module": "view3d"}, {"id": "x.y", "label": "", "module": "x"}])
    fpath = os.path.join(tmp, "my picture.png")
    open(fpath, "wb").write(b"x")
    named = DG.paths_in(f"insert {fpath} into the slide")
    dd = DG.DialogDriver(NS(allowed=True), 1, DG.Sandbox("t", "s", root=tmp))
    dd.user_files = named
    pic = NS(kind="file_open", filter_exts=["png", "jpg"])
    glb = NS(kind="file_open", filter_exts=["glb", "fbx"])
    anyf = ["glb", "*"]
    checks = {"gesture_kind_from_words": kinds == ["stroke", "orbit", "zoom", "select_area", "pan", "drag"], "path_inside_surface": inside and len(pts) > 10,
              "clear_path_allowed": clear_ok, "path_over_a_link_refused": not link_ok and "Get Involved" in link_why, "path_on_another_window_refused": not other_ok and "another window" in other_why,
              "routes_from_measured_traits": routes[0].startswith("the application's own scripting") and routes[1] == "" and routes[2].startswith("synthetic touch"),
              "registry_becomes_verbs": [v.label for v in verbs] == ["Add Cube", "Orbit View"] and verbs[0].aid == "script:mesh.primitive_cube_add" and verbs[0].sources == ["script-registry"],
              "named_file_found": named == [os.path.abspath(fpath)], "named_file_chosen_for_its_type": dd._user_choice(pic) == os.path.abspath(fpath) and dd._user_choice(glb) == "",
              "unmakeable_type_detected": not (set(glb.filter_exts) & DG.FIXTURE_EXTS) and "*" in anyf}
    return _verdict(checks, f"kinds={kinds}; routes={routes}; link_why={link_why[:60]}")


# ====================================================================================================================== PR81
def run_pr81() -> TestOutcome:
    """PR81: a step whose precondition is not met (nothing to pose / a disabled command) and no guide procedure that creates it - the application's OWN 'Add / New / Insert <thing>'
    command for the thing the task names is run first (all its words wanted beats one wanted word); unsafe / disabled / context-menu commands are never chosen; nothing named -> nothing run"""
    from core_organs.professor import apprun as AR
    cat = _cat([(["Commands", "object"], "Add Armature", "command", {"aid": "script:object.armature_add"}), (["Commands", "poselib"], "Create Pose Asset", "command", {"aid": "script:poselib.create_pose_asset"}),
                (["Commands", "armature"], "Add Bone Collection", "command", {}), (["Context menu: Object"], "Add Armature Modifier", "menu_item", {}),
                (["Window"], "New Window", "command", {}), (["Commands", "anim"], "Add Empty Keying Set", "command", {})])
    next(v for v in cat.verbs if v.label == "Add Empty Keying Set").safety = "unsafe"
    ran = []
    r = AR.AppRun.__new__(AR.AppRun)
    r.cat, r.settle_s, r._precond_note = cat, 0.1, ""
    r.reset_ui = lambda: None
    r.ex = NS(_step_for_verb=lambda v, goal, conf, src: NS(verb=v), run=lambda rep, **k: (ran.append(rep.steps[0].verb.label), setattr(rep, "ok", True)))
    at = NS(results=[{"step": 2, "verb": "Pose Mode", "status": "blocked", "summary": "precondition not met: poll() False"}], why="precondition not met")
    t1 = {"goal": "Pose the armature", "steps": [NS(raw="Select the armature and switch to Pose Mode.")]}
    ok1 = r._create_with_own_command(t1, at)
    first = list(ran)
    t2 = {"goal": "Add an empty keying set", "steps": [NS(raw="Add an empty keying set.")]}
    ok2 = r._create_with_own_command(t2, NS(results=[], why="disabled"))
    t3 = {"goal": "Rotate", "steps": [NS(raw="Rotate it.")]}
    ok3 = r._create_with_own_command(t3, NS(results=[], why="disabled"))
    cat.verbs += _cat([(["Commands", "transform"], "Create Orientation", "command", {})]).verbs
    t4 = {"goal": "Create Orientation", "steps": [NS(raw="Select an armature.", target=""), NS(raw="Click Create Orientation.", target="Create Orientation")]}
    n_before = len(ran)
    r._create_with_own_command(t4, NS(results=[{"verb": "armature", "status": "unknown", "summary": "needs_object: no armature in the scene"}], why="did not create"))
    own_skipped = ran[n_before:] == ["Add Armature"]
    cat.verbs += _cat([(["Commands", "curves"], "Add Circle", "command", {})]).verbs
    n2 = len(ran)
    t5 = {"goal": "Circle Select", "steps": [NS(raw="Select the Circle Select tool.", target="Circle Select"), NS(raw="Click Apply.", target="Apply")]}
    r._create_with_own_command(t5, NS(results=[{"step": 2, "verb": "Apply", "status": "no_effect", "summary": "scripting: file.execute -> precondition not met"}], why="precondition not met"))
    r._create_with_own_command(t5, NS(results=[{"step": 2, "verb": "Apply", "status": "no_effect", "summary": "precondition not met"}], why="precondition not met"))
    goal_words_not_created = len(ran) == n2
    checks = {"own_add_command_run": ok1 and first == ["Add Armature"], "note_says_what_ran": "Add Armature" in r._precond_note, "unsafe_never_chosen": not ok2 and n_before == 1,
              "nothing_named_nothing_run": not ok3 and n_before == 1, "context_menu_skipped": "Add Armature Modifier" not in ran, "own_command_never_its_precondition": own_skipped, "goal_words_and_files_create_nothing": goal_words_not_created}
    return _verdict(checks, f"ran {ran}; note '{r._precond_note}'")


# ====================================================================================================================== PR82
def run_pr82() -> TestOutcome:
    """PR82: a guide's key press that the posted key cannot confirm (a blind window) is rerouted to the command the application's OWN keymap binds to that chord, run by its scripting
    engine (first when the window is blind, after the posted key otherwise); a chord bound to two different commands, an unsafe command, or no bridge -> no reroute"""
    from core_organs.professor.executor import Executor, ExecReport, Step
    cat = _cat([(["Commands", "object"], "Toggle Edit Mode", "command", {"aid": "script:object.editmode_toggle", "shortcut": "Tab"}),
                (["Commands", "view3d"], "Grab", "command", {"aid": "script:transform.translate", "shortcut": "G"}), (["Commands", "graph"], "Grab Keys", "command", {"aid": "script:graph.translate", "shortcut": "G"}),
                (["Commands", "wm"], "Quit", "command", {"aid": "script:wm.quit_blender", "shortcut": "Ctrl+Q"})])
    next(v for v in cat.verbs if v.label == "Quit").safety = "unsafe"
    calls = []
    class FX:
        allowed, app_key, overlay = True, "demo", None

        def __getattr__(self, name):
            return lambda *a, **k: (False, "no")

        def why_not(self):
            return ""

        def holding(self):
            return contextlib.nullcontext()

        def focus_watch(self):
            return contextlib.nullcontext()

        def key(self, k):
            calls.append("posted " + k)
            return True, "posted " + k

    import core_organs.professor.probe as EXM
    fx = FX()
    ex = Executor(1, fx, cat, owned=True)
    no_bridge = ex._keymap_command("Tab")
    ex.script_bridge = NS(fileinfo=lambda a: {}, execute=lambda a: (calls.append("script " + a), (True, f"scripting: {a} -> FINISHED"))[1])
    picks = {k: ("script:" + ex._keymap_command(k)[0] if ex._keymap_command(k) else None) for k in ("tab", "G", "ctrl+q", "F12")}
    ctx = {"Tab": {"ok": True, "id": "object.mode_set", "props": {"mode": "EDIT", "toggle": True}, "kind": "command"}, "Shift+A": {"ok": True, "id": "wm.call_menu", "kind": "menu"},
           "G": {"ok": True, "id": "transform.translate", "kind": "interactive"}}
    ex.script_bridge = NS(key_resolve=lambda c: ctx.get(c, {"ok": False}), fileinfo=lambda a: {},
                          execute=lambda a, props=None: (calls.append(f"script {a} {props or ''}".strip()), (True, f"scripting: {a} -> FINISHED"))[1])
    by_ctx = {k: ex._keymap_command(k) for k in ("tab", "shift+a", "G", "ctrl+q")}
    ex.blind = True
    snap = NS(sig="s", names=[], image=None)
    ex._snap = lambda: snap
    ex._settle = lambda s0, t, **k: snap
    rep = ExecReport(goal="enter edit mode", steps=[Step(0, "Press Tab.", None, "", [], "key", text="tab", safety="safe", routes=["key:tab"], expected="", source="guide")])
    real_delta = EXM.delta
    EXM.delta = lambda a, b: NS(new_windows=[], added=[], effect=lambda: "no_effect", summary=lambda: "nothing changed")
    try:
        ex.run(rep, dry_run=False, settle_s=0.0, learn=False)
    except Exception as exc:                                                    # noqa: BLE001
        import traceback
        rep.stopped = "EXC " + traceback.format_exc()[-400:]
    finally:
        EXM.delta = real_delta
    r0 = rep.results[0] if rep.results else NS(status="none", route="", summary=rep.stopped)
    checks = {"no_bridge_no_reroute": no_bridge is None, "unique_binding_found": picks["tab"] == "script:object.editmode_toggle", "ambiguous_chord_left_alone": picks["G"] is None,
              "unsafe_never": picks["ctrl+q"] is None, "unbound_none": picks["F12"] is None,
              "context_resolves_tab": bool(by_ctx["tab"]) and by_ctx["tab"][0] == "object.mode_set" and by_ctx["tab"][1].get("mode") == "EDIT",
              "menu_and_interactive_left_to_key": by_ctx["shift+a"] is None and by_ctx["G"] is None, "unbound_in_context_falls_back_to_catalog_safety": by_ctx["ctrl+q"] is None,
              "blind_runs_command_first": bool(calls) and calls[0].startswith("script object.mode_set") and r0.status == "done" and str(r0.route).startswith("key:scripting")}
    return _verdict(checks, f"picks {picks}; ctx {by_ctx}; calls {calls}; result {r0.status} via {r0.route}: {str(r0.summary)[:120]}")


# ====================================================================================================================== PR83
def run_pr83() -> TestOutcome:
    """PR83: a control the catalog knows but the screen does not show because the application's own chrome is collapsed (measured: Paint with its tool bar hidden - Pencil and the colours
    'not found') - the application's own 'Show toolbar' / 'Expand ribbon' / 'Open Navigation' is used once, then the control is found; other buttons ('Open settings') are never pressed"""
    from core_organs.professor.executor import Executor
    from core_organs.professor.harvest import Verb
    state = {"shown": False, "pressed": []}
    mk = lambda name, role="button": NS(name=name, role=role, enabled=True, offscreen=False, aid="", pats=["invoke"], rect=(0, 0, 10, 10))
    def nodes():
        base = [mk("Open settings"), mk("Show more"), mk("Show toolbar")]
        return base + ([mk("Pencil")] if state["shown"] else [])
    fx = NS(allowed=True, why_not=lambda: "", holding=contextlib.nullcontext, node=lambda n: (state["pressed"].append(n.name), state.__setitem__("shown", state["shown"] or n.name == "Show toolbar"), (True, "invoked " + n.name))[2])
    cat = _cat([(["Tools"], "Pencil", "button", {})])
    ex = Executor(1, fx, cat, owned=True)
    ex._all_nodes = nodes
    ex._live_node = lambda v: next((n for n in nodes() if n.name == v.label), None)
    ex._open_path = lambda v: False
    ex._enter_context = lambda v: ""
    v = cat.verbs[0]
    ok, how = ex._deliver(v, next(r for r in ex.routes_for(v) if r.kind == "control"))
    first_two = list(state["pressed"])
    for _ in range(6):
        ex._reveal_hidden_ui()
    checks = {"control_found_after_reveal": ok and "Pencil" in how, "only_the_reveal_control_pressed": first_two == ["Show toolbar", "Pencil"] and set(state["pressed"]) == {"Show toolbar", "Pencil"},
              "capped_per_run": state["pressed"].count("Show toolbar") == 4, "logged_for_restore": ex.revealed_log == ["Show toolbar"]}
    return _verdict(checks, f"pressed {state['pressed']}; {how}")


# ====================================================================================================================== PR84
def run_pr84() -> TestOutcome:
    """PR84: guide pages that lost their separators and procedures that leave the application - 'Bookmarks and lists Bookmark manager' (arrow icons dropped) is split into the catalog's
    menu path; once a procedure moves into another program (the registry editor), its next steps that name nothing of this application are counted outside, not as failures"""
    from core_organs.professor.knowledge import guide_steps as G
    cat = _cat([(["More"], "Bookmarks and lists", "menu_item", {"leads_to": "menu"}), (["More", "Bookmarks and lists"], "Bookmark manager", "menu_item", {}),
                (["More"], "Settings", "menu_item", {}), (["Help"], "About", "menu_item", {})])
    v1, s1, p1 = G.split_run_together(cat, "Bookmarks and lists Bookmark manager")
    v2, _s2, _p2 = G.split_run_together(cat, "Bookmarks and listsBookmark Manager")
    v3, _s3, _p3 = G.split_run_together(cat, "Change theme")
    steps = [G.GuideStep(1, "Open the Registry Editor."), G.GuideStep(2, "In the folder look for a key called **Thing**.", target="Thing"),
             G.GuideStep(3, "Set its value to 0.", target="value")]
    try:
        gs = G.ground(steps, cat, app_words=("demo",))
        hows = [g.how for g in gs]
    except Exception as exc:                                                    # noqa: BLE001
        hows = ["EXC " + repr(exc)[:120]]
    checks = {"split_into_path": v1 is not None and v1.label == "Bookmark manager", "camel_join_split": v2 is not None and v2.label == "Bookmark manager", "no_false_split": v3 is None,
              "other_program_steps_outside": hows == ["outside", "outside", "outside"]}
    return _verdict(checks, f"split {p1} ({s1}); hows {hows}")


# ====================================================================================================================== PR85
def run_pr85() -> TestOutcome:
    """PR85: 'select an object or mesh element(s)' in an application with a scripting engine is no longer a human's step - the engine selects one of the document's OWN objects of that kind
    (route 'scripting'); none of that kind -> 'needs_object' (the run then creates one with the application's own Add command); without an engine the step stays a named refusal"""
    from core_organs.professor.executor import Executor, Step
    from core_organs.professor.knowledge.guide_steps import GuideStep
    cat = _cat([(["Commands", "object"], "Add Armature", "command", {"aid": "script:object.armature_add"})])
    fx = NS(allowed=True, why_not=lambda: "")
    ex = Executor(1, fx, cat, owned=True)
    plain = ex._content_step(GuideStep(1, "Select an object or mesh element(s)."), "c")
    have = {"mesh": True, "armature": False}
    ex.script_bridge = NS(select_object=lambda k: (True, f"scripting: selected and made active: Cube ({k})") if have.get("armature" if "armature" in k else "mesh") else (False, f"needs_object: no {k} in the scene"))
    st1 = ex._content_step(GuideStep(1, "Select an object or mesh element(s)."), "c")
    st2 = ex._content_step(GuideStep(2, "Select the armature."), "c")
    snap = NS(sig="s", names=[], image=None)
    ex._snap = lambda: snap
    ex._settle = lambda s0, t, **k: snap
    import core_organs.professor.probe as PB
    real = PB.delta
    PB.delta = lambda a, b: NS(new_windows=[], added=[], effect=lambda: "no_effect", summary=lambda: "nothing changed")
    try:
        r1 = ex._select_object(st1, 0.0)
        r2 = ex._select_object(st2, 0.0)
        ex._last = (snap, snap, NS(effect=lambda: "no_effect", summary=lambda: "nothing changed", new_windows=[], added=[]))
        ex._after_step(st1, r1)
    finally:
        PB.delta = real
    checks = {"already_selected_stays_verified": r1.verified is True, "without_engine_a_named_refusal": plain.kind == "unknown", "engine_makes_it_an_object_step": st1.kind == "object" and st2.kind == "object",
              "selected_through_engine": r1.status == "done" and r1.route == "scripting", "none_of_kind_needs_object": r2.status == "unknown" and r2.summary.startswith("needs_object")}
    return _verdict(checks, f"plain {plain.kind}; st1 {st1.kind}/{st1.text}; r1 {r1.status} {r1.route}; r2 {r2.status} {r2.summary[:60]}")


# ====================================================================================================================== PR86
def run_pr86() -> TestOutcome:
    """PR86: commands of the SAME name in several editors ('Select Box' of the Info editor / of the 3D viewport) - the one the engine's poll() says can run now is used (measured: the Info
    editor's ran and did nothing); when the chosen one can run, or nothing can tell, it is kept"""
    from core_organs.professor.executor import Executor
    cat = _cat([(["Commands", "info"], "Select Box", "command", {"aid": "script:info.select_box"}), (["Commands", "view3d"], "Select Box", "command", {"aid": "script:view3d.select_box"}),
                (["Commands", "node"], "Select Box", "command", {"aid": "script:node.select_box"}), (["Commands", "object"], "Join", "command", {"aid": "script:object.join"})])
    ran = []
    live = {"info.select_box": False, "view3d.select_box": True, "node.select_box": False, "object.join": True}
    ex = Executor(1, NS(allowed=True, why_not=lambda: ""), cat, owned=True)
    ex.script_bridge = NS(polls=lambda ids: {i: live.get(i, False) for i in ids}, fileinfo=lambda a: {}, execute=lambda a, props=None: (ran.append(a), (True, a + " -> FINISHED"))[1])
    v_info = cat.verbs[0]
    ex._script_command("info.select_box", v_info)
    ex._script_command("object.join", cat.verbs[3])
    live["info.select_box"] = True
    ex._script_command("info.select_box", v_info)
    ran2 = []
    ex.script_bridge = NS(polls=lambda ids: {i: True for i in ids}, fileinfo=lambda a: {},
                          execute=lambda a, props=None: (ran2.append(a), (True, a + " -> FINISHED") if a == "view3d.select_box" else (False, f"scripting: {a} -> precondition not met: poll() False"))[1])
    ok_f, how_f = ex._script_command("info.select_box", v_info)
    checks = {"runnable_namesake_used": ran[0] == "view3d.select_box", "no_twin_kept": ran[1] == "object.join", "runnable_choice_kept": ran[2] == "info.select_box",
              "refused_command_falls_to_namesake": ok_f and ran2[:2] == ["info.select_box", "view3d.select_box"]}
    return _verdict(checks, f"ran {ran}")


# ====================================================================================================================== PR87
def run_pr87() -> TestOutcome:
    """PR87: a PARKED window whose provider computes IsOffscreen against the monitors (measured: Settings - 215 of 224 nodes 'offscreen', zero-size, yet UIA Select on them works)
    gets its flags re-read against the window itself: zero-size and inside-the-window nodes are present, outside-the-window ones stay offscreen; a window that is not parked,
    or one where only a few nodes carry the flag, is left exactly as the provider said"""
    from core_organs.professor import executor as X
    from core_organs import background_window as bw
    mk = lambda name, rect, off=True: NS(name=name, rect=rect, offscreen=off)
    def tree():
        return [mk(f"item{i}", (0, 0, 0, 0)) for i in range(12)] + [mk("scrolled away", (-30000, -30000, -29900, -29980)), mk("inside", (-23990, -23990, -23900, -23950)),
                                                                       mk("frame button", (-23000, -24000, -22950, -23960), False)]
    real_p, real_r = bw.is_parked, bw._rect
    bw._rect = lambda h: (-24000, -24000, -22700, -22990)
    try:
        bw.is_parked = lambda h: True
        a = tree(); n_a = X._offscreen_by_window(1, a)
        bw.is_parked = lambda h: False
        b = tree(); n_b = X._offscreen_by_window(1, b)
        bw.is_parked = lambda h: True
        c = [mk("x", (0, 0, 0, 0))] + [mk(f"v{i}", (-23990, -23990, -23900, -23950), False) for i in range(14)]; n_c = X._offscreen_by_window(1, c)
    finally:
        bw.is_parked, bw._rect = real_p, real_r
    by = {n.name: n.offscreen for n in a}
    checks = {"zero_size_present": not by["item0"] and n_a == 13, "inside_present": not by["inside"], "outside_stays_offscreen": by["scrolled away"],
              "not_parked_untouched": n_b == 0 and all(n.offscreen for n in b[:12]), "few_flags_untouched": n_c == 0 and c[0].offscreen}
    return _verdict(checks, f"fixed {n_a} / {n_b} / {n_c}")


# ====================================================================================================================== PR88
def run_pr88() -> TestOutcome:
    """PR88: TRIGGER BUTTONS - when every ordinary route of a guide step fails, the same command filed elsewhere is tried once and, with a SEEN effect, kept as a trigger that is tried
    FIRST next time; two failures in a row retire it; at most N per run / per application; never for unsafe commands, never for a step that is not the guide's"""
    import tempfile
    from core_organs.professor import executor as X, triggers as TR
    import core_organs.professor.probe as PB
    from core_organs.professor.executor import Executor, ExecReport, Step
    cat = _cat([(["Header & Footer", "Header"], "Edit Header", "button", {}), (["Insert", "Header & Footer", "Header"], "Edit Header", "button", {}),
                (["Tools"], "Erase Everything", "button", {})])
    hidden, twin, danger = cat.verbs
    danger.safety = "unsafe"
    state = {"n": 0, "twin_works": True}
    nodes = {twin.id: NS(name="Edit Header", role="button", enabled=True, offscreen=False, rect=(0, 0, 10, 10), pats=["invoke"], selected=None, aid="")}
    fx = NS(allowed=True, why_not=lambda: "", holding=contextlib.nullcontext, focus_watch=contextlib.nullcontext,
            node=lambda n: (state.__setitem__("n", state["n"] + (1 if state["twin_works"] else 0)), (True, "UIA Invoke"))[1])
    ex = Executor(1, fx, cat, owned=True)
    ex._live_node = lambda v: nodes.get(v.id)
    ex._open_path = lambda v: False
    ex._enter_context = lambda v: ""
    ex._reveal_hidden_ui = lambda: ""
    ex._all_nodes = lambda: []
    ex._snap = lambda: NS(sig=str(state["n"]), names=[], image=None, windows=())
    ex._settle = lambda s0, t, **k: NS(sig=str(state["n"]), names=[], image=None, windows=())
    tmp = tempfile.mkdtemp()
    real_delta = PB.delta
    PB.delta = lambda a, b: NS(new_windows=[], added=[], effect=lambda: "no_effect" if a.sig == b.sig else "state_change", summary=lambda: "changed" if a.sig != b.sig else "nothing changed")
    def run(v, source="guide"):
        st = ex._step_for_verb(v, "do it", 0.9, source)
        rep = ExecReport(goal="g", steps=[st])
        ex.run(rep, dry_run=False, settle_s=0.0, learn=False)
        return rep.results[0] if rep.results else NS(status="none", route="", summary=rep.stopped)
    try:
        ex.triggers = TR.TriggerBank("demo", path=os.path.join(tmp, "demo.json"))
        r_not_guide = run(hidden, source="exec")
        r1 = run(hidden)
        bank2 = TR.TriggerBank("demo", path=os.path.join(tmp, "demo.json"))
        ex.triggers = bank2
        r2 = run(hidden)
        state["twin_works"] = False
        run(hidden); run(hidden)
        retired = bank2.get(hidden) is None
        r_unsafe_why = bank2.may_create(danger)
        bank2.new_this_run = TR.MAX_NEW_PER_RUN
        r_cap_why = bank2.may_create(twin)
    finally:
        PB.delta = real_delta
    checks = {"not_for_non_guide_steps": r_not_guide.status != "done", "created_after_all_routes_failed": r1.status == "done" and str(r1.route).startswith("trigger:"),
              "persisted_and_tried_first": r2.status == "done" and str(r2.route).startswith("trigger:") and "trigger " in (r2.tried[0] if r2.tried else ""),
              "retired_after_two_failures": retired, "never_unsafe": bool(r_unsafe_why), "capped_per_run": bool(r_cap_why)}
    return _verdict(checks, f"r1 {r1.status} {r1.route} {getattr(r1, 'tried', None)}; r2 {r2.status} {r2.route}; unsafe: {r_unsafe_why}; cap: {r_cap_why}")


# ====================================================================================================================== PR89
def run_pr89() -> TestOutcome:
    """PR89: the remaining generic gaps - a CONTEXTUAL tab with no command of its name is entered through the 'Edit ...' command of the same-named group on another tab (also when the
    step names the tab itself); 'Format Text Effects' is formatting, 'Format Drive' is not; a stored catalog is re-classified when loaded; an exploration of the SAME build within
    the reuse window is carried in instead of walked again (another build, or an old one, is explored)"""
    import tempfile, json as _json
    from core_organs.professor import safety as SF, harvest as HV, apprun as AR
    from core_organs.professor.executor import Executor
    cat = _cat([(["Header & Footer", "Options"], "Different First Page", "checkbox", {}), (["Insert", "Header & Footer", "Header"], "Edit Header", "button", {}),
                (["File", "Open"], "Open Recent", "button", {}), ([], "Header & Footer", "tab", {})])
    ex = Executor(1, NS(allowed=True, why_not=lambda: ""), cat, owned=True)
    live = {"tab": False}
    ex._tab_live = lambda t: live["tab"]
    tried = []
    def deliver(v, r):
        tried.append(v.label)
        live["tab"] = v.label == "Edit Header"
        return True, "ok"
    ex._deliver = deliver
    real_sleep = AR.time.sleep
    e1 = ex._enter_context(cat.verbs[0])
    live["tab"] = False
    e2 = ex._enter_context(cat.verbs[3])
    fmt = {k: SF.classify(k) for k in ("Format Text Effects", "Format Painter", "Format Drive", "Delete")}
    tmp = tempfile.mkdtemp()
    stored = {"app_key": "demo", "verbs": [{"id": "1", "label": "Format Text Effects", "path": ["Home"], "safety": "unsafe"}, {"id": "2", "label": "Thing", "path": [], "safety": "unknown"}]}
    re_cat = HV.Catalog.from_dict(stored)
    real_dir = HV.CATALOG_DIR
    HV.CATALOG_DIR = tmp
    try:
        def make(ver, age_days, notes=True, flag="|complete"):
            c = _cat([(["Home"], f"V{i}", "button", {"sources": ["ribbon"]}) for i in range(12)])
            c.app_key = "demo"
            c.notes = [f"explored|16.0.1|{int(time.time() - age_days * 86400)}{flag}"] if notes else []
            c.save(os.path.join(tmp, "demo.json"))
            r = AR.AppRun.__new__(AR.AppRun)
            r.spec, r.report, r._no_reveal = NS(key="demo"), {"phases": {}}, False
            r.ui = NS(phase=lambda *a, **k: None)
            r._exe_version = lambda: ver
            return r, r._reuse_exploration()
        ok_r, same = make("16.0.1", 1)
        _r2, other_build = make("16.0.2", 1)
        _r3, too_old = make("16.0.1", 30)
        _r4, unstamped = make("16.0.1", 1, notes=False)
        part_r, partial = make("16.0.1", 1, flag="|partial")
    finally:
        HV.CATALOG_DIR = real_dir
    checks = {"group_entry_command_enters_the_mode": bool(e1) and "Edit Header" in tried and "Open Recent" not in tried, "tab_step_enters_too": bool(e2),
              "format_is_formatting": fmt["Format Text Effects"] == "safe" and fmt["Format Painter"] == "safe", "format_drive_unsafe": fmt["Format Drive"] == "unsafe" and fmt["Delete"] == "unsafe",
              "stored_catalog_reclassified": re_cat.verbs[0].safety == "safe" and re_cat.verbs[1].safety == "unknown",
              "same_build_reused": len(same) == 12 and ok_r._no_reveal and "reused_exploration" in ok_r.report["phases"],
              "other_build_old_or_unstamped_explored": not other_build and not too_old and not unstamped,
              "partial_is_carried_and_continued": len(partial) == 12 and not getattr(part_r, "_reused", None) and not part_r._no_reveal}
    return _verdict(checks, f"entered: {e1} | {e2}; fmt {fmt}; reuse {len(same)}/{len(other_build)}/{len(too_old)}/{len(unstamped)}")


# ====================================================================================================================== PR90
def run_pr90() -> TestOutcome:
    """PR90: the checkpoint machinery - a vision name AGREES with the application's own name only when it means it; 'the gear icon' grounds to the settings control and a
    pronoun step ('uncheck it') to the previous step's control; British and American spellings are one word; a command the guide BOLDS gets that cited sentence as its
    explanation (a word merely used in passing does not); the outcome model reads what happened to the same control before; the scorecard marks a missing number n/a, not passed"""
    import tempfile, json as _json
    from core_organs.professor import symbol_eval as SE, scorecard as SC
    from core_organs.professor.knowledge import guide_steps as G, guide_explain as GX
    from core_organs.professor.ml.outcome import OutcomeModel
    agree = {"bold": SE.agree("Bold (Ctrl+B)", "Bold"), "wrong": SE.agree("Bold", "Italic"), "empty": SE.agree("Underline", "")}
    cat = _cat([([], "Open settings", "button", {}), (["Options"], "Read-only", "checkbox", {}), (["Home"], "Edit colours", "button", {})])
    iv, _w = G.icon_noun(cat, "Click the gear icon in the corner.")
    steps = [G.GuideStep(1, "Select **Read-only**.", target="Read-only"), G.GuideStep(2, "uncheck it.")]
    gs = G.ground(steps, cat)
    spelled = G._words_eq("Edit colors", "Edit colours")
    ix = NS(_load=lambda key: {"rows": [(1, "Options > General", "Select **Read-only** to keep others from changing the file. The read-only file is shared."), (2, "x", "Colours are nice.")]})
    c2 = _cat([(["Options"], "Read-only", "checkbox", {}), (["Home"], "Colours", "button", {})])
    er = GX.enrich(c2, ix, "demo")
    m = OutcomeModel(path=None)
    ctx = {"app": "a", "toolkit": "t", "role": "button", "route": "control", "label": "Bold"}
    m.observe(ctx, "state_change", True)
    seen = m.with_history(ctx)
    tmp = tempfile.mkdtemp()
    rp = os.path.join(tmp, "report.json")
    _json.dump({"app": "demo", "phases": {}, "tasks": [{"final": "ok"}, {"final": "failed"}, {"final": "blocked"}]}, open(rp, "w"))
    sc = SC.score(rp)
    c7 = next(r for r in sc["rows"] if r["id"] == "C7")
    c1 = next(r for r in sc["rows"] if r["id"] == "C1")
    checks = {"vision_agreement_scored": agree["bold"] and not agree["wrong"] and not agree["empty"], "icon_noun_grounds": iv is not None and iv.label == "Open settings",
              "pronoun_refers_back": gs[1].verb is not None and gs[1].verb.label == "Read-only", "spellings_one_word": spelled,
              "bold_sentence_explains": "Read-only" in (c2.verbs[0].desc or "") and "guide:" in c2.verbs[0].desc and not c2.verbs[1].desc and er["added"] == 1,
              "outcome_history_feature": seen.get("hist_lr") == (1, 1), "scorecard_counts_blocked_out": c7["percent"] == 50.0, "scorecard_missing_is_na": c1["percent"] is None and not c1["passed"]}
    return _verdict(checks, f"agree {agree}; icon {iv.label if iv else None}; pronoun {gs[1].how}; explain {er}; hist {seen.get('hist_lr')}; C7 {c7['percent']}")


TESTS = [("PR90", run_pr90), ("PR89", run_pr89), ("PR88", run_pr88), ("PR87", run_pr87), ("PR86", run_pr86), ("PR85", run_pr85), ("PR84", run_pr84), ("PR83", run_pr83), ("PR82", run_pr82), ("PR81", run_pr81), ("PR71", run_pr71), ("PR70", run_pr70), ("PR69", run_pr69), ("PR63", run_pr63), ("PR64", run_pr64), ("PR65", run_pr65), ("PR66", run_pr66), ("PR67", run_pr67), ("PR68", run_pr68)]
