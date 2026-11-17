"""Probe the object-model reroute on an OWNED parked Word: ExecuteMso + TypeText, no focus change."""
import sys, time, ctypes
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.professor import apprun as AR
from core_organs.professor.adapters.object_model import OfficeModel, _native_om
from core_organs import fast_uia

u = ctypes.windll.user32
fg0 = u.GetForegroundWindow()
run = AR.AppRun(AR.spec_for(sys.argv[1] if len(sys.argv) > 1 else "word"), echo=True, vision=False)
try:
    print("start", run.start(), run.hwnd)
    om = OfficeModel.for_window(run.hwnd, run.target.exe)
    print("model:", om)
    if om:
        print("type:", om.type_text("Hojaiga object model test. "))
        print("select all:", om.execute("SelectAll"))
        print("bold:", om.execute("Bold"))
        print("bold pressed:", om._call(lambda app: app.CommandBars.GetPressedMso("Bold"), 4.0))
        print("text now:", om._call(lambda app: app.ActiveDocument.Content.Text[:60] if hasattr(app, "ActiveDocument") else "-", 4.0))
        print("calls", om.calls)
finally:
    print("fg changed?", u.GetForegroundWindow() != fg0)
    run._teardown()
    print("closed")
