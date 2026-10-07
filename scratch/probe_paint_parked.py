"""DECISIVE measurement for P1-F. PAINT1 pastes an image into Paint while Paint is HELD PARKED off-screen
(the harness background mode). This asks, in that exact state: does Paint expose a 'Paste' control the backbone
can Invoke, and does opening the Edit menu (Expand) make one appear? Nothing here is physical input - only UIA
pattern calls on a window THIS probe started and closes.

Drives background_window.enter() (the real park) so the layout matches what PAINT1 actually sees."""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import fast_uia, background_window as bw

u32 = ctypes.windll.user32


def paint_ws():
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _l):
        if u32.IsWindowVisible(h) and u32.GetWindowTextLengthW(h) > 0:
            b = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(h, b, 256)
            if "paint" in b.value.lower():
                out.append(int(h))
        return True

    u32.EnumWindows(cb, 0)
    return out


def rows(h):
    return fast_uia.snapshot(h, timeout_ms=6000) or []


def find(h, sub):
    for n in rows(h):
        if sub in (n.name or "").lower():
            return n
    return None


before = set(paint_ws())
# SW_SHOWMINNOACTIVE: the window is minimized, so bw.enter() takes its REAL park branch (this is the state
# PAINT1 runs in - "paint hwnd=... held parked off-screen"). No foreground is stolen either way.
ctypes.windll.shell32.ShellExecuteW(None, "open", "mspaint.exe", None, None, 7)
hwnd = 0
for _ in range(60):
    time.sleep(0.5)
    new = [h for h in paint_ws() if h not in before]
    if new:
        hwnd = new[0]
        break
if not hwnd:
    print("paint did not open")
    raise SystemExit(1)
bw.mark_ours(hwnd)
print(f"paint hwnd={hwnd}")

st = bw.enter(hwnd)
print(f"bw.enter -> {st}")
time.sleep(1.2)
_slivered = bw.sliver(hwnd)
if _slivered:
    time.sleep(1.0)
print(f"   is_minimized={bw.is_minimized(hwnd)} user_can_see={bw.user_can_see(hwnd)} "
      f"sliver_applied={_slivered} rect={bw._rect(hwnd)}")

r0 = rows(hwnd)
named = [(n.name, n.ctype, sorted(n.pats), n.rect, n.expand_state) for n in r0]
print(f"\nPARKED: {len(r0)} nodes; any 'paste'? "
      f"{[x for x in named if 'paste' in (x[0] or '').lower()]}")
edit = next((n for n in r0 if (n.name or '').lower() == 'edit'), None)
if edit:
    print(f"  Edit: pats={sorted(edit.pats)} rect={edit.rect} expand_state={edit.expand_state}")

def phase(tag):
    print(f"\n########## {tag} ##########")
    for verb in ("invoke", "expand"):
        e = find(hwnd, "edit")
        if e is None:
            print(f"\n{verb}: Edit gone"); continue
        live = e.ctrl
        try:
            live.GetExpandCollapsePattern().Collapse(); time.sleep(0.5)
        except Exception:
            pass
        print(f"\n== {verb.upper()} ({sorted(e.pats)}, rect={e.rect}) ==")
        try:
            (live.GetInvokePattern().Invoke() if verb == "invoke"
             else live.GetExpandCollapsePattern().Expand())
        except Exception as exc:
            print(f"   raised {type(exc).__name__}: {str(exc)[:60]}")
        for w in (0.8, 1.5, 3.0):
            time.sleep(w if w == 0.8 else 0.7)
            pastes = [x for x in rows(hwnd) if 'paste' in (x.name or '').lower()]
            if pastes:
                print(f"   +{w}s PASTE APPEARED: {[(p.name, p.ctype, sorted(p.pats), p.rect) for p in pastes[:2]]}")
                break
        else:
            ec = find(hwnd, "edit")
            print(f"   +3s NO paste; Edit expand_state={ec.expand_state if ec else '?'}; "
                  f"nodes={len(rows(hwnd))}")


phase("A: PARKED off-screen + 1px sliver (exactly what PAINT1 runs in)")

# Phase B: put OUR OWN window genuinely on screen (no activation, no input) to separate
# "parked window cannot lay out a flyout" from "invoke is the wrong verb".
u32.SetWindowPos(hwnd, 0, 40, 40, 1100, 760, 0x0040)  # SWP_NOACTIVATE
time.sleep(1.5)
print(f"\n   on-screen now: rect={bw._rect(hwnd)} user_can_see={bw.user_can_see(hwnd)}")
phase("B: SAME window moved ON-SCREEN")

for h in [x for x in paint_ws() if x not in before]:
    try:
        bw.exit(h)
    except Exception:
        pass
    u32.PostMessageW(h, 0x0010, 0, 0)
