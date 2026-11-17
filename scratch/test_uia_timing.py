import sys, time, ctypes
sys.path.extend(['d:/new_automation', 'd:/new_automation/All codes'])
from core_organs.professor import launcher, state_protect
from core_organs.professor.effectors import Effector, pattern_of
from core_organs import fast_uia, background_window as bw

t = launcher.resolve('calculator')
guard = state_protect.StateGuard('calculator')
info = launcher.launch_owned(t, guard)
hwnd = info['hwnd']
print("Calculator hwnd:", hwnd)

bg = bw.BackgroundSession(hwnd)
bg.__enter__()

time.sleep(2.0)
nodes = fast_uia.snapshot(hwnd)
print("Nodes:", len(nodes))

# Find TogglePaneButton
nav = next((n for n in nodes if n.aid == 'TogglePaneButton'), None)
curr = next((n for n in nodes if n.aid == 'Currency'), None)

print("Nav:", nav.name if nav else None, nav.rect if nav else None)
print("Curr:", curr.name if curr else None, curr.rect if curr else None)

fx = Effector(hwnd, allow_input=True, owned=True)

# Test 1: invoke TogglePaneButton
print("Invoking TogglePaneButton...")
t0 = time.time()
ok, note = fx.node(nav)
print(f"TogglePaneButton took {time.time()-t0:.3f}s: ok={ok}, note={note}")

time.sleep(1.0)
nodes2 = fast_uia.snapshot(hwnd)
curr2 = next((n for n in nodes2 if n.aid == 'Currency'), None)
print("Curr after drawer open:", curr2.name if curr2 else None, curr2.rect if curr2 else None)

# Test 2: select Currency
print("Selecting Currency...")
t0 = time.time()
ok2, note2 = fx.node(curr2)
print(f"Currency took {time.time()-t0:.3f}s: ok={ok2}, note={note2}")

bg.__exit__(None, None, None)
guard.restore()
