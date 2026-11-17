"""
reflexion_proof -- isolates the Part-3 Reflexion formula (p' = p + (1-p)r).

The live benchmark's name-mismatch cases are ALSO caught by the vision tier, so they
don't isolate Reflexion. Here we deliberately disable vision and drive Calculator with a
trajectory whose operator name is WRONG ("Times sign" instead of the real "Multiply by"):
  * Reflexion OFF -> the step is NOT LOCATED, the multiply never happens, 6x7 != 42 -> FAIL
  * Reflexion ON  -> it reads the live tree, finds "Multiply by", re-targets, and 6x7 -> 42 -> PASS
Same app, same trajectory, same (vision-off) resolver; the ONLY difference is Reflexion.
"""
import json
import os
import subprocess
import time
from pathlib import Path

os.environ["HOJAIGA_OFFSCREEN"] = "1"
import live_trajectory_executor as LX

TMP = Path("reports/ml_analysis/_reflexion_traj.json")
TMP.parent.mkdir(parents=True, exist_ok=True)


def step(sid, name, exp):
    return {"step_id": sid,
            "ui_target": {"element_name": name, "element_type": "Button", "bounding_box": [0, 0, 0, 0]},
            "virtual_mouse_action": {"action_type": "CLICK"},
            "expected_state_change": exp,
            "low_level_instruction": f"click {name}"}


TRAJ = {"app_metadata": {"app_name": "Calculator", "dataset_split": "EVAL", "scan_prerequisites_met": True},
        "target_kind": "desktop_gui", "high_level_task": "6 x 7 = 42 (wrong op name)",
        "prerequisite_state": "Calculator open in Standard mode", "total_steps": 4,
        "trajectory": [step(1, "Six", "Display is 6"), step(2, "Times sign", "multiplication armed"),
                       step(3, "Seven", "Display is 7"), step(4, "Equals", "Display is 42")]}


def ensure_calc():
    hwnd, title = LX.find_hwnd("Calculator")
    if hwnd:
        return hwnd, title
    subprocess.Popen(["calc.exe"])
    for _ in range(20):
        time.sleep(0.6)
        hwnd, title = LX.find_hwnd("Calculator")
        if hwnd:
            return hwnd, title
    return None, None


def reset(hwnd):
    for n in LX.snapshot_nodes(hwnd):
        if str(getattr(n, "name", "") or "").lower() == "clear":
            LX.uia_act(n, "CLICK")
            return


def run(reflexion_on):
    LX.REFLEXION = reflexion_on
    hwnd, title = ensure_calc()
    if not hwnd:
        print("Calculator unavailable"); return None
    reset(hwnd)
    TMP.write_text(json.dumps(TRAJ, indent=3), encoding="utf-8")
    summ = LX.run_trajectory(str(TMP), hwnd, title, vision_handoff=False)  # vision OFF -> isolate reflexion
    nodes = LX.snapshot_nodes(hwnd)
    ok = "42" in LX._result_text(nodes)
    return {"reflexion": reflexion_on, "verified": summ["verified"], "total": summ["total"],
            "recovered": summ.get("reflexion_recovered", 0), "task_success_42": ok}


def main():
    print("== Reflexion OFF (vision disabled) ==")
    off = run(False)
    print(json.dumps(off))
    print("== Reflexion ON  (vision disabled) ==")
    on = run(True)
    print(json.dumps(on))
    if off and on:
        print("\n[PROOF] task success  OFF=%s  ON=%s   |  steps verified OFF=%d/%d ON=%d/%d  |  reflexion recoveries ON=%d"
              % (off["task_success_42"], on["task_success_42"],
                 off["verified"], off["total"], on["verified"], on["total"], on["recovered"]))


if __name__ == "__main__":
    main()
