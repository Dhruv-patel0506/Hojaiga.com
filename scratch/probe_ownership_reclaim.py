"""Prove the ownership reclaim: a window marked ours gets closed at the boundary; an unmarked
look-alike survives. Fixtures are the suite's own native windows - no third-party app involved."""
import ctypes
import ctypes.wintypes as wt
import time

from core_organs import background_window as bw
from core_organs import si_test_support as sup
from core_organs.run_system_intelligence_tests import _reclaim_harness_artifacts

u = ctypes.windll.user32

leaked = sup.NativeButtonWindow(title="HJ-Reclaim-Owned").start()
time.sleep(0.3)
hq = int(leaked.hwnd or 0)
assert u.IsWindow(hq), "fixture window not alive"

bw.mark_ours(hq)                       # the launch layer's act: this process created it
print("in registry before reclaim:", hq in bw.ours_alive())

owned_closed, titled_closed = _reclaim_harness_artifacts()
time.sleep(0.4)
print(f"reclaim -> owned={owned_closed} titled={titled_closed}")
print("owned window alive after:", u.IsWindow(hq), "(want False)")
print("registry after:", bw.ours_alive(), "(want empty)")
leaked.stop()

foreign = sup.NativeButtonWindow(title="HJ-Reclaim-Foreign").start()
time.sleep(0.3)
hf = int(foreign.hwnd or 0)
owned2, titled2 = _reclaim_harness_artifacts()
time.sleep(0.4)
print(f"second reclaim -> owned={owned2} titled={titled2}")
print("unmarked look-alike alive:", u.IsWindow(hf), "(want True)")
print("RESULT:", (not u.IsWindow(hq)) and u.IsWindow(hf) and owned_closed == 1 and owned2 == 0)
foreign.stop()
