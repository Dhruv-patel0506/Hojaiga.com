"""Does the background tree reader behave as designed on the window that measured 22 s per read?
It must: never block the caller, publish a COMPLETE generation, and let a step read 1000+ controls instantly."""
import sys, time
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor import executor as EX

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 1902220
m = EX.mirror_for(HWND)
a = time.time()
print(f"latest() at +0.0s -> {m.latest()}  (call took {time.time()-a:.3f}s: a reader never waits)")
for i in range(10):
    time.sleep(4.0)
    got = m.latest()
    print(f"  +{time.time()-a:5.1f}s  published={0 if got is None else len(got):5} nodes   stats={m.stats()}")
    if got:
        break
print("enabled?", EX._frame_enabled(HWND))
