"""MEASURE (before touching shared actuation): in WinUI Paint, does Invoke on the 'Edit' menu bar item open
its flyout, or only Expand? And does either make a 'Paste' control appear? Read of the control tree only; the
one pattern call is UIA, never physical input. Paint is started by this probe and closed by this probe.

Evidence that motivated it (k1, 2026-10-06): "[step] click 'Edit' via uia-invoke -> WRONG_STATE | region
pixel-delta 0.000" while the save goal's "click 'Save as' via uia-expand -> PASS".
"""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import fast_uia

u32 = ctypes.windll.user32
user32 = u32


def paint_windows():
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _l):
        if user32.IsWindowVisible(h) and user32.GetWindowTextLengthW(h) > 0:
            b = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, b, 256)
            c = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, c, 256)
            if "paint" in b.value.lower() or "paint" in c.value.lower():
                out.append((int(h), b.value, c.value))
        return True

    user32.EnumWindows(cb, 0)
    return out


before = {h for h, _t, _c in paint_windows()}
user32.ShowWindow  # keep attribute refs obvious
sw = ctypes.windll.shell32.ShellExecuteW(None, "open", "mspaint.exe", None, None, 7)
print(f"ShellExecuteW -> {sw}")

hwnd = 0
for _ in range(60):
    time.sleep(0.5)
    new = [w for w in paint_windows() if w[0] not in before]
    if new:
        hwnd = new[0][0]
        print(f"paint hwnd={hwnd} title={new[0][1]!r} class={new[0][2]!r}")
        break
if not hwnd:
    print("paint did not open")
    raise SystemExit(1)


def named(sub):
    snap = fast_uia.snapshot(hwnd, timeout_ms=6000) or []
    return [(n.name, n.ctype, sorted(n.pats), tuple(n.rect)) for n in snap
            if sub in (n.name or "").lower()]


def find_uia(sub):
    """The Node whose name matches, so its LIVE control handle can be acted on (fast_uia caches the flat tree
    but keeps `el`/`ctrl` for exactly the few actions that need a handle)."""
    for n in (fast_uia.snapshot(hwnd, timeout_ms=6000) or []):
        if sub in (n.name or "").lower() and "expand" in n.pats:
            return n
    for n in (fast_uia.snapshot(hwnd, timeout_ms=6000) or []):
        if sub in (n.name or "").lower():
            return n
    return None


print("\n-- offered BEFORE any menu action --")
rows = named("edit")
for r in rows[:6]:
    print("   ", r)
print("   'paste' present?", bool(named("paste")), " total nodes:",
      len(fast_uia.snapshot(hwnd, timeout_ms=6000) or []))

def sliver_it(h):
    """Same geometry background_window.sliver() uses: park a w x h window at (-w+1, -h+1) so exactly ONE pixel
    is on screen. The app lays out (it thinks it is visible); no person can see it."""
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    w, hh = r.right - r.left, r.bottom - r.top
    user32.SetWindowPos(h, 0, -w + 1, -hh + 1, 0, 0, 0x0001 | 0x0004 | 0x0040)  # NOSIZE|NOZORDER|NOACTIVATE
    return (w, hh)


print("\n-- forcing layout (a 1px sliver on screen) --")
print("   window size:", sliver_it(hwnd))
time.sleep(1.5)
_probe = fast_uia.snapshot(hwnd, timeout_ms=6000) or []
_real = sum(1 for n in _probe if n.rect and n.rect[2] > n.rect[0])
print(f"   nodes={len(_probe)} with_nonempty_rect={_real}")
for n in (fast_uia.snapshot(hwnd, timeout_ms=6000) or []):
    if (n.name or "").lower() == "edit":
        print("   Edit now:", n.ctype, sorted(n.pats), n.rect, "expand_state=", n.expand_state)

for verb in ("invoke", "expand"):
    t = find_uia("edit")
    if t is None:
        print(f"\n{verb}: no Edit control found")
        continue
    print(f"\n== {verb.upper()} on Edit (patterns={sorted(t.pats)} expand_state={t.expand_state}) ==")
    live = t.ctrl
    try:  # start each verb from the same collapsed state
        live.GetExpandCollapsePattern().Collapse()
        time.sleep(0.6)
    except Exception:
        pass
    t0 = time.perf_counter()
    try:
        if verb == "invoke":
            live.GetInvokePattern().Invoke()
        else:
            live.GetExpandCollapsePattern().Expand()
    except Exception as exc:
        print(f"   raised {type(exc).__name__}: {str(exc)[:80]}")
    print(f"   call took {time.perf_counter() - t0:.2f}s")
    for wait in (0.6, 1.5, 3.0):
        time.sleep(wait if wait == 0.6 else wait - 0.6)
        snaps = named("paste")
        if snaps:
            print(f"   after +{wait:.1f}s: 'paste' VISIBLE {snaps[:3]}")
            break
    else:
        print(f"   after 3s: still no 'paste'. Edit-state now: "
              f"{[ (n[0], n[2]) for n in named('edit')][:2]}")
    print("   node count now:", len(fast_uia.snapshot(hwnd, timeout_ms=6000) or []))

# close only the window this probe started
for h in [w[0] for w in paint_windows() if w[0] not in before]:
    user32.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
