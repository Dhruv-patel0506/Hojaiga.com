p = r"D:\new_automation\All codes\core_organs\atlas\scanner.py"
s = open(p, encoding="utf-8").read()
old = "def resolve_installed(name: str) -> str:"
new = '''def close_owned(h: int, timeout_s: float = 9.0) -> Dict[str, Any]:
    """Close a program window THIS scan launched (a disposable empty document), whatever it asks. Order: the engine's polite close; if a (possibly hidden, off-screen) save prompt
    holds it open, answer it with the non-saving button; if the process still refuses, end the process we started (nothing of the user's is in it). Reports what was needed."""
    import ctypes
    from core_organs import universal_scan as us
    from core_organs import fast_uia
    from core_organs import headless_input as hin
    u32 = ctypes.windll.user32
    rec: Dict[str, Any] = {"how": "close"}
    try:
        pid = hin.window_pid(h) if u32.IsWindow(h) else 0
    except Exception:
        pid = 0
    if us.close_window(h, timeout_s=timeout_s / 2, discard_unsaved=True):
        return rec
    # hidden save prompts are windows of the same process that the engine's popup listing does not show
    for _ in range(2):
        for w in hin.process_windows(h, include_hidden=True):
            if w == h:
                continue
            nodes = fast_uia.snapshot(w, timeout_ms=3000) or []
            if not any(re.search(r"save (your )?changes|do you want to save|want to save", n.name or "", re.I) for n in nodes):
                continue
            btn = next((n for n in nodes if n.ctype == "ButtonControl" and re.match(r"(don.t save|no|discard|close without saving)", (n.name or "").strip(), re.I) and "invoke" in n.pats), None)
            if btn is not None:
                try:
                    btn.ctrl.GetInvokePattern().Invoke()
                    rec["how"] = "answered the save prompt with the non-saving button"
                except Exception:
                    pass
        time.sleep(1.2)
        if not u32.IsWindow(h):
            return rec
    if u32.IsWindow(h) and pid:
        import subprocess
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
        rec["how"] = "process ended (it refused to close and holds only the scan's empty document)"
        time.sleep(0.8)
    rec["closed"] = not u32.IsWindow(h)
    return rec


def resolve_installed(name: str) -> str:'''
assert old in s
s = s.replace(old, new, 1)
old = 'live["closed"] = bool(us.close_window(h, discard_unsaved=True))'
assert old in s
s = s.replace(old, 'live["closed"] = close_owned(h)', 1)
if "\nimport re\n" not in s and "import re" not in s.split("class Atlas")[0]:
    s = s.replace("import os\n", "import os\nimport re\n", 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
