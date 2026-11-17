"""Why did 'asked the search for Power & battery: nothing appeared' happen?
Launch an owned, PARKED Settings; put the words in the catalogued search box the same way the executor does; then watch the WHOLE tree (main + popups) for 6 s and print what shows up."""
import sys, time
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import background_window as bw, fast_uia, headless_input as hin
from core_organs.professor import launcher as LN, state_protect as SPT
from core_organs.professor.effectors import Effector

hin.ensure_input_desktop()
t = LN.resolve("settings")
guard = SPT.StateGuard("settings", t.appid)
info = LN.launch_owned(t, guard)
print("launch:", {k: info.get(k) for k in ("launched", "hwnd", "title")})
hwnd = int(info.get("hwnd") or 0)
if not hwnd:
    sys.exit("no window")
bg = bw.BackgroundSession(hwnd)
bg.__enter__()
print("park mode:", getattr(bg, "mode", "?"))
time.sleep(3.0)

def names(tag):
    nodes = fast_uia.snapshot(hwnd, timeout_ms=8000) or []
    pops = []
    try:
        from core_organs.professor.dialogs import light_popups
        pops = list(light_popups(hwnd))
    except Exception as exc:
        print("popups err", exc)
    extra = []
    for w in pops:
        extra += (fast_uia.snapshot(w, timeout_ms=4000) or [])
    print(f"{tag}: main={len(nodes)} nodes, popup windows={len(pops)} (+{len(extra)} popup nodes)")
    hits = [n for n in nodes + extra if "power" in (n.name or "").lower() or "battery" in (n.name or "").lower()]
    for n in hits[:12]:
        print("   hit:", repr(n.name)[:70], "| role", n.role, "| rect", n.rect)
    return nodes, extra

nodes, _ = names("before")
box = next((n for n in nodes if (n.aid or "") == "CommandSearchTextBox"), None)
print("search box node:", box is not None, (box.name, box.rect) if box else "")
fx = Effector(hwnd, allow_input=True, owned=True)
if box is not None:
    ok, how = fx.set_value(box, "Power & battery")
    print("set_value:", ok, how)
    time.sleep(0.6)
    # did the words actually LAND in the box? read its value back from the fresh tree
    for n in (fast_uia.snapshot(hwnd, timeout_ms=6000) or []):
        if (n.aid or "") == "CommandSearchTextBox":
            print("box value after set_value:", repr(getattr(n, "value", None))[:60], "| name now", repr(n.name)[:60])
            break
    fx.insert_text("Power & battery", deadline_s=2.0)
    time.sleep(0.6)
    for n in (fast_uia.snapshot(hwnd, timeout_ms=6000) or []):
        if (n.aid or "") == "CommandSearchTextBox":
            print("box value after typing:", repr(getattr(n, "value", None))[:60], "| name now", repr(n.name)[:60])
            break
end = time.time() + 6.0
while time.time() < end:
    nodes, extra = names("poll")
    if any("battery" in (n.name or "").lower() for n in nodes + extra):
        break
    time.sleep(1.0)
try:
    bg.__exit__(None, None, None)
except Exception:
    pass
print("done")
