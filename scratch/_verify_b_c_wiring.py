"""Scratch verification for this session's B (organ_36 backup) and C (cross-run attach) wiring.

No LLM, no GUI: the enhanced compiler is faked at the module attribute the helper re-imports
per call, and the knowledge manager is pointed at a temp dir. Proves: backup adapts steps,
fires only when the PRIMARY fails, respects HOJAIGA_COMPILE_BACKUP=0; and that the recorder
persists success/fail into action_stats and respects HOJAIGA_XRUN_RECORD=0.
"""
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, r"D:\new_automation\All codes")
os.environ["HOJAIGA_WEBAPP_WATCH"] = "0"

fails = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'XX'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


from core_organs import organ_01_crewai_engine as o1
from core_organs import organ_36_enhanced_compiler as ec36
from core_organs import organ_36_workflow_compiler as wc36
from core_organs.organ_knowledge_manager import AppKnowledgeManager

# ---------------------------------------------------------------- B: backup compiler
_fake_plan = SimpleNamespace(checkpoints=[
    SimpleNamespace(id="checkpoint_1", name="Preparation", description="launch app"),
    SimpleNamespace(id="checkpoint_2", name="Execution", description="do the work"),
])
_orig_enh = ec36.compile_enhanced_task
ec36.compile_enhanced_task = lambda command, context=None: _fake_plan

res = o1._organ36_backup_compile("open paint and draw a house")
check("B1 backup adapts EnhancedTaskPlan -> steps", bool(res) and res["success"]
      and len(res["steps"]) == 2 and res["steps"][0]["capability"] == "DESKTOP.GENERAL_EXECUTION"
      and res["source"] == "organ36_backup", str(res)[:200])


class _BoomKernel:
    def compile_workflow(self, *a, **k):
        raise RuntimeError("forced primary failure (simulated)")


_orig_kernel = wc36.WorkflowCompilerKernel
wc36.WorkflowCompilerKernel = _BoomKernel
os.environ["HOJAIGA_COMPILE_BACKUP"] = "1"
res2 = o1._compile_task_with_organ36("open paint")
check("B2 primary failure -> backup returned", res2.get("source") == "organ36_backup"
      and len(res2.get("steps", [])) == 2, str(res2)[:200])

os.environ["HOJAIGA_COMPILE_BACKUP"] = "0"
res3 = o1._compile_task_with_organ36("open paint")
check("B3 toggle OFF -> honest success:False, no backup", res3.get("success") is False
      and res3.get("steps") == [] and "source" not in res3, str(res3)[:200])

# A backup that itself raises must still fall through to success:False (never fatal):
# primary kernel STAYS broken here - that is the whole point of this scenario.
def _raise(*a, **k):
    raise ValueError("backup broken too")
os.environ["HOJAIGA_COMPILE_BACKUP"] = "1"
ec36.compile_enhanced_task = _raise
res4 = o1._compile_task_with_organ36("open paint")
check("B4 backup crash -> falls through, no exception", res4.get("success") is False, str(res4)[:120])
ec36.compile_enhanced_task = _orig_enh
wc36.WorkflowCompilerKernel = _orig_kernel
os.environ.pop("HOJAIGA_COMPILE_BACKUP", None)

# ---------------------------------------------------------------- C: cross-run record attach
tmp = tempfile.mkdtemp(prefix="xrun_verify_")
km = AppKnowledgeManager(storage_dirs=[tmp])
AppKnowledgeManager._instance = km  # get_instance() inside the hook now uses the temp store
km.save_knowledge("paint", {"app_type": "desktop", "ui_elements": [{"name": "File", "interactable": True}]})

o1._xrun_record_operate_result("paint", {"trace": [
    {"verb": "click", "element": "File", "verdict": "ok", "method": "UIA"},
    {"verb": "type", "element": "canvas", "verdict": "FAILED: denied", "method": "UIA"},
    {"verb": "hover", "element": "", "verdict": "ok"},          # no verb target -> skipped
]})
prof = json.load(open(km.get_knowledge("paint")["_filepath"], encoding="utf-8"))
stats = prof.get("action_stats", {})
check("C1 success recorded", stats.get("click:File", {}).get("success_count") == 1, str(stats)[:200])
check("C2 failure recorded", stats.get("type:canvas", {}).get("fail_count") == 1
      and stats.get("type:canvas", {}).get("last_errors"), str(stats)[:200])
check("C3 empty-verb trace entry skipped", "hover:" not in "".join(stats.keys()), str(stats)[:200])

os.environ["HOJAIGA_XRUN_RECORD"] = "0"
o1._xrun_record_operate_result("paint", {"trace": [{"verb": "click", "element": "File", "verdict": "ok"}]})
os.environ.pop("HOJAIGA_XRUN_RECORD", None)
prof2 = json.load(open(km.get_knowledge("paint")["_filepath"], encoding="utf-8"))
check("C4 toggle OFF -> nothing extra persisted",
      prof2["action_stats"]["click:File"]["success_count"] == 1, str(prof2["action_stats"])[:200])

# A recorder crash must never propagate into actuation
AppKnowledgeManager._instance = None
o1._xrun_record_operate_result("paint", {"trace": [{"verb": "click", "element": "x", "verdict": "ok"}]})
check("C5 hook survives singleton swap/no-profile (no exception)", True)

print("\nRESULT:", "ALL CHECKS PASSED" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
