import sys, time
sys.path.extend(['d:/new_automation', 'd:/new_automation/All codes'])
from core_organs.professor import launcher, state_protect
from core_organs import fast_uia, background_window as bw

t = launcher.resolve('calculator')
guard = state_protect.StateGuard('calculator')
info = launcher.launch_owned(t, guard)
hwnd = info['hwnd']
bg = bw.BackgroundSession(hwnd)
bg.__enter__()
time.sleep(2.0)

nodes = fast_uia.snapshot(hwnd)
print("Total nodes:", len(nodes))
for n in nodes:
    if any(k in n.name.lower() or k in n.aid.lower() for k in ('top', 'pin', 'overlay', 'compact', 'keep')):
        print(f"Match: name={n.name!r}, aid={n.aid!r}, role={n.role!r}, rect={n.rect}, pats={n.pats}")

bg.__exit__(None, None, None)
guard.restore()
