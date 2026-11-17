"""
win32_suite -- Stage-3 execution on a classic Win32 GDI app (Character Map) to accumulate
genuinely-verified episodic rows off-screen, where UWP/XAML input throttling does NOT apply.
Each task's steps are run through the hardened executor (SELECTION_STATE / UIA_DELTA / value
mutation gates); a task is committed to episodic_memory ONLY if every step verifies. Honest:
a step that does not actually flip state is NOT committed.
"""
import os
os.environ["HOJAIGA_OFFSCREEN"] = "1"
import time
import subprocess
import json
import agent_loop as A
import live_trajectory_executor as LX
import semantic_match as SM
import episodic_memory as EM


def click(name, etype="Button"):
    return {"step_id": 0, "ui_target": {"element_name": name, "element_type": etype, "bounding_box": [0, 0, 0, 0]},
            "virtual_mouse_action": {"action_type": "CLICK"}, "expected_state_change": "",
            "low_level_instruction": f"CLICK {name}"}


# (task_id, intent, [steps])  -- each runs on a freshly-launched charmap for a clean slate
TASKS = [
    ("charmap-advview", "Toggle Advanced view on", [click("Advanced view", "CheckBox")]),
    ("charmap-select", "Select a character into the copy box", [click("Select")]),
    ("charmap-select-clear", "Select then Clear the copy box", [click("Select"), click("Clear")]),
    ("charmap-select-copy", "Select then Copy a character", [click("Select"), click("Copy")]),
    ("charmap-groupby", "Open the Group-by selector", [click("Group by :", "ComboBox")]),
    # ---- Win32 menu navigation (classic menus obey Invoke off-screen) ----
    ("charmap-file-menu", "Open the File menu", [click("File", "MenuItem")]),
    ("charmap-edit-menu", "Open the Edit menu", [click("Edit", "MenuItem")]),
    ("charmap-edit-selectall", "Edit > Select All", [click("Edit", "MenuItem"), click("Select All", "MenuItem")]),
    ("charmap-edit-copy", "Edit > Copy", [click("Edit", "MenuItem"), click("Copy", "MenuItem")]),
    ("charmap-view-menu", "Open the View menu", [click("View", "MenuItem")]),
]


def fresh_charmap():
    subprocess.run(["taskkill", "/F", "/IM", "charmap.exe"], capture_output=True)
    time.sleep(1.0)
    subprocess.Popen(["charmap.exe"])
    for _ in range(15):
        time.sleep(0.6)
        h, t = A._ensure("Character", "charmap.exe")
        if h:
            LX._organs()[1].isolate_offscreen(h)
            time.sleep(0.4)
            return h
    return None


def run():
    committed = 0
    for tid, intent, steps in TASKS:
        h = fresh_charmap()
        if not h:
            print(f"[win32] SKIP {tid}: charmap not found")
            continue
        results, all_ok = [], True
        for i, st in enumerate(steps):
            rec, v, _ = LX._attempt_step(st, i + 1, "win32", h, None, False, True, SM.LEX_STRONG, False, False)
            results.append(rec)
            print(f"[win32]   {tid} step{i+1} {st['ui_target']['element_name']!r} verified={v} via {rec.get('verification_type')}")
            all_ok = all_ok and v
        if all_ok:
            try:
                EM.save_verified("Character", intent, results, verification_type="SELECTION_STATE/UIA")
                committed += 1
                print(f"[win32] COMMIT {tid} ({len(steps)} steps verified)")
            except Exception as e:
                print(f"[win32] commit failed {tid}: {e}")
        else:
            print(f"[win32] NOT committed {tid} (a step did not verify -- honest)")
    subprocess.run(["taskkill", "/F", "/IM", "charmap.exe"], capture_output=True)
    print(f"[win32] Character Map suite: {committed}/{len(TASKS)} tasks fully verified + committed")
    return committed


if __name__ == "__main__":
    run()
