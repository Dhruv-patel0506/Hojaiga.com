"""Does a flyout of a PARKED app ever reach the SCREEN's pixels? Independent of window geometry: grab the composed desktop every ~25 ms while the app's
menus are crawled, and count frames that differ from a baseline taken just before. Run twice: HOJAIGA_CONCEAL_FLYOUTS=0 and =1."""
import sys, os, time, threading, tempfile, uuid
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from PIL import ImageGrab, ImageChops
from core_organs import si_tests_behavior as sb, organ_48_app_behavior_model as bm

app = sys.argv[1] if len(sys.argv) > 1 else "paint"
frames = []
stop = False


def grab():
    while not stop:
        t = time.perf_counter()
        try:
            im = ImageGrab.grab(all_screens=True).convert("L")
            frames.append((t, im.resize((im.width // 4, im.height // 4))))
        except Exception:
            pass
        time.sleep(0.01)


db = os.path.join(tempfile.gettempdir(), "hj_flash_" + uuid.uuid4().hex[:6] + ".db")
m = bm.BehaviorModel(db)
with sb.LiveApp(app, park=True) as la:
    if not la.ok:
        print("cannot launch", la.why)
        sys.exit(1)
    time.sleep(1.5)
    base = ImageGrab.grab(all_screens=True).convert("L")
    base = base.resize((base.width // 4, base.height // 4))
    th = threading.Thread(target=grab, daemon=True)
    th.start()
    t0 = time.perf_counter()
    e0 = bm.crawl_e0(m, app, la.hwnd)
    dt = time.perf_counter() - t0
    stop = True
    th.join(2)
    from core_organs import background_window as bw
    print("crawl", app, e0.get("window_mode"), e0.get("ingested"), f"{dt:.1f}s", "conceal=", bw.CONCEAL_FLYOUTS)
bad = []
for t, im in frames:
    d = ImageChops.difference(im, base).point(lambda v: 255 if v > 40 else 0)
    n = sum(1 for v in d.getdata() if v)
    bad.append((t, n))
big = [n for _, n in bad if n > 300]
print(f"frames={len(frames)} avg_gap={((frames[-1][0]-frames[0][0])/max(1,len(frames)-1))*1000:.0f}ms  frames_differing(>300px@1/4)={len(big)}  max_diff_px={max([n for _, n in bad] or [0])}")
runs, cur = [], 0.0
last_t = None
for t, n in bad:
    if n > 300:
        cur += (t - last_t) * 1000 if last_t else 0
    else:
        if cur:
            runs.append(cur)
        cur = 0.0
    last_t = t
print("differing-run lengths ms:", [round(r) for r in runs][:12], "longest", round(max(runs or [0])))
