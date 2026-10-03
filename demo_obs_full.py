"""DEMO — full Hojaiga desktop automation visibility pass.

Shows what the previous run was missing:
  1. REAL-TIME APP SCANNING via the UI-Automation tree (not screenshots).
     Every button / dropdown / checkbox is enumerated live; the scan is
     re-run after a RESIZE and after a MINIMIZE/RESTORE to prove it tracks
     the real window geometry, not a stale photo.
  2. VIRTUAL MOUSE — the OS cursor is animated to the scanned control
     coordinate and clicks there (you can watch it move).
  3. DAP CAPSULE — a small always-on-top HUD capsule shows the current
     action, like the CDP virtual-cursor capsule.
  4. Errors (crash / update dialogs) are still solved from the error_catalog DB.

Full log is written to demo_obs_full.log AND printed.
"""
from __future__ import annotations
import argparse, logging, os, subprocess, sys, threading, time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(r"D:\new_automation\demo_obs_full.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("demo")

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.organ_40_app_launcher import AppCatalog, VerbAliasEngine, AppLauncher
from core_organs.organ_29_popup_handler import resolve_dialog_via_catalog

import pyautogui
from pywinauto import Application

pyautogui.FAILSAFE = False

UPDATE_LABELS = {"Update Now", "Skip Version", "Remind me Later", "Not Now", "Later", "Skip"}
INTERACTIVE = {"Button", "ComboBox", "ListItem", "MenuItem", "Edit",
               "CheckBox", "TabItem", "Slider", "RadioButton"}


# ── Virtual mouse (visible animated OS cursor) ──────────────────────────
class VirtualMouse:
    def move_to(self, x, y, duration: float = 0.5):
        log.info("VIRTUAL MOUSE -> animate to screen (%d, %d)", x, y)
        pyautogui.moveTo(x, y, duration=duration)

    def click(self, x, y, label: str = "", duration: float = 0.4):
        self.move_to(x, y, duration)
        log.info("VIRTUAL MOUSE -> CLICK at (%d, %d)  [target: %s]", x, y, label)
        pyautogui.click(x, y)


# ── DAP capsule HUD (small always-on-top action indicator) ───────────────
class CapsuleHUD:
    """Small always-on-top action capsule (thread-safe: all Tcl calls happen
    in the HUD's own thread; the caller only ever pushes text to a queue)."""

    def __init__(self):
        import tkinter as tk
        import queue as _queue
        self._tk = tk
        self._q = _queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(5)

    def _run(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
            self.label = tk.Label(
                self.root, text="Hojaiga \u25cf READY", bg="#1e90ff", fg="white",
                font=("Segoe UI", 11, "bold"), padx=14, pady=7)
            self.label.pack()
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.92)
            self.root.geometry("+24+24")
            self._ready.set()
            self._poll()
            self.root.mainloop()
        except Exception as e:
            logging.getLogger("demo").warning("HUD thread failed: %s", e)
            self._ready.set()

    def _poll(self):
        try:
            while True:
                item = self._q.get_nowait()
                if item is None:
                    self.root.destroy()
                    return
                self.label.config(text="Hojaiga \u25cf " + item)
        except Exception:
            pass
        self.root.after(80, self._poll)

    def set(self, text: str):
        try:
            self._q.put(text)
        except Exception:
            pass

    def close(self):
        try:
            self._q.put(None)
        except Exception:
            pass


# ── Real-time app scanning (UI-Automation tree, NOT screenshots) ─────────
def scan_window(app, main_title):
    """Enumerate the live UI-Automation tree of the OBS window.

    Returns list of (control_type, name, rect) for every interactive control.
    Because this queries the live tree, it is robust to resize / minimize:
    coordinates are always fresh, never a photo.
    """
    try:
        w = app.window(title=main_title)
    except Exception:
        return []
    out = []
    try:
        for el in w.descendants():
            try:
                ct = el.element_info.control_type
                name = el.element_info.name or ""
                if ct in INTERACTIVE or name:
                    r = el.rectangle()
                    out.append((ct, name, r))
            except Exception:
                continue
    except Exception as exc:
        log.warning("scan error: %s", exc)
    return out


def log_scan(controls, tag: str):
    log.info("=== %s : %d interactive controls enumerated from UI tree ===",
             tag, len(controls))
    for ct, name, r in controls:
        if not name and ct not in INTERACTIVE:
            continue
        w, h = (r.right - r.left), (r.bottom - r.top)
        log.info("   [%s] '%-22s' @ (%d,%d)-(%d,%d)  %dx%d",
                 ct, name[:22], r.left, r.top, r.right, r.bottom, w, h)


def find_control(controls, name_substr: str, ctype: str = "Button"):
    kw = name_substr.lower()
    for ct, name, r in controls:
        if ct == ctype and kw in (name or "").lower():
            return r
    return None


def click_control_element(app, main_title, name_substr: str, ctype: str = "Button") -> bool:
    """Find the live UI-tree element and click it.

    Uses the element's own click_input(move_duration=...) so the real OS
    cursor is animated onto the control (visible virtual mouse) and the click
    is DPI/geometry-safe — no coordinate guesswork. Returns True if clicked.
    """
    try:
        w = app.window(title=main_title)
    except Exception:
        return False
    target = None
    for el in w.descendants(control_type=ctype):
        if name_substr.lower() in (el.window_text() or "").lower():
            target = el
            break
    if target is None:
        return False
    r = target.rectangle()
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    log.info("SCAN target %r center = (%d, %d)", name_substr, cx, cy)
    log.info("VIRTUAL MOUSE -> animate + CLICK at (%d, %d)  [target: %s]",
             cx, cy, name_substr)
    try:
        target.click_input(move_duration=0.4)
    except Exception as e:
        log.warning("element click failed (%s); falling back to coords", e)
        vm.click(cx, cy, name_substr)
    return True


def resolve_obstructions(app):
    """Solve any blocking popups through the shared error_catalog DB."""
    for w in app.windows():
        try:
            t = w.window_text()
        except Exception:
            continue
        try:
            btns = [el.window_text() for el in w.descendants(control_type="Button")
                    if el.window_text()]
        except Exception:
            btns = []
        if not btns:
            continue
        tl = t.lower()
        if "crash" in tl or "error" in tl:
            plan = resolve_dialog_via_catalog(t, btns)
            if plan.get("action") == "click_button":
                label = plan.get("label")
                log.info("error_db: dialog %r -> click '%s' (source=%s)",
                         t, label, plan.get("_source"))
                try:
                    w.set_focus()
                except Exception:
                    pass
                clicked = False
                for el in w.descendants(control_type="Button"):
                    if el.window_text() == label:
                        try:
                            el.click_input()
                            clicked = True
                        except Exception:
                            pass
                        break
                if not clicked:
                    # Fallback: Enter triggers the default button
                    # ("Run in Normal Mode") on OBS's crash dialog.
                    try:
                        w.type_keys("{ENTER}")
                    except Exception:
                        pass
            continue
        if any(b in UPDATE_LABELS for b in btns):
            plan = resolve_dialog_via_catalog(t, btns)
            if plan.get("action") == "click_button":
                log.info("error_db: update prompt -> click '%s' (source=%s)",
                         plan.get("label"), plan.get("_source"))
                for el in w.descendants(control_type="Button"):
                    if el.window_text() == plan.get("label"):
                        try:
                            el.click_input()
                        except Exception:
                            pass


def obs_pids():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process obs64 -EA SilentlyContinue).Id"],
        capture_output=True, text=True)
    return [int(x) for x in out.stdout.split() if x.strip().isdigit()]


