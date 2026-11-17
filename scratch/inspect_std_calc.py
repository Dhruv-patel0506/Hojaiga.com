import sys, time
sys.path.extend(['d:/new_automation', 'd:/new_automation/All codes'])
from core_organs.professor import launcher, state_protect
from core_organs.professor.effectors import Effector
from core_organs.professor.executor import Executor
from core_organs.professor.harvest import harvest_tree, Catalog
from core_organs import fast_uia

t = launcher.resolve('calculator')
guard = state_protect.StateGuard('calculator')
info = launcher.launch_owned(t, guard)
hwnd = info['hwnd']
print("Calculator hwnd:", hwnd)

for _ in range(10):
    time.sleep(1.0)
    nodes = fast_uia.snapshot(hwnd)
    if len(nodes) > 10:
        break

print("Total nodes:", len(nodes))
for n in nodes:
    if 'standard' in n.name.lower():
        print(f"Node: name={n.name!r}, aid={n.aid!r}, role={n.role!r}, selected={getattr(n, 'selected', None)}, pats={getattr(n, 'pats', [])}, rect={n.rect}")

guard.restore()
