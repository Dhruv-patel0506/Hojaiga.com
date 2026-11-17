import uiautomation as ua

calc = ua.WindowControl(searchDepth=1, ClassName='ApplicationFrameWindow')
if not calc.Exists(0, 0):
    print("Not found")
else:
    for c, d in ua.WalkControl(calc, maxDepth=10):
        if "Standard" in c.Name:
            print("Found:", c.Name, "ControlTypeName:", c.ControlTypeName, "BoundingRectangle:", c.BoundingRectangle, "IsEnabled:", c.IsEnabled)
            print("Patterns:")
            for p in ["Invoke", "Toggle", "SelectionItem", "ExpandCollapse", "LegacyIAccessible"]:
                try:
                    pat = c.GetPattern(getattr(ua.PatternId, f"{p}Pattern"))
                    print(f"  {p}: {pat}")
                except Exception as e:
                    pass
