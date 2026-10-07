"""Probe 2: find the actual editable child of Win11 Notepad and land text there."""
import sys, os, time, ctypes, ctypes.wintypes as wt, tempfile, uuid
sys.path.insert(0, r"d:\new_automation\All codes")
os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")
from core_organs import si_tests_behavior as B
from core_organs import headless_input as hin
from core_organs import fast_uia
_u32 = ctypes.windll.user32

path = os.path.join(tempfile.gettempdir(), "hj_rbgprobe2_" + uuid.uuid4().hex[:6] + ".txt")
with open(path, "w", encoding="utf-8") as fh:
    fh.write("base line\n")
text = "rbg1-" + uuid.uuid4().hex[:8] + " steady rises keep the pen dry"

la = B.LiveApp("notepad", park=False, args=[path])
la.__enter__()
hwnd = la.hwnd
print("launch:", la.ok, hwnd, hin.safe_window_text(hwnd))

def children(top):
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        b = ctypes.create_unicode_buffer(256)
        _u32.GetClassNameW(h, b, 256)
        t = ctypes.create_unicode_buffer(256)
        _u32.GetWindowTextW(h, t, 256)
        out.append((h, b.value, t.value[:30]))
        return True
    _u32.EnumChildWindows(top, cb, 0)
    return out

try:
    for h, c, t in children(hwnd):
        print("  child:", hex(h), c, repr(t))
    rows = fast_uia.snapshot(hwnd, timeout_ms=8000) or []
    for n in rows:
        if n.role in ("edit", "document"):
            print("  uia cand:", n.role, n.cls, "pats=", n.pats, "aid=", n.aid, "name=", repr((n.name or "")[:20]))
    # try post_text to each plausible child
    for h, c, t in children(hwnd):
        if "edit" in c.lower() or "rich" in c.lower() or "document" in c.lower():
            ok, note = hin.post_text(h, text)
            print("  post_text ->", c, ok, note)
            time.sleep(0.5)
            rows2 = fast_uia.snapshot(hwnd, timeout_ms=6000) or []
            stat = [n.name for n in rows2 if n.role == "text" and "character" in (n.name or "")]
            print("  status chars now:", stat)
            okk, note2 = hin.post_key_combo(h, "ctrl+s")
            print("  ctrl+s->child:", okk, note2)
            time.sleep(1.5)
            okk2, note3 = hin.post_key_combo(hwnd, "ctrl+s")
            print("  ctrl+s->root:", okk2, note3)
            time.sleep(1.5)
            print("  FILE:", repr(open(path, encoding='utf-8', errors='replace').read()[:60]))
            break
finally:
    la.__exit__(None, None, None)
    try: os.remove(path)
    except Exception: pass
print("PROBE2_DONE")
