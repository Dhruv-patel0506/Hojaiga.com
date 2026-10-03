"""
Hojaiga Individual Task Runner
Usage: python run_task.py "your task statement here"
"""

import sys
import os
import uuid
import argparse

sys.path.insert(0, r"D:\new_automation\All codes")

def run(objective):
    from core_organs.organ_01_brain import HojaigaBrain
    brain = HojaigaBrain()
    tid = f"task_{uuid.uuid4().hex[:6]}"
    result = brain.compile_task(objective, task_id=tid)
    status = result.get("status", "UNKNOWN")
    print(f"\n[RESULT] {status}")
    if result.get("error"):
        print(f"[ERROR] {result['error'][:300]}")
    if result.get("crew_output"):
        print(f"[OUTPUT] {str(result['crew_output'])[:500]}")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task", type=str, help="Task objective as a string")
    args = parser.parse_args()
    run(args.task)