def kill_all_obs():
    subprocess.run(["taskkill", "/IM", "obs64.exe", "/F"], capture_output=True)
    time.sleep(4)


def connect_obs_main(timeout: float = 70):
    from pywinauto import Application as App
    deadline = time.time() + timeout
    pid = None
    while time.time() < deadline:
        if pid is None:
            pids = obs_pids()
            if not pids:
                time.sleep(1)
                continue
            pid = pids[0]
        try:
            app = App(backend="uia").connect(process=pid, timeout=2)
        except Exception:
            pid = None
            time.sleep(1)
            continue
        try:
            wins = app.windows()
        except Exception:
            pid = None
            time.sleep(1)
            continue
        titles = [w.window_text() for w in wins]
        if any("Crash" in t or "Error" in t for t in titles):
            resolve_obstructions(app)
            log.info("Resolved blocking dialog via error_catalog; settling...")
            time.sleep(15)
            pid = None
            continue
        for w in wins:
            t = w.window_text()
            if "OBS" in t and w.is_visible() and "Crash" not in t and "Error" not in t:
                return app, t
        time.sleep(1)
    return None, None


def obs_record_dirs():
    dirs = [os.path.expandvars(r"%USERPROFILE%\Videos"),
            r"C:\Users\dhruv\Videos"]
    return dirs


def find_recording(start_time, dirs):
    exts = (".mkv", ".mp4", ".flv", ".mov", ".ts")
    cands = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith(exts):
                    p = os.path.join(root, f)
                    try:
                        m = os.path.getmtime(p)
                    except Exception:
                        continue
                    if m >= start_time - 5:
                        cands.append((m, p))
    cands.sort()
    return cands[-1][1] if cands else None


