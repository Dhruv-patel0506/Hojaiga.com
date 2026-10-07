"""Probe RBG1 executor primitives on a real fresh Notepad (minimized, opened with a file)."""
import sys, os, time, ctypes, tempfile, uuid, traceback
sys.path.insert(0, r"d:\new_automation\All codes")
os.environ.setdefault("HOJAIGA_WEBAPP_WATCH", "0")
from core_organs import si_tests_behavior as B
from core_organs import headless_input as hin
from core_organs import fast_uia
_u32 = ctypes.windll.user32

path = os.path.join(tempfile.gettempdir(), "hj_rbgprobe_" + uuid.uuid4().hex[:6] + ".txt")
with open(path, "w", encoding="utf-8") as fh:
    fh.write("base line\n")
text = "rbg1-" + uuid.uuid4().hex[:8] + " steady rises keep the pen dry"

la = B.LiveApp("notepad", park=False, args=[path])
la.__enter__()
print("launch:", la.ok, la.hwnd, la.why, la.launch_note)
hwnd = la.hwnd
try:
    print("title:", hin.safe_window_text(hwnd))
    rows = fast_uia.snapshot(hwnd, timeout_ms=8000) or []
    print("nodes:", len(rows))
    for n in rows:
        if n.role in ("edit", "document", "text"):
            print("  cand:", n.role, repr((n.name or "")[:20]), "pats=", n.pats, "cls=", n.cls)
    # SetValue attempt
    ok, how = False, ""
    for n in rows:
        if n.role not in ("edit", "document", "text"):
            continue
        try:
            vp = n.ctrl.GetValuePattern()
            if vp is None:
                print("  no ValuePattern on", n.role); continue
            print("  before:", repr((vp.Value or "")[:30]))
            vp.SetValue(text)
            time.sleep(0.4)
            print("  after SetValue:", repr((vp.Value or "")[:40]))
            ok, how = True, f"via {n.role}"
            break
        except Exception as e:
            print("  SetValue err", n.role, type(e).__name__, str(e)[:80])
    print("set:", ok, how)
    okc, note = hin.post_key_combo(hwnd, "ctrl+s")
    print("ctrl+s:", okc, note)
    time.sleep(2.0)
    content = open(path, encoding="utf-8", errors="replace").read()
    print("file now:", repr(content[:80]))
    # post_text fallback too
    okp, note2 = hin.post_text(hwnd, "EXTRA")
    print("post_text:", okp, note2)
    okc2, note3 = hin.post_key_combo(hwnd, "ctrl+s")
    time.sleep(2.0)
    print("file after pt+save:", repr(open(path, encoding='utf-8', errors='replace').read()[:90]))
finally:
    la.__exit__(None, None, None)
    try: os.remove(path)
    except Exception: pass
print("PROBE_DONE")
