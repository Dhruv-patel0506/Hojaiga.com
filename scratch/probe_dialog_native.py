"""Probe 19: attach to the Excel that probe 18 left with a Save dialog open, drive that dialog PURELY natively,
and let the file say which write roads really persisted.

Why native: the loop's dialog driver reached UIA on this dialog and every attempt died with the same COM error
(-2147220992). A classic Win32 common dialog does not need UIA at all: its name box is control id 1001 and its
accept button is id 1 (the data the recognizer already carries). This attaches to the live instance, prints what
the dialog actually is, writes the path with WM_CHAR to the id-1001 child, confirms it, and reads the workbook.
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import background_window as bw                        # noqa: E402
from core_organs import headless_input as hin                          # noqa: E402
from core_organs.desktop_grounding import DesktopGrounding, file_holds_text  # noqa: E402

TARGET = r"D:\new_automation\_e2e_tmp\hj_c18.xlsx"
if os.path.exists(TARGET):
    os.remove(TARGET)

u = ctypes.windll.user32
g = DesktopGrounding()
h = g.find_window("excel")
if not h:
    print("no excel window")
    sys.exit(2)
h = int(h)
bw.mark_ours(h)
pid = ctypes.c_ulong()
u.GetWindowThreadProcessId(h, ctypes.byref(pid))
print("excel hwnd", h, "pid", pid.value, flush=True)

rows = []
for w in hin.process_windows(h, include_hidden=False):
    rows.append((int(w), hin._class_name(w), (hin.safe_window_text(w) or "")[:50]))
print("process windows:", rows, flush=True)

dialogs = [r for r in rows if r[1] in ("#32770", "NUIDialog")]
if not dialogs:
    print("no dialog is open - nothing to drive")
    sys.exit(3)
dlg = dialogs[0][0]

kids = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
def _kb(child, _l):
    buf = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(child, buf, 256)
    tb = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(child, tb, 256)
    kids.append((int(child), buf.value, u.GetDlgCtrlID(child), tb.value[:40]))
    return True


u.EnumChildWindows(dlg, _kb, 0)
print("dialog children (hwnd, class, id, text):", kids, flush=True)

name_edit = next((k for k in kids if k[2] == 1001), None)
accept = next((k for k in kids if k[2] == 1), None)
if not name_edit:
    print("no IDFILENAME(1001) child: this dialog is not the classic one")
    sys.exit(4)

eh = name_edit[0]
res = ctypes.c_size_t(0)
u.SendMessageTimeoutW(eh, 0x00B1, 0, -1, 0x2, 800, ctypes.byref(res))     # EM_SETSEL all
u.SendMessageTimeoutW(eh, 0x0303, 0, 0, 0x2, 800, ctypes.byref(res))      # WM_CLEAR
for ch in TARGET:
    u.PostMessageW(eh, 0x0102, ord(ch), 1)
time.sleep(1.0)
buf = ctypes.create_unicode_buffer(512)
u.GetWindowTextW(eh, buf, 512)
print("name box now:", repr(buf.value), flush=True)

# confirm: the dialog's default push button, by its own id (no UIA anywhere in this path)
if accept:
    u.PostMessageW(accept[0], 0x00F5, 0, 0)                                # BM_CLICK
u.PostMessageW(dlg, 0x0100, 0x0D, 0)                                      # WM_KEYDOWN VK_RETURN
u.PostMessageW(dlg, 0x0101, 0x0D, 0)                                      # WM_KEYUP
for _ in range(30):
    if os.path.exists(TARGET):
        break
    time.sleep(1.0)
time.sleep(2.0)
print("dialog still up:", bool(u.IsWindow(dlg) and u.IsWindowVisible(dlg)), flush=True)
print("file exists:", os.path.exists(TARGET),
      os.path.getsize(TARGET) if os.path.exists(TARGET) else "", flush=True)
for probe in ("42", "55", "77"):
    print(f"file holds {probe!r}:", file_holds_text(TARGET, probe), flush=True)