def main_run(seconds: int):
    log.info("=== DEMO: open OBS, SCAN it, drive with VIRTUAL MOUSE + CAPSULE, record, stop, find ===")

    kill_all_obs()
    cat = AppCatalog(); cat.ensure_scanned()
    engine = VerbAliasEngine(cat, gateway=None)
    name, path, used_default = engine.resolve_installed(
        "open OBS Studio and record for a while then stop and save the file")
    if used_default or not name:
        log.error("Could not resolve OBS Studio; abort."); return
    log.info("Aliasing resolved target app: %r", name)

    log.info("Launching %r (Windows search bar)...", name)
    AppLauncher(cat).launch(name)
    time.sleep(8)

    app, main_title = connect_obs_main()
    if app is None:
        log.error("OBS main window not reachable; abort."); return

    vm = VirtualMouse()
    try:
        hud = CapsuleHUD()
    except Exception as e:
        log.warning("HUD capsule unavailable: %s", e)

        class _Null:
            def set(self, *a, **k):
                pass

            def close(self):
                pass
        hud = _Null()
    hud.set("Scanning OBS UI tree...")

    # ── SCAN #1 : initial ───────────────────────────────────────────────
    controls = scan_window(app, main_title)
    log_scan(controls, "SCAN #1 (initial)")

    # ── RESIZE robustness : enlarge window, re-scan, show coords changed ─
    try:
        import win32gui
        w0 = app.window(title=main_title)
        r0 = w0.rectangle()
        hwnd = w0.handle
        new_w, new_h = r0.width() + 220, r0.height() + 130
        win32gui.MoveWindow(hwnd, r0.left, r0.top, new_w, new_h, True)
        time.sleep(1.2)
        r1 = app.window(title=main_title).rectangle()
        log.info("RESIZE: window %dx%d -> %dx%d (live UI-tree scan shows new coords)",
                 r0.width(), r0.height(), r1.width(), r1.height())
    except Exception as e:
        log.warning("resize failed: %s", e)
    controls = scan_window(app, main_title)
    log_scan(controls, "SCAN #2 (after RESIZE — coordinates are fresh)")

    # ── MINIMIZE robustness : hidden tree -> restore -> re-scan ─────────
    try:
        app.window(title=main_title).minimize()
        time.sleep(1)
        hidden = scan_window(app, main_title)
        log.info("SCAN while MINIMIZED returned %d controls "
                 "(UI tree is empty when hidden -> automation re-scans on restore)",
                 len(hidden))
        app.window(title=main_title).restore()
        time.sleep(1)
        restored = scan_window(app, main_title)
        log.info("SCAN after RESTORE returned %d controls", len(restored))
        controls = restored
    except Exception as e:
        log.warning("minimize demo failed: %s", e)

    # ── START RECORDING via virtual mouse (scanned element) ────────────
    hud.set("Locating 'Start Recording'")
    if not click_control_element(app, main_title, "Start Recording", "Button"):
        log.error("Start Recording not found in scan; abort."); hud.close(); return
    hud.set("Clicked 'Start Recording' (virtual mouse)")
    time.sleep(2)
    controls2 = scan_window(app, main_title)
    if find_control(controls2, "Stop Recording", "Button"):
        log.info("Recording STARTED (UI tree now exposes 'Stop Recording').")
    else:
        log.warning("Recording start not confirmed by re-scan; proceeding.")

    # ── Heartbeat ───────────────────────────────────────────────────────
    start_time = time.time()
    while (time.time() - start_time) < seconds:
        time.sleep(2)
        hud.set("Recording... %.0f/%ds" % (time.time() - start_time, seconds))
        log.info("recording... %.0f/%ds", time.time() - start_time, seconds)

    # ── STOP RECORDING via virtual mouse (re-scan for fresh coords) ─────
    hud.set("Locating 'Stop Recording'")
    if not click_control_element(app, main_title, "Stop Recording", "Button"):
        if not click_control_element(app, main_title, "Stop Recording", "Button"):
            log.error("Stop Recording not found in scan."); hud.close(); return
    hud.set("Clicked 'Stop Recording' (virtual mouse)")
    time.sleep(3)

    f = find_recording(start_time, obs_record_dirs())
    if f:
        log.info("RECORDING FILE FOUND: %s (%d bytes)", f, os.path.getsize(f))
    else:
        log.warning("No new recording file detected.")

    hud.set("Done")
    time.sleep(1)
    hud.close()
    # Graceful close so OBS clears its "crashed last run" flag (no force-kill).
    try:
        app.window(title=main_title).close()
    except Exception:
        pass
    time.sleep(4)
    if obs_pids():
        subprocess.run(["taskkill", "/IM", "obs64.exe", "/F"], capture_output=True)
    log.info("=== DEMO COMPLETE ===")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=8)
    args = ap.parse_args()
    main_run(args.seconds)
