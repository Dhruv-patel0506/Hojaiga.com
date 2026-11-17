"""_uwp_probe: does UIA InvokePattern drive UWP Calculator where posted-clicks failed?"""
import sys, time
from pathlib import Path
sys.path.insert(0, "All codes")
sys.path.insert(0, ".")
from core_organs import fast_uia, headless_input as hin
import live_trajectory_executor as LX

hwnd, title = LX.find_hwnd("Calculator")
print("hwnd", hwnd, title)
nodes = LX.snapshot_nodes(hwnd)
print("nodes", len(nodes))

def find(aid):
    for n in nodes:
        if (n.aid or "") == aid:
            return n
    return None

# read the display value element
def display():
    ns = LX.snapshot_nodes(hwnd)
    for n in ns:
        if (n.aid or "") == "CalculatorResults":
            return n.name
    # fallback: any Text control whose name has digits
    for n in ns:
        if n.role == "text" and (n.name or "").strip().isdigit():
            return "text:"+n.name
    return "?"

print("display BEFORE:", display())

for aid in ["num1Button", "plusButton", "num1Button", "equalButton"]:
    n = find(aid)
    if n is None:
        print(f"  {aid}: NOT FOUND in tree")
        continue
    ok, note = LX.uia_act(n, "CLICK")   # UIA InvokePattern path
    print(f"  invoke {aid}: ok={ok} note={note}")
    time.sleep(0.4)

print("display AFTER UIA-invoke:", display())
pf = LX.capture_proof(hwnd, "uwp_probe_after")
print("proof:", pf)
