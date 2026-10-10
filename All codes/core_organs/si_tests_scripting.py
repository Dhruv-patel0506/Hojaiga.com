"""
si_tests_scripting -- offline tests for the application-scripting route's Blender-class capabilities (registered into the Professor suite):

  PR78  task or reference? (professor.knowledge.task_like): instructions with a result outrank definitions of menu entries / regions
  PR79  settings as catalog verbs: panels' properties at the path they are drawn at, one verb per choice, private strings left out; a setting is set by key / choice / value
  PR80  file commands inside the sandbox only: a command that takes a file gets a fixture to read or the outbox to write (never the application's own file browser), the bridge's answers
        (needs a file / precondition not met / refused) become honest results
No application, no window, no network: the bridge is replaced by a recording stand-in.
"""

from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace as NS

for _p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except Exception:                                        # pragma: no cover
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore


def _step(raw, action="click", target="", path=None, chord=""):
    return NS(raw=raw, action=action, target=target, path=path or [], chord=chord, text="")


# ------------------------------------------------------------------------------------------------------------------------------------------ PR78
def run_pr78() -> "TestOutcome":
    """PR78: a procedure is a TASK (instructions with a result) or REFERENCE (what a menu entry / region means): the scorer ranks tasks above reference and says why"""
    from core_organs.professor.knowledge import task_like as TL
    task = {"goal": "Creating a Slow-Motion Effect", "cite": "Speed Control Strip > Examples > Creating a Slow-Motion Effect",
            "steps": [_step("Select the clip and add an effect strip.", "select", "clip"), _step("Then set the speed factor to 0.5.", "set", "speed"), _step("Now press Space to play and you will see the slowed clip.", "press")],
            "text": "1. Select the clip and add an effect strip. 2. Then set the speed factor to 0.5. 3. Now press Space to play; you will see the slowed clip."}
    ref = {"goal": "File Menu", "cite": "Topbar > Menus > File Menu",
           "steps": [_step("Open Allows opening an existing blend-file.", "open", "Open"), _step("Save Allows saving the current file.", "click", "Save")],
           "text": "Open Allows opening an existing blend-file. Save Allows saving the current file. Show Displays the options."}
    region = {"goal": "Interactive Region", "cite": "Splash Screen > Interactive Region", "steps": [_step("Open Opens a file browser.", "open", "Open")], "text": "Open Opens a file browser."}
    one_line = {"goal": "Using UV Maps", "cite": "Using UV Maps", "steps": [_step("Click the Add button.", "click", "Add")], "text": "Click the Add button."}
    s_task, s_ref, s_reg, s_one = (TL.task_score(x) for x in (task, ref, region, one_line))
    items = [("task", task), ("ref", ref), ("region", region)]
    ranked = [n for n, x in sorted(items, key=lambda kv: -TL.task_score(kv[1]))]
    checks = {"task_scores_high": s_task >= TL.TASK_THRESHOLD + 0.2, "reference_scores_low": s_ref < TL.TASK_THRESHOLD and s_reg < TL.TASK_THRESHOLD,
              "tasks_rank_first": ranked[0] == "task", "a_single_instruction_still_counts": s_one >= 0.0 and s_one < s_task,
              "reason_is_given": "interface" in TL.explain(region) or "reference" in TL.explain(ref) or "few lines" in TL.explain(ref)}
    return _verdict(checks, f"task={s_task:.2f} file-menu={s_ref:.2f} region={s_reg:.2f} one-line={s_one:.2f}; why(region)='{TL.explain(region)}'")


# ------------------------------------------------------------------------------------------------------------------------------------------ PR79
def run_pr79() -> "TestOutcome":
    """PR79: settings become catalog verbs at the path they are drawn at (one verb per choice, private strings left out) and are set by key / choice / value; booleans flip when no value is named"""
    from core_organs.professor.adapters import script_bridge as SB
    items = [{"key": "p1", "id": "language", "label": "Language", "ui_name": "Language", "type": "ENUM", "readonly": False, "desc": "Language used for translation",
              "path": ["Preferences", "Interface", "Translation"], "items": [{"id": "en_US", "label": "English (US)"}, {"id": "fr_FR", "label": "French"}], "value": "en_US"},
             {"key": "p2", "id": "use_auto_save", "label": "Auto Save", "ui_name": "Auto Save", "type": "BOOLEAN", "readonly": False, "desc": "", "path": ["Preferences", "Save & Load"], "value": True},
             {"key": "p3", "id": "temp_dir", "label": "Temporary Files", "ui_name": "Temporary Files", "type": "STRING", "readonly": False, "desc": "", "path": ["Preferences", "File Paths"], "value": "C:/x"},
             {"key": "p4", "id": "version", "label": "Version", "ui_name": "Version", "type": "STRING", "readonly": True, "desc": "", "path": ["Preferences"], "value": "5"},
             {"key": "p5", "id": "region", "label": "Region", "ui_name": "Region", "type": "POINTER", "readonly": False, "desc": "", "path": ["Preferences"], "value": None}]
    verbs = SB.prop_verbs(items)
    labels = [(v.label, v.aid, v.role) for v in verbs]
    calls = []

    class _Fake(SB.ScriptBridge):
        def __init__(self):
            super().__init__(1, "t", "")

        def request(self, what, timeout=20.0, **kw):
            calls.append((what, kw))
            if what == "rna_get":
                return {"ok": True, "value": True}
            return {"ok": True, "note": f"{kw.get('key')} -> {kw.get('value')}", "value": kw.get("value")}
    b = _Fake()
    r_choice = b.apply_setting("p1=fr_FR", "")
    r_value = b.apply_setting("p2", "off")
    r_flip = b.apply_setting("p2", "")
    sets = [kw.get("value") for w, kw in calls if w == "rna_set"]
    checks = {"language_verb_at_its_path": any(v.label == "Language" and v.path == ["Preferences", "Interface", "Translation"] and v.aid == "script:rna:p1" and v.role == "dropdown" for v in verbs),
              "one_verb_per_choice": [(v.label, v.aid) for v in verbs if v.path[-1:] == ["Language"]] == [("English (US)", "script:rna:p1=en_US"), ("French", "script:rna:p1=fr_FR")],
              "boolean_is_a_checkbox": any(v.label == "Auto Save" and v.role == "checkbox" for v in verbs),
              "path_like_strings_left_out": not any(v.label == "Temporary Files" for v in verbs), "read_only_and_pointers_left_out": not any(v.label in ("Version", "Region") for v in verbs),
              "choice_sets_that_choice": sets[0] == "fr_FR", "value_is_passed": sets[1] == "off", "no_value_flips_a_boolean": sets[2] is False and r_flip[0],
              "all_marked_as_settings": all("script-properties" in v.sources for v in verbs)}
    return _verdict(checks, f"verbs={labels}; calls={[c[0] for c in calls]}")


