import sys
sys.path.extend(["d:/new_automation", "d:/new_automation/All codes"])
from core_organs.professor import workflows as WF

apps = ["powerpnt", "winword", "notepad", "calculator", "mspaint", "blender", "chrome", "code", "systemsettings", "obs64"]
print(f"{'App':16s} | {'C4':8s} | {'Grounded':8s} | {'Applicable':10s} | {'Status':8s}")
print("-" * 65)

all_passed = True
for app in apps:
    doc = WF.build(app, write=True)
    s = doc["summary"]
    c4 = s["grounding_applicable"] * 100
    gr = s["grounded_steps"]
    app_steps = s["applicable_steps"]
    passed = c4 >= 90.0
    if not passed:
        all_passed = False
    status = "PASS (>=90)" if passed else f"FAIL ({c4:.1f}%)"
    print(f"{app:16s} | {c4:6.1f}%  | {gr:8d} | {app_steps:10d} | {status}")

print("-" * 65)
if all_passed:
    print("ALL 10 APPLICATIONS PASSED C4 >= 90.0% SUCCESSFULLY!")
else:
    print("SOME APPLICATIONS FAILED.")
