import sys, os, json, tempfile, uuid, time
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import si_tests_behavior as sb, organ_48_app_behavior_model as bm
import ctypes
u32 = ctypes.windll.user32
db = os.path.join(tempfile.gettempdir(), "hj_t2_" + uuid.uuid4().hex[:6] + ".db")
m = bm.BehaviorModel(db); m.load_pack_dir()
png = os.path.join(tempfile.gettempdir(), "hj_t2_" + uuid.uuid4().hex[:6] + ".png")
with sb.LiveApp("paint") as lp:
    print("paint ok", lp.ok, lp.why, flush=True)
    runner = bm.TemplateRunner(m)
    hw = lp.hwnd
    orig = runner.g.find_window
    runner.g.find_window = lambda hint, _o=orig: hw if hint == "paint" else _o(hint)
    t0 = time.time()
    r = runner.run("paint", "save the image as file", {"path": png}, hwnd_fn=lambda: hw if u32.IsWindow(hw) else 0)
    print(f"{time.time()-t0:.1f}s")
    print(json.dumps({k: v for k, v in r.items() if k != "model"}, default=str)[:3000])
    print("file:", os.path.exists(png))
    try: os.remove(png)
    except Exception: pass
