import sys, os, json, tempfile, uuid, time, ctypes
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import si_tests_behavior as sb, organ_48_app_behavior_model as bm, background_window as bw
u32 = ctypes.windll.user32
db = os.path.join(tempfile.gettempdir(), "hj_cc_" + uuid.uuid4().hex[:6] + ".db")
m = bm.BehaviorModel(db); m.load_pack_dir()
def crawl(tag, hwnd, app="paint"):
    t = time.time()
    r = bm.crawl_e0(m, app, hwnd)
    print(tag, {k: v for k, v in r.items() if k in ("window_mode", "ingested", "elapsed_s", "stopped", "units")}, [(m["method"], m["found"], m["nodes"], m["stopped"], m["skipped"][:3]) for m in r.get("methods", [])], f"{time.time()-t:.1f}s", flush=True)
mode = sys.argv[1]
if mode == "both":
    with sb.LiveApp("notepad") as ln, sb.LiveApp("paint") as lp:
        crawl("paint crawl with notepad also parked:", lp.hwnd)
elif mode == "paint":
    with sb.LiveApp("paint") as lp:
        crawl("paint crawl alone:", lp.hwnd)
elif mode == "both_notepad_first":
    with sb.LiveApp("notepad") as ln, sb.LiveApp("paint") as lp:
        crawl("notepad crawl:", ln.hwnd, "notepad")
        crawl("paint crawl after notepad crawl:", lp.hwnd)
