"""
deep_ui_scan -- Stage 1 of the corrected pipeline: the "Xerox" recursive UI scanner.

Instead of hand-coding which buttons exist, this OPENS an app and DISCOVERS its whole
capability surface from the live UIA tree: it expands every ExpandCollapse node (the
Calculator nav drawer, menu bars) and invokes top-level menus (File/Edit/View), re-scanning
after each to capture controls that only exist once a flyout is open, then collapses/Escapes.
The result is brain/ui_capability_map_<app>.json -- the ground-truth "what this app can do"
map that the guide + LLM planner (Stages 2-3) reason over. Zero hardcoded button lists.

Usage: python deep_ui_scan.py [Calculator Notepad Paint ...]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path("All codes").resolve()))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ["HOJAIGA_OFFSCREEN"] = "1"
from core_organs import fast_uia, headless_input as hin

UIA_EXPAND = 10005
UIA_INVOKE = 10000
OUT_DIR = Path("brain")
APPS = {"Calculator": "calc.exe", "Notepad": "notepad.exe", "Paint": "mspaint.exe",
        "Character": "charmap.exe"}   # classic Win32 GDI app (window title "Character Map")
MENU_WORDS = {"file", "edit", "view", "help", "format", "settings"}


def find(app):
    for h, t in hin.top_level_titles(visible_only=False):
        if app.lower() in (t or "").lower():
            return h, t
    return None, None


def ensure(app, exe):
    h, t = find(app)
    if h:
        return h, t
    subprocess.Popen([exe])
    for _ in range(20):
        time.sleep(0.6)
        h, t = find(app)
        if h:
            return h, t
    return None, None


def snap(h):
    try:
        return fast_uia.snapshot(h, max_nodes=8000) or []
    except Exception:
        return []


def key(n):
    return (str(n.name or ""), str(n.aid or ""), str(n.ctype or ""))


def rec(n, under=""):
    return {"name": n.name, "aid": n.aid, "ctype": n.ctype, "enabled": bool(n.enabled),
            "expandable": "expand" in (n.pats or []), "under": under}


def scan_app(app):
    exe = APPS.get(app)
    if not exe:
        return None
    h, t = ensure(app, exe)
    if not h:
        print(f"[scan] {app}: window not found"); return None
    hin.isolate_offscreen(h)
    time.sleep(0.4)
    found = {}
    for n in snap(h):
        k = key(n)
        if k[0] or k[1]:
            found[k] = rec(n)

    # 1) expand every ExpandCollapse node (nav drawer, combo, group) to reveal hidden children
    expands = [n for n in snap(h) if "expand" in (n.pats or [])][:40]
    for n in expands:
        try:
            pat = n.ctrl.GetPattern(UIA_EXPAND)
            if pat is None:
                continue
            pat.Expand(); time.sleep(0.35)
            for m in snap(h):
                k = key(m)
                if (k[0] or k[1]) and k not in found:
                    found[k] = rec(m, under=(n.name or n.aid))
            try:
                pat.Collapse()
            except Exception:
                hin.post_key_combo(h, "Escape")
            time.sleep(0.15)
        except Exception:
            pass

    # 2) open top-level menus (File/Edit/View/...) by name and capture their items
    for n in snap(h):
        nm = str(n.name or "").lower()
        if nm in MENU_WORDS or "menu" in str(n.ctype or "").lower():
            try:
                ip = n.ctrl.GetPattern(UIA_INVOKE)
                if ip is not None:
                    ip.Invoke(); time.sleep(0.35)
                    for m in snap(h):
                        k = key(m)
                        if (k[0] or k[1]) and k not in found:
                            found[k] = rec(m, under=str(n.name))
                    hin.post_key_combo(h, "Escape"); time.sleep(0.15)
            except Exception:
                pass
    hin.post_key_combo(h, "Escape")
    try:
        hin.release_isolation(h)
    except Exception:
        pass

    controls = list(found.values())
    out = OUT_DIR / f"ui_capability_map_{app.lower()}.json"
    out.write_text(json.dumps({"app": app, "count": len(controls), "controls": controls},
                              ensure_ascii=False, indent=3), encoding="utf-8")
    print(f"[scan] {app}: {len(controls)} controls discovered -> {out}")
    return controls


def _reset_calculator_mode():
    """The Xerox scan clicks through EVERY mode (landing on Speed Converter), and Windows
    persists that last-mode in the locked UWP Settings hive -> Calculator then boots into a
    converter with no CalculatorResults/operators, silently breaking all math automation.
    Reset-AppxPackage restores the Standard-mode default so later runs start clean."""
    subprocess.run(["taskkill", "/F", "/IM", "CalculatorApp.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "Calculator.exe"], capture_output=True)
    time.sleep(1.0)
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-AppxPackage *WindowsCalculator* | Reset-AppxPackage"], capture_output=True, timeout=180)
        print("[scan] Calculator mode reset to Standard (Reset-AppxPackage)")
    except Exception as e:
        print(f"[scan] Calculator mode reset failed: {type(e).__name__}")


def main():
    subprocess.run(["taskkill", "/F", "/IM", "CalculatorApp.exe"], capture_output=True)
    apps = sys.argv[1:] or list(APPS)
    for app in apps:
        cs = scan_app(app)
        if not cs:
            continue
        interesting = [c for c in cs if any(x in (c["name"] or "") for x in
                       ("Memory", "Recall", "Square", "Cube", "Scientific", "Programmer",
                        "Graphing", "Convert", "Date", "sin", "cos", "log", "File", "Edit",
                        "View", "Save", "Pencil", "Brush", "Eraser", "Canvas", "Figure"))]
        for c in interesting[:30]:
            print(f"    * {c['name']!r} [{c['ctype']}] en={c['enabled']} under={c['under']!r}")
    if "Calculator" in apps or (len(sys.argv) <= 1):
        _reset_calculator_mode()


if __name__ == "__main__":
    main()
