import time, json
from core_organs.desktop_grounding import operate_app

GOALS = ["press 2", "press 1", "press plus", "press 2", "press 1", "press equals"]

t0 = time.time()
res = operate_app("Calculator", GOALS, isolated=True, max_steps_per_goal=4)
el = round(time.time() - t0, 1)
out = {
    "completed": res.get("completed"),
    "steps": res.get("steps"),
    "elapsed_s": el,
    "launched": res.get("launched"),
    "window_title": res.get("window_title"),
}
trace = res.get("trace") or []
out["trace_len"] = len(trace)
out["trace"] = [
    {
        "goal": t.get("goal"),
        "element": t.get("element"),
        "verb": t.get("verb"),
        "verdict": t.get("verdict"),
        "method": t.get("method"),
        "evidence": (t.get("evidence") or "")[:90],
    }
    for t in trace
]
print(json.dumps(out, indent=2, default=str))

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
