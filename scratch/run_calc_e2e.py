import time, json, sys
from core_organs.desktop_grounding import operate_app

t0 = time.time()
res = operate_app(
    "Calculator",
    ["add 21 and 21"],
    isolated=True,
)
el = round(time.time() - t0, 1)
out = {
    "completed": res.get("completed"),
    "steps": res.get("steps"),
    "elapsed_s": el,
    "goals": res.get("goals"),
    "launch_note": res.get("launch_note"),
    "recipe": res.get("recipe"),
    "launched": res.get("launched"),
    "hwnd": res.get("hwnd"),
    "window_title": res.get("window_title"),
}
trace = res.get("trace") or []
out["trace_len"] = len(trace)
out["trace_tail"] = trace[-8:]
print(json.dumps(out, indent=2, default=str))

# cleanup: close any Calculator windows we opened
import ctypes, ctypes.wintypes as wt
u = ctypes.windll.user32


@ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
def _cb(h, l):
    buf = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(h, buf, 256)
    if buf.value.lower() == "applicationframewindow":
        t = u.GetWindowTextLengthW(h)
        tb = ctypes.create_unicode_buffer(t + 1)
        u.GetWindowTextW(h, tb, t + 1)
        if "Calculator" in tb.value:
            u.PostMessageW(h, 0x0010, 0, 0)
    return True


u.EnumWindows(_cb, 0)
