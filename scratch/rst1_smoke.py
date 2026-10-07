import sys, os, time
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import state_keeper as sk
from core_organs import si_test_support as sup

sk.reset()
fx = sup.FrameWithPopups().start()
print("frame hwnd:", fx.hwnd, "alive:", bool(fx.hwnd))
base = fx.open_popup()
time.sleep(0.25)
pre = sk.observe(fx.hwnd)
print("pre popups:", pre["popups"], "uia:", pre["uia"], "iconic:", pre["iconic"])
ours = [fx.open_popup(), fx.open_popup()]
time.sleep(0.3)
print("visible now:", fx.visible_popups())
rep = sk.restore(fx.hwnd)
print("report status:", rep.get("status"), "matches:", rep.get("matches_pre_state"))
print("restored:", rep.get("restored"))
print("degraded:", rep.get("degraded"))
print("residual:", rep.get("residual"))
print("base alive after:", fx.alive(base), "ours alive:", [fx.alive(i) for i in ours])
rep2 = sk.restore(fx.hwnd)
print("second restore (unobserved):", rep2.get("status"))
# abort path
box = []
try:
    with sk.preserve(fx.hwnd) as k:
        box.append(k)
        our2 = fx.open_popup()
        time.sleep(0.2)
        raise RuntimeError("boom")
except RuntimeError as e:
    print("propagated:", e)
r = box[0]["report"]
print("abort report:", r.get("status"), "aborted:", r.get("aborted"), "matches:", r.get("matches_pre_state"))
print("our2 alive:", fx.alive(our2), "base alive:", fx.alive(base))
fx.stop()
sk.reset()
print("SMOKE_DONE")
