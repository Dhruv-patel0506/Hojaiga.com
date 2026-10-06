"""Excel end-to-end through the loop, with the stale-file hole closed.

The task the work order named (1.3/D: reach a file path through a rich app's Save dialog), run the way
the suite runs it: `operate_app`, virtual cursor only, and the file judged by "written AFTER the goal
started" -- because a leftover file from an earlier run once made a task that saved nothing look green.
"""
import sys, os, time
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
os.environ["HOJAIGA_WEBAPP_WATCH"] = "0"
os.environ.setdefault("HOJAIGA_KNOWLEDGE_ROOT", os.path.join(r"D:\new_automation", "organ_04_knowledge"))
import psutil
from core_organs import headless_input as hin
from core_organs.desktop_grounding import operate_app

out_dir = r"D:\new_automation\_excel_e2e_tmp"
os.makedirs(out_dir, exist_ok=True)
target = os.path.join(out_dir, f"pro_{int(time.time())}.xlsx")     # a name no earlier run used: freshness
for f in os.listdir(out_dir):                                      # ... and no leftovers to be confused with
    try:
        os.remove(os.path.join(out_dir, f))
    except OSError:
        pass

pids0 = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "excel.exe"}
viol0 = len(hin.VIOLATIONS)
t0 = time.time()
goals = ["type 42 in cell A1", f"save the workbook as {target}"]
r = operate_app("excel", goals, expect_map={1: {"file_created": target}}, max_steps_per_goal=6)
elapsed = time.time() - t0
written = os.path.exists(target) and os.stat(target).st_mtime >= t0 - 1.0 and os.stat(target).st_size > 0
print(f"completed={r.get('completed')} blocked_at_goal={r.get('blocked_at_goal')} "
      f"steps={r.get('steps')} {elapsed:.1f}s awaiting_human={r.get('awaiting_human')}", flush=True)
print(f"FILE WRITTEN THIS RUN: {written}  size={os.path.getsize(target) if os.path.exists(target) else 0}", flush=True)
for st in r.get("trace", []):
    print(f"  {st.get('verb','?'):>7} {str(st.get('element',''))[:26]:<26} {st.get('verdict',''):<11} "
          f"{str(st.get('evidence',''))[:110]}", flush=True)
print(f"input-guard violations={len(hin.VIOLATIONS) - viol0} "
      f"physical-pointer-moved={hin.VIOLATIONS[viol0:] if len(hin.VIOLATIONS) > viol0 else 'no'}", flush=True)
try:
    # close ONLY the process we started: a window search by app name would find the user's own Excel too,
    # and that window must not be touched
    for p in psutil.process_iter(["name", "pid"]):
        if (p.info["name"] or "").lower() == "excel.exe" and p.pid not in pids0:
            p.terminate()
except Exception as exc:
    print("teardown:", exc, flush=True)
print("done", flush=True)
