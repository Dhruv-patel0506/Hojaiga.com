"""
Hojaiga Progressive Task Test Suite
Tests each capability independently, then combines them.
Run: python test_progressive_tasks.py --level 1
"""

import sys
import os
import time
import json
import subprocess
import uuid
import argparse

sys.path.insert(0, r"D:\new_automation\All codes")

# ─── LEVEL 1: Launch apps ───────────────────────────────────────
LEVEL_1_TASKS = [
    ("Open Notepad", "open notepad"),
    ("Open Calculator", "open calculator"),
    ("Open Paint", "open paint"),
    ("Open WordPad", "open wordpad"),
    ("Open Chrome", "open chrome"),
]

# ─── LEVEL 2: Type into apps ────────────────────────────────────
LEVEL_2_TASKS = [
    ("Type hello in Notepad", "open notepad, create a new file, and type 'Hello World'"),
    ("Type multi-line in Notepad", "open notepad, create a new file, and type 'Line 1\nLine 2\nLine 3'"),
    ("Type and save in Notepad", "open notepad, create a new file, type 'This is a test', then save it as 'test_save.txt'"),
]

# ─── LEVEL 3: Keyboard shortcuts ────────────────────────────────
LEVEL_3_TASKS = [
    ("Ctrl+N in Notepad", "open notepad, press ctrl+n to create new file, then type 'New file created'"),
    ("Ctrl+Z undo in Notepad", "open notepad, create a new file, type 'undo this', then press ctrl+z to undo"),
    ("Alt+Tab switch", "open notepad, type 'first window', then press alt+tab to switch windows"),
]

# ─── LEVEL 4: Multi-app coordination ────────────────────────────
LEVEL_4_TASKS = [
    ("Notepad to Calculator", "open notepad, type '2+2=', then open calculator"),
    ("Write and verify", "open notepad, type 'Verification test', then inspect the screen to confirm text is there"),
    ("Type and scan", "open notepad, type 'Scan me', then scan the app to list all UI elements"),
]

# ─── LEVEL 5: Web + Desktop combo ──────────────────────────────
LEVEL_5_TASKS = [
    ("Chrome + Notepad", "open chrome and navigate to google.com, then open notepad and type 'Google is open'"),
    ("Scrape + Notepad", "scrape technology companies in Atlanta to excel, then open notepad and type 'Scraping done'"),
    ("Full pipeline", "open notepad, type 'Task started', then scrape plumbers in Denver to excel, then open notepad and type 'Task complete'"),
]


def run_task(task_obj, task_id=None):
    """Execute a single task via the Brain (organ_01)."""
    tid = task_id or f"progressive_{uuid.uuid4().hex[:6]}"
    print(f"\n{'='*60}")
    print(f"[TASK] {task_obj['objective']}")
    print(f"[ID]   {tid}")
    print(f"{'='*60}\n")

    from core_organs.organ_01_brain import HojaigaBrain
    brain = HojaigaBrain()
    result = brain.compile_task(task_obj["objective"], task_id=tid)

    status = result.get("status", "UNKNOWN")
    print(f"\n[RESULT] Status: {status}")
    if result.get("error"):
        print(f"[ERROR]  {result['error'][:200]}")
    if result.get("agents"):
        print(f"[AGENTS] {len(result['agents'])} spawned")
    if result.get("crew_output"):
        print(f"[OUTPUT] {str(result['crew_output'])[:300]}")

    return result


def run_level(level_num, tasks):
    """Run all tasks in a level."""
    print(f"\n{'#'*60}")
    print(f"# LEVEL {level_num}: {len(tasks)} tasks")
    print(f"{'#'*60}")

    results = []
    for i, (name, objective) in enumerate(tasks, 1):
        print(f"\n--- Level {level_num}, Task {i}/{len(tasks)}: {name} ---")
        task_obj = {
            "objective": objective,
            "task_id": f"L{level_num}_{i}_{uuid.uuid4().hex[:4]}"
        }
        result = run_task(task_obj)
        results.append({"name": name, "objective": objective, "result": result})
        time.sleep(2)  # Brief pause between tasks

    passed = sum(1 for r in results if r["result"].get("status") in ("SUCCESS", "COMPLETED"))
    print(f"\n[LEVEL {level_num} SUMMARY] {passed}/{len(tasks)} passed")
    return results


def main():
    parser = argparse.ArgumentParser(description="Hojaiga Progressive Task Tester")
    parser.add_argument("--level", type=int, default=1, choices=[1,2,3,4,5],
                        help="Which level to run (1=launch, 2=type, 3=shortcuts, 4=multi-app, 5=web+desktop)")
    parser.add_argument("--all", action="store_true", help="Run all levels sequentially")
    parser.add_argument("--dry-run", action="store_true", help="Print tasks without executing")
    args = parser.parse_args()

    levels = {
        1: ("LAUNCH APPS", LEVEL_1_TASKS),
        2: ("TYPE INTO APPS", LEVEL_2_TASKS),
        3: ("KEYBOARD SHORTCUTS", LEVEL_3_TASKS),
        4: ("MULTI-APP COORDINATION", LEVEL_4_TASKS),
        5: ("WEB + DESKTOP COMBO", LEVEL_5_TASKS),
    }

    if args.dry_run:
        for lvl, (desc, tasks) in levels.items():
            print(f"\n[LEVEL {lvl}] {desc}")
            for i, (name, obj) in enumerate(tasks, 1):
                print(f"  {i}. {name}: {obj}")
        return

    if args.all:
        all_results = {}
        for lvl in range(1, 6):
            desc, tasks = levels[lvl]
            all_results[lvl] = run_level(lvl, tasks)
            time.sleep(3)
        print("\n" + "="*60)
        print("ALL LEVELS COMPLETE")
        for lvl, results in all_results.items():
            passed = sum(1 for r in results if r["result"].get("status") in ("SUCCESS", "COMPLETED"))
            print(f"  Level {lvl}: {passed}/{len(results)} passed")
    else:
        desc, tasks = levels[args.level]
        run_level(args.level, tasks)


if __name__ == "__main__":
    main()