# ------------------------------------------------------------------------------------------------------------------------------------------ PR80
def run_pr80() -> "TestOutcome":
    """PR80: a command that takes a file gets a sandbox file (fixture to read / outbox to write), never the application's own file browser; the bridge's refusals become honest results"""
    from core_organs.professor import executor as X, dialogs as DG
    from core_organs.professor.adapters import script_bridge as SB
    tmp = tempfile.mkdtemp(prefix="hojaiga_scr_")
    sb = DG.Sandbox("t", "s", root=os.path.join(tmp, "sandbox"))
    log = []

    class _Bridge(SB.ScriptBridge):
        def __init__(self):
            super().__init__(1, "t", "")
            self.info = {"wm.open_mainfile": {"path_props": ["filepath"], "exts": ["blend"], "direction": "open"}, "wm.obj_import": {"path_props": ["filepath"], "exts": ["obj"], "direction": "open"},
                         "wm.save_as_mainfile": {"path_props": ["filepath"], "exts": ["blend"], "direction": "save"}, "view3d.view_all": {"path_props": []}}

        def request(self, what, timeout=20.0, **kw):
            log.append((what, kw))
            if what == "fileinfo":
                return {"ok": True, **self.info.get(kw["id"], {"path_props": []})}
            if what == "execute":
                if kw["id"] == "screen.redo_last":
                    return {"ok": False, "precondition": True, "note": "not available in the current state (its poll() is False)"}
                if kw["id"] == "wm.window_new":
                    return {"ok": False, "refused": True, "note": "refused: 'wm.window_new' would open another window"}
                if kw["id"] == "wm.open_mainfile" and not kw.get("props"):
                    return {"ok": False, "needs_path": True}
                return {"ok": True, "note": "{'FINISHED'}"}
            if what == "save_copy":
                open(kw["path"], "wb").write(b"BLENDER")
                return {"ok": True, "note": "{'FINISHED'}"}
            return {"ok": True}
    ex = X.Executor.__new__(X.Executor)
    ex.script_bridge, ex.sandbox = _Bridge(), sb
    o_ok, o_how = ex._script_command("wm.open_mainfile", NS(label="Open"))
    i_ok, i_how = ex._script_command("wm.obj_import", NS(label="Import Wavefront OBJ"))
    s_ok, s_how = ex._script_command("wm.save_as_mainfile", NS(label="Save As"))
    plain_ok, _ = ex._script_command("view3d.view_all", NS(label="Frame All"))
    pre_ok, pre_how = ex.script_bridge.execute("screen.redo_last")
    ref_ok, ref_how = ex.script_bridge.execute("wm.window_new")
    np_ok, np_how = ex.script_bridge.execute("wm.open_mainfile")
    execs = [kw for w, kw in log if w == "execute" and kw.get("props")]
    paths = [list(kw["props"].values())[0] for kw in execs]
    checks = {"open_gets_a_blend_copy_in_the_inbox": o_ok and paths[0].startswith(sb.inbox) and paths[0].endswith(".blend") and os.path.isfile(paths[0]),
              "import_gets_a_generated_fixture": i_ok and paths[1].startswith(sb.inbox) and paths[1].endswith(".obj") and os.path.getsize(paths[1]) > 20,
              "save_goes_to_the_outbox_with_the_right_type": s_ok and paths[2].startswith(sb.outbox) and paths[2].endswith(".blend"),
              "every_path_is_inside_the_sandbox": all(sb.inside(p) for p in paths), "plain_command_runs_as_is": plain_ok,
              "precondition_is_reported_as_such": (not pre_ok) and "precondition not met" in pre_how,
              "window_command_is_a_policy_refusal": (not ref_ok) and ref_how.startswith("refused"),
              "no_path_means_needs_a_file": (not np_ok) and "needs a file" in np_how,
              "a_parenthesis_or_a_property_called_location_is_not_a_file_step": (not DG.is_file_step_text("select one base strip (image, movie, or scene) by LMB click"))
              and (not DG.is_file_step_text("Choose which of the Location/Rotation/Scale to fix")) and DG.is_file_step_text("Choose a location to save the file") and DG.is_file_step_text("Select the file you want")}
    return _verdict(checks, f"paths={[os.path.relpath(p, sb.root) for p in paths]}; pre='{pre_how[:70]}'")


TESTS = [("PR78", run_pr78), ("PR79", run_pr79), ("PR80", run_pr80)]
