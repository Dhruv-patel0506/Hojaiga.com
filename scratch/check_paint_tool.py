import ctypes, uiautomation as auto
u32 = ctypes.windll.user32
hdesk = u32.OpenDesktopW("default", 0, False, 0x01FF)
if hdesk:
    u32.SetThreadDesktop(hdesk)

root = auto.ControlFromHandle(720934)
for c, d in auto.WalkControl(root, maxDepth=10):
    if c.Name in ('Pencil', 'Brushes', 'Selection', 'Eraser', 'Fill', 'Oval', 'Rectangle', 'Shapes'):
        print(f"{c.ControlTypeName} '{c.Name}' id='{c.AutomationId}' rect={c.BoundingRectangle}")
