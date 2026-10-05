import uiautomation as auto
import ctypes
import time
import win32gui
import win32process

user32 = ctypes.windll.user32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

hwnd = None
for w in auto.GetRootControl().GetChildren():
    if "obs" in (w.Name or "").lower() and "crash" not in (w.Name or "").lower():
        hwnd = w.NativeWindowHandle
        break

print(f"OBS HWND: {hwnd}")
if not hwnd:
    sys.exit(1)

root = auto.ControlFromHandle(hwnd)
btn = root.ButtonControl(Name="Settings")
print("Button exists:", btn.Exists(2))
print("Button Name:", btn.Name)
print("Button ClassName:", btn.ClassName)
print("Button AutomationId:", btn.AutomationId)
print("Button IsEnabled:", btn.IsEnabled)
print("Button IsOffscreen:", btn.IsOffscreen)
print("Button BoundingRect:", btn.BoundingRectangle)
print("Button Patterns:")
for pat_name in ["GetInvokePattern", "GetTogglePattern", "GetSelectionItemPattern", "GetValuePattern"]:
    if hasattr(btn, pat_name):
        try:
            pat = getattr(btn, pat_name)()
            print(f"  {pat_name}: {pat}")
        except Exception as e:
            print(f"  {pat_name}: error {e}")

# Check parent hierarchy
p = btn.GetParentControl()
chain = []
while p and p.NativeWindowHandle != auto.GetRootControl().NativeWindowHandle:
    chain.append(f"{p.ControlTypeName}('{p.Name}', class='{p.ClassName}', hwnd={p.NativeWindowHandle})")
    p = p.GetParentControl()
print("\nParent chain:")
for c in chain:
    print("  <-", c)
