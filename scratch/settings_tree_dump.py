"""WHY is the search box missing from the parked Settings tree?
(a) is the box there under a different aid/name?  (b) is the whole tree un-laid-out (every rect 0x0)?
Dump search-named nodes + rect statistics, then lay the window out and dump again."""
import sys, time
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import background_window as bw, fast_uia, headless_input as hin
from core_organs.professor import launcher as LN, state_protect as SPT

hin.ensure_input_desktop()
t = LN.resolve("settings")
guard = SPT.StateGuard("settings", t.appid)
info = LN.launch_owned(t, guard)
hwnd = int(info.get("hwnd") or 0)
print("hwnd", hwnd, "title", info.get("title"))
bg = bw.BackgroundSession(hwnd)
bg.__enter__()
time.sleep(3.0)


def dump(tag):
    nodes = fast_uia.snapshot(hwnd, timeout_ms=9000) or []
    nz = [n for n in nodes if n.rect and n.rect[2] > n.rect[0]]
    print(f"\n== {tag}: {len(nodes)} nodes, {len(nz)} with a real rect, {len(nodes) - len(nz)} with a 0x0 rect")
    for n in nodes:
        words = " ".join(str(getattr(n, k, "") or "") for k in ("name", "help", "aid", "ctype"))
        if any(w in words.lower() for w in ("search", "find")):
            print("   search-ish:", repr(n.name)[:64], "| aid", repr(n.aid)[:28], "| role", n.role, "| rect", n.rect)
    # what are the top-of-window nodes a person sees (the command bar)?
    for n in nz[:10]:
        print("   first real:", repr(n.name)[:60], "| aid", repr(n.aid)[:26], "| rect", n.rect)


dump("parked")
try:
    bg.lay_out(settle_s=1.5)
    print("lay_out called")
except Exception as exc:
    print("lay_out failed:", exc)
dump("after lay_out")
try:
    bg.__exit__(None, None, None)
except Exception:
    pass
# close the instance we started, so the next probe / run finds a clean slate
try:
    import ctypes
    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)          # WM_CLOSE
except Exception:
    pass
print("\ndone")
