import ctypes, uiautomation as auto
u32 = ctypes.windll.user32
hdesk = u32.OpenDesktopW('default', 0, False, 0x01FF)
if hdesk:
    u32.SetThreadDesktop(hdesk)

root = auto.ControlFromHandle(720934)
for c, d in auto.WalkControl(root, maxDepth=10):
    name = c.Name or ""
    aid = c.AutomationId or ""
    rect = c.BoundingRectangle
    nl = name.lower()
    if any(k in nl for k in ["canvas", "paint", "image", "scroll", "pencil", "brush", "tool", "shape"]):
        print(f"{' '*d}{c.ControlTypeName} '{name}' id='{aid}' rect={rect}")
