"""Offline smoke test for harvest_video_guides: caption de-rolling, regex extraction,
schema normalisation and hostile-model-output parsing. No network, no model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harvest_video_guides as H  # noqa: E402

fails = []


def check(name, got, want):
    ok = got == want
    print(("  PASS  " if ok else "  FAIL  ") + name + f"  got={got!r}")
    if not ok:
        fails.append(name)


# 1) rolling auto-captions must not print the same words three times
rolling = [
    {"start": 0, "end": 2, "text": "Okay so first we open the"},
    {"start": 2, "end": 4, "text": "first we open the File menu and"},
    {"start": 4, "end": 6, "text": "File menu and click Save As"},
]
check("rolling_captions", [c["text"] for c in H.dedupe_rolling(rolling)],
      ["Okay so first we open the", "File menu and", "click Save As"])

# 2) regex extraction of a typical narration
narration = ("First, click the blue Export button. Then type hello world into the Name field. "
             "Go to File > Save As and press Ctrl+S. Now select the Summary tab and wait a moment.")
got = [(s["action"], s["target_text"], s["value"]) for s in H.rules_extract(narration)["steps"]]
print("  rules produced:", got)
acts = [g[0] for g in got]
check("has_type", "type" in acts, True)
check("has_key", "key" in acts, True)
check("has_click", "click" in acts, True)

# 3) normalisation into the executor schema
chunk = {"t0": 0, "t1": 5, "narration": narration, "frame": "x.jpg", "kind": "stride"}
steps = H.normalise_steps(H.rules_extract(narration), chunk, "Excel", 0)
trip = [(s["virtual_mouse_action"]["action_type"], s["ui_target"]["element_name"],
         s["virtual_mouse_action"].get("text_payload"), s["provenance"]["executable"])
        for s in steps]
print("  normalised:", trip)
check("all_known_actions",
      all(s["virtual_mouse_action"]["action_type"] in (H.VALID_ACTIONS | {"SCROLL", "WAIT", "OBSERVE"})
          for s in steps), True)
check("type_has_payload",
      any(s["virtual_mouse_action"]["action_type"] == "TYPE_TEXT"
          and s["virtual_mouse_action"].get("text_payload") for s in steps), True)
check("click_needs_target",
      all(s["ui_target"]["element_name"] for s in steps
          if s["virtual_mouse_action"]["action_type"] == "CLICK"), True)
# the executor builds a chord from modifiers + "key", so that is the field we must fill
keys = [s for s in steps if s["virtual_mouse_action"]["action_type"] == "KEY_COMBINATION"]
check("key_field_matches_executor",
      (keys[0]["virtual_mouse_action"]["key"], keys[0]["virtual_mouse_action"]["modifiers"])
      if keys else None, ("s", ["ctrl"]))
drag = H.normalise_steps({"steps": [{"action": "drag", "target_text": "File box"}]}, chunk, "Excel", 0)
check("drag_not_actuable_from_video", drag[0]["provenance"]["executable"], False)

# 4) hostile model output
prose = 'Sure! {"steps": [{"action":"click","target_text":"Save"}]} hope that helps'
check("json_in_prose", (H.extract_json(prose) or {}).get("steps")[0]["target_text"], "Save")
fenced = '```json\n{"steps":[]}\n```'
check("json_in_fence", len((H.extract_json(fenced) or {}).get("steps", "x")), 0)
check("json_absent", H.extract_json("no json here"), None)
check("json_brace_in_string", (H.extract_json('{"a":"x{y}z","steps":[]}') or {}).get("a"), "x{y}z")

# 5) key combos + target cleaning
check("combo_three", H.split_combo("Ctrl+Shift+Esc"), (["ctrl", "shift"], "esc"))
check("combo_cmd", H.split_combo("cmd s"), (["win"], "s"))
check("clean_adjective", H.obj_clean("blue Export button"), "Export button")
check("clean_clause", H.obj_clean("Summary tab and wait a moment"), "Summary tab")
check("clean_compound_kept", H.obj_clean("Text to Speech"), "Text to Speech")
check("clean_leading", H.obj_clean("the little Plus sign"), "Plus sign")
check("clean_position_kept", H.obj_clean("Right Align button"), "Right Align button")

# 6) split + dedupe helpers
check("dhash_identical", H.hamming(12345, 12345), 0)
check("scale_escape", H.scale_vf(720), "scale=-2:min(720\\,ih)")
rows = [{"chunk": 0, "segment": "new_task", "task": "A", "steps": steps[:2]},
        {"chunk": 1, "segment": "continue", "task": "B", "steps": steps[:1]}]
tasks, dropped, deduped = H.split_for_tasks(rows, 35, keep_nonexec=False, min_steps=1)
check("task_split", [t[0] for t in tasks], ["A", "B"])
check("task_split_steps", [len(t[1]) for t in tasks], [2, 1])
# a chatty model that announces "new_task" every chunk must not shatter the guide into stubs
chatty = [{"chunk": i, "segment": "new_task", "task": f"T{i}", "steps": [s]} for i, s in enumerate(steps)]
merged = H.split_for_tasks(chatty, 35, keep_nonexec=False, min_steps=3)[0]
check("stubs_merged", len(merged), 2)
check("split_reports_counts", H.split_for_tasks(rows, 35)[1:], (0, 0))
twice = [{"chunk": 0, "segment": "continue", "task": "", "steps": [steps[0], steps[0], steps[1]]}]
merged2 = H.split_for_tasks(twice, 35)[0]
check("boundary_repeat_merged", [len(t[1]) for t in merged2], [2])

# 7) app name inferred from a formulaic tutorial title (the dataset's primary key)
for title, want in [("Excel for Beginners - The Complete Course", "excel"),
                    ("How to use GIMP: Complete Introduction ~ Tutorials for Beginners 2017", "gimp"),
                    ("Intro to Unity: Building your first game in 1 hour", "unity"),
                    ("Notepad++ Full Tutorial", "notepad"),
                    ("Blender 3D Tutorial for Beginners 2026", "blender_3d"),
                    ("Microsoft Word in Just 60 Minutes. Complete Word Tutorial", "microsoft_word")]:
    check(f"guess_app[{want}]", H.slugify(H.guess_app(title)), want)
print("\n" + ("ALL PASS" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
