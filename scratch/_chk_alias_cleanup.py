"""Check VerbAliasEngine.resolve after adding the powerpoint entry, and close any
Chrome profile-picker window the earlier misfire left on screen."""
import sys
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_40_app_launcher import AppCatalog, VerbAliasEngine

eng = VerbAliasEngine(AppCatalog())
for q in ["powerpoint", "microsoft powerpoint", "create a presentation",
          "word", "excel", "gmail", "open blender"]:
    app, src = eng.resolve_detailed(q)
    print(f"resolve({q!r:32}) -> {app!r:22} source={src}")

# cleanup: close the profile picker (window titled 'Who's using Chrome?') if present
import win32con  # noqa: E402
import win32gui  # noqa: E402

closed = []


def cb(h, _):
    t = win32gui.GetWindowText(h) or ""
    c = win32gui.GetClassName(h)
    if ("Who's using Chrome" in t or "DevTools" in t) and c.startswith("Chrome_"):
        win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
        closed.append((t, c))


win32gui.EnumWindows(cb, None)
print("closed stray windows:", closed or "none found")
